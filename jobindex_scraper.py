#!/usr/bin/env python3
"""
Jobindex Scraper - Comprehensive scraper for all job postings on Jobindex.dk
Scrapes job search pages, extracts job URLs, and stores job content in Chroma vector database
"""

import hashlib
import asyncio
import logging
import os
import time
from playwright.async_api import async_playwright, Error as PlaywrightError
from readability import Document
from openai import OpenAI
from chromadb import HttpClient
import argparse
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import re
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('jobindex_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Set specific loggers to reduce verbosity
logging.getLogger('playwright').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)

# Configuration from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your_openai_api_key_here")
CHROMA_HOST = os.getenv("CHROMA_HOST", "your_chroma_host_here")
CHROMA_TENANT = os.getenv("CHROMA_TENANT", "your_chroma_tenant_id_here")
CHROMA_DATABASE = os.getenv("CHROMA_DATABASE", "your_chroma_database_name_here")
CHROMA_API_KEY = os.getenv("CHROMA_API_KEY", "your_chroma_api_token_here")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "2000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "250"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "jobs")

# Jobindex configuration
JOBINDEX_BASE_URL = "https://www.jobindex.dk"
JOBINDEX_SEARCH_URL = "https://www.jobindex.dk/jobsoegning"
MAX_PAGES = 1000
DELAY_BETWEEN_REQUESTS = 1
DELAY_BETWEEN_JOB_REQUESTS = 0.5

class JobindexScraper:
    def __init__(self):
        self.openai_client = OpenAI(api_key=OPENAI_API_KEY)
        self.chroma_client = None
        self.collection = None
        self.processed_urls = set()
        self.failed_urls = set()
        self.browser = None
        self.context = None
        self.page = None

    def init_chroma(self):
        """Initialize ChromaDB connection"""
        try:
            self.chroma_client = HttpClient(
                ssl=True,
                host=CHROMA_HOST,
                tenant=CHROMA_TENANT,
                database=CHROMA_DATABASE,
                headers={'x-chroma-token': CHROMA_API_KEY}
            )
            self.collection = self.chroma_client.get_or_create_collection(COLLECTION_NAME)
            logger.info(f"Connected to ChromaDB collection: {COLLECTION_NAME}")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            raise

    async def init_browser(self):
        """Initialize Playwright browser with manual stealth settings"""
        try:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-zygote',
                ]
            )
            self.context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                bypass_csp=True
            )
            
            try:
                with open('stealth.js', 'r') as f:
                    stealth_script = f.read()
                await self.context.add_init_script(stealth_script)
            except FileNotFoundError:
                logger.error("stealth.js not found! Please create it in the same directory.")
                raise
            
            self.page = await self.context.new_page()
            
            async def route_interceptor(route):
                if route.request.resource_type in {"image", "font", "media", "stylesheet"}:
                    await route.abort()
                else:
                    await route.continue_()
            await self.page.route("**/*", route_interceptor)
            
            logger.info("Playwright browser initialized with stealth settings.")
            
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            raise

    async def extract_job_urls_from_page(self, page_num: int = 1) -> List[str]:
        """Extract job URLs from a job search page using Playwright"""
        url = f"{JOBINDEX_SEARCH_URL}?page={page_num}" if page_num > 1 else JOBINDEX_SEARCH_URL
        logger.info(f"Scraping job search page {page_num}: {url}")

        try:
            if not await self._is_browser_alive():
                logger.warning(f"Browser not responsive, attempting recovery before page {page_num}")
                await self._recover_browser()

            await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            # Initial cookie dismissal
            await self.try_dismiss_cookies()
            
            # Wait for page to fully load and check for any delayed cookie banners
            await asyncio.sleep(2)
            await self.dismiss_cookies_if_present()
            
            # Force dismiss any overlays that might block job extraction
            await self.force_dismiss_overlays()
            
            job_urls = await self.extract_jobs_from_page()
            logger.info(f"Found {len(job_urls)} unique job URLs on page {page_num}")
            return job_urls

        except Exception as e:
            logger.error(f"Error scraping page {page_num}: {e}")
            return []

    async def try_dismiss_cookies(self):
        """Try to dismiss cookie banners with comprehensive selector coverage"""
        # Common cookie banner selectors in multiple languages
        selectors = [
            # Danish
            'button:has-text("Accepter alle")',
            'button:has-text("Accepter")',
            'button:has-text("OK")',
            'button:has-text("Jeg accepterer")',
            'button:has-text("Godkend alle")',
            'button:has-text("Godkend")',
            # English
            'button:has-text("Accept all")',
            'button:has-text("Accept")',
            'button:has-text("OK")',
            'button:has-text("I accept")',
            'button:has-text("Allow all")',
            'button:has-text("Allow")',
            'button:has-text("Got it")',
            'button:has-text("Continue")',
            # Generic button selectors
            '[data-testid*="cookie"] button',
            '[class*="cookie"] button',
            '[id*="cookie"] button',
            '.cookie-banner button',
            '.cookie-notice button',
            '.cookie-popup button',
            '.cookie-modal button',
            # More specific selectors
            'button[data-testid="cookie-accept"]',
            'button[data-testid="cookie-accept-all"]',
            'button[data-testid="cookie-allow"]',
            'button[data-testid="cookie-allow-all"]',
            # Class-based selectors
            '.cookie-accept',
            '.cookie-accept-all',
            '.cookie-allow',
            '.cookie-allow-all',
            '.cookie-close',
            '.cookie-dismiss',
            # ID-based selectors
            '#cookie-accept',
            '#cookie-accept-all',
            '#cookie-allow',
            '#cookie-allow-all',
            '#cookie-close',
            '#cookie-dismiss',
            # Generic close buttons
            'button[aria-label*="close"]',
            'button[aria-label*="dismiss"]',
            'button[title*="close"]',
            'button[title*="dismiss"]',
            '.close',
            '.dismiss',
            '.btn-close',
            '.modal-close'
        ]
        
        dismissed = False
        for selector in selectors:
            try:
                # Try to find the button
                button = self.page.locator(selector).first
                if await button.is_visible(timeout=1000):
                    # Check if it's actually clickable
                    if await button.is_enabled(timeout=1000):
                        await button.click(timeout=2000)
                        logger.debug(f"Dismissed cookie banner using selector: {selector}")
                        await asyncio.sleep(0.5)
                        dismissed = True
                        break
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue
        
        # Additional fallback: try to find any visible button with cookie-related text
        if not dismissed:
            try:
                # Look for any button containing cookie-related words
                cookie_buttons = await self.page.query_selector_all('button')
                for button in cookie_buttons:
                    try:
                        button_text = await button.text_content()
                        if button_text and any(word in button_text.lower() for word in ['accept', 'accepter', 'godkend', 'allow', 'ok', 'close', 'dismiss']):
                            if await button.is_visible(timeout=1000) and await button.is_enabled(timeout=1000):
                                await button.click(timeout=2000)
                                logger.debug(f"Dismissed cookie banner using fallback text detection: {button_text}")
                                await asyncio.sleep(0.5)
                                dismissed = True
                                break
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"Fallback cookie detection failed: {e}")
        
        if not dismissed:
            logger.debug("No cookie banner found or dismissed")
        else:
            # Wait a bit more to ensure the banner is fully dismissed
            await asyncio.sleep(1)

    async def dismiss_cookies_if_present(self):
        """Check and dismiss any cookie banners that might have appeared"""
        try:
            # Quick check for common cookie banner indicators
            cookie_indicators = [
                '[class*="cookie"]',
                '[id*="cookie"]',
                '[data-testid*="cookie"]',
                '.cookie-banner',
                '.cookie-notice',
                '.cookie-popup',
                '.cookie-modal'
            ]
            
            for indicator in cookie_indicators:
                try:
                    element = await self.page.query_selector(indicator)
                    if element and await element.is_visible(timeout=500):
                        logger.info("🔄 Cookie banner detected, attempting to dismiss...")
                        await self.try_dismiss_cookies()
                        return
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Cookie check failed: {e}")

    async def force_dismiss_overlays(self):
        """Force dismiss any overlay elements that might block interactions"""
        try:
            # Try to click on common overlay dismiss areas
            overlay_selectors = [
                '.overlay',
                '.modal-backdrop',
                '.popup-backdrop',
                '.lightbox-backdrop',
                '[class*="overlay"]',
                '[class*="modal"]',
                '[class*="popup"]'
            ]
            
            for selector in overlay_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element and await element.is_visible(timeout=500):
                        # Try clicking on the overlay itself
                        await element.click(timeout=1000)
                        logger.debug(f"Clicked overlay: {selector}")
                        await asyncio.sleep(0.5)
                except Exception:
                    continue
                    
            # Try pressing Escape key to close modals
            await self.page.keyboard.press('Escape')
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.debug(f"Overlay dismissal failed: {e}")

    async def cleanup_page_interferences(self):
        """Clean up any page elements that might interfere with scraping"""
        try:
            # Check for and dismiss cookie banners
            await self.dismiss_cookies_if_present()
            
            # Dismiss overlays
            await self.force_dismiss_overlays()
            
            # Try to scroll to ensure all content is loaded
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.5)
            await self.page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.debug(f"Page cleanup failed: {e}")

    async def extract_jobs_from_page(self) -> List[str]:
        """Extracts job URLs from the current page with improved filtering."""
        job_urls = set()
        all_found_urls = set()  # For debugging
        
        try:
            # Get all links on the page for debugging
            all_links = await self.page.query_selector_all('a[href]')
            logger.debug(f"Found {len(all_links)} total links on the page")
            
            # Also check for any elements with "job" in the class or text
            job_elements = await self.page.query_selector_all('[class*="job"], [class*="stilling"], [class*="seejob"]')
            logger.debug(f"Found {len(job_elements)} elements with job-related classes")
            
        except Exception as e:
            logger.debug(f"Debug analysis failed: {e}")
        
        # First, try to find the main job listings container
        try:
            # Use the precise selector that gives exactly 20 links (same as find_links.py)
            seejobdesktop_links = await self.page.query_selector_all('a.seejobdesktop')
            logger.info(f"Found {len(seejobdesktop_links)} job links on page")
            
            if len(seejobdesktop_links) != 20:
                logger.warning(f"Expected 20 links, found {len(seejobdesktop_links)}")
            
            # Extract URLs from the seejobdesktop links
            for link in seejobdesktop_links:
                try:
                    href = await link.get_attribute('href')
                    if href:
                        full_url = urljoin(JOBINDEX_BASE_URL, href)
                        all_found_urls.add(full_url)
                        job_urls.add(full_url)
                except Exception:
                    continue
                    
        except Exception as e:
            logger.debug(f"Precise selector extraction failed: {e}")
        
        # If still no results, try the most specific "Se job" approach
        if len(job_urls) == 0:
            logger.info("Trying fallback job extraction...")
            try:
                # Use only the most precise selector that gives exactly 20 links
                se_job_selectors = [
                    'a.seejobdesktop',          # Specific class - gives exactly 20 links!
                ]
                
                for selector in se_job_selectors:
                    try:
                        buttons = await self.page.query_selector_all(selector)
                        logger.debug(f"Found {len(buttons)} buttons with selector: {selector}")
                        
                        for button in buttons:
                            try:
                                href = await button.get_attribute('href')
                                if href:
                                    full_url = urljoin(JOBINDEX_BASE_URL, href)
                                    all_found_urls.add(full_url)
                                    
                                    # For redirect URLs, we need to follow them to get the actual job URL
                                    if href.startswith('/c?t=h') or 'c?t=h' in href:
                                        actual_job_url = await self._follow_jobindex_redirect(full_url)
                                        if actual_job_url:
                                            job_urls.add(actual_job_url)
                                            logger.debug(f"Added actual job URL from redirect: {actual_job_url}")
                                        else:
                                            # If redirect fails, keep the redirect URL as fallback
                                            job_urls.add(full_url)
                                            logger.debug(f"Added redirect URL as fallback: {full_url}")
                                    else:
                                        if self._is_valid_job_url(href):
                                            job_urls.add(full_url)
                                            logger.debug(f"Added direct job URL: {full_url}")
                            except Exception as e:
                                logger.debug(f"Error extracting href from button with selector {selector}: {e}")
                                continue
                                
                    except Exception as e:
                        logger.debug(f"Selector {selector} failed: {e}")
                        continue
                        
            except Exception as e:
                logger.debug(f"Specific 'Se job' extraction failed: {e}")
        
        # Filter and validate URLs
        filtered_urls = []
        for url in job_urls:
            if self._is_valid_job_url(url):
                filtered_urls.append(url)
        
        # Sort URLs to ensure consistent ordering
        filtered_urls.sort()
        
        logger.info(f"Extracted {len(filtered_urls)} valid job URLs")
        
        return filtered_urls
    
    def _is_valid_job_url(self, url: str) -> bool:
        """Validate if a URL is actually a job posting URL."""
        if not url:
            return False
        
        # Since we're using the precise 'seejobdesktop' selector, 
        # we can be more permissive with URL validation
        # Convert to lowercase for easier matching
        url_lower = url.lower()
        
        # Must be a proper URL (not just a fragment or relative path)
        if url.startswith('#') or url.startswith('javascript:'):
            return False
        
        # Must have some path content (not just domain)
        parsed = urlparse(url)
        if not parsed.path or len(parsed.path.strip('/')) < 1:
            return False
        
        # For seejobdesktop links, we trust that they're job-related
        # Just do basic validation
        return True

    async def _follow_jobindex_redirect(self, redirect_url: str) -> Optional[str]:
        """Follow Jobindex redirect URLs to get the actual job posting URL."""
        try:
            logger.debug(f"Following redirect: {redirect_url}")
            
            # Create a new page context for the redirect to avoid interfering with main scraping
            redirect_page = await self.context.new_page()
            
            try:
                # Navigate to the redirect URL
                await redirect_page.goto(redirect_url, wait_until='domcontentloaded', timeout=15000)
                
                # Wait a bit for the redirect to complete
                await asyncio.sleep(2)
                
                # Get the final URL after redirect
                final_url = redirect_page.url
                
                # Check if we got redirected to an actual job posting
                if final_url != redirect_url and self._is_valid_job_url(final_url):
                    logger.debug(f"Redirect successful: {redirect_url} → {final_url}")
                    return final_url
                else:
                    logger.debug(f"Redirect didn't lead to valid job URL: {final_url}")
                    return None
                    
            finally:
                # Always close the redirect page
                await redirect_page.close()
                
        except Exception as e:
            logger.error(f"Error following redirect {redirect_url}: {e}")
            return None
    
    async def extract_job_content(self, url: str) -> Optional[str]:
        """Extract clean text content from a job posting URL"""
        try:
            if not await self._is_browser_alive():
                await self._recover_browser()
            
            await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            # Handle any cookie banners that might appear on job pages
            await self.try_dismiss_cookies()
            await asyncio.sleep(1)
            await self.dismiss_cookies_if_present()
            await self.force_dismiss_overlays()
            
            await asyncio.sleep(2)
            html = await self.page.content()

            text = self._try_readability_extraction(html, url)
            if text and len(text) > 200:
                return self.clean_text(text)
            
            text = self._try_basic_extraction(html, url)
            if text and len(text) > 100:
                return self.clean_text(text)

            return None
        except PlaywrightError as e:
            if "Target page, context or browser has been closed" in str(e):
                logger.error(f"Browser crashed for {url}. Falling back to requests.")
                return await self._try_requests_fallback(url)
            else:
                logger.warning(f"Playwright error for {url}: {e}. Falling back.")
                return await self._try_requests_fallback(url)
        except Exception as e:
            logger.error(f"General error extracting content for {url}: {e}")
            return await self._try_requests_fallback(url)

    def _try_readability_extraction(self, html: str, url: str) -> Optional[str]:
        try:
            doc = Document(html)
            summary = doc.summary()
            soup = BeautifulSoup(summary, "html.parser")
            return soup.get_text("\n", strip=True)
        except Exception as e:
            logger.debug(f"Readability failed for {url}: {e}")
            return None

    def _try_basic_extraction(self, html: str, url: str) -> Optional[str]:
        try:
            soup = BeautifulSoup(html, "html.parser")
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'form']):
                element.decompose()
            body = soup.find('body')
            return body.get_text("\n", strip=True) if body else None
        except Exception as e:
            logger.debug(f"Basic extraction failed for {url}: {e}")
            return None

    async def _try_requests_fallback(self, url: str) -> Optional[str]:
        logger.info(f"Attempting requests fallback for {url}")
        try:
            response = await asyncio.to_thread(
                requests.get, url, timeout=20, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)'}
            )
            response.raise_for_status()
            text = self._try_readability_extraction(response.text, url)
            return self.clean_text(text) if text and len(text) > 100 else None
        except Exception as e:
            logger.error(f"Requests fallback FAILED for {url}: {e}")
            return None

    async def _is_browser_alive(self) -> bool:
        try:
            return self.browser and self.browser.is_connected() and not self.page.is_closed()
        except Exception:
            return False

    async def _recover_browser(self):
        logger.info("🔄 Attempting browser recovery...")
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
        await self.init_browser()

    def clean_text(self, text: str) -> str:
        if not text: return ""
        text = re.sub(r'\n\s*\n', '\n\n', text).strip()
        return text

    def chunks(self, text: str) -> List[str]:
        if not text or len(text) < 100: return []
        chunks_list = []
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            chunks_list.append(text[start:end])
            start += CHUNK_SIZE - CHUNK_OVERLAP
        return chunks_list

    def embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        if not texts: return None
        try:
            response = self.openai_client.embeddings.create(model="text-embedding-3-large", input=texts)
            return [data.embedding for data in response.data]
        except Exception as e:
            logger.error(f"Error creating embeddings: {e}")
            return None

    def store_job_in_chroma(self, url: str, content: str):
        """
        Stores job content in ChromaDB with detailed metadata.
        """
        try:
            doc_id = hashlib.sha256(url.encode("utf-8")).hexdigest()
            chunks_list = self.chunks(content)
            if not chunks_list:
                logger.warning(f"No chunks created for {url}, skipping storage.")
                return

            vectors = self.embed_texts(chunks_list)
            if not vectors:
                logger.error(f"Embedding failed for {url}, skipping storage.")
                return

            ids = [f"{doc_id}-{i}" for i in range(len(chunks_list))]
            scraped_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # **OPDATERET**: Implementering af den ønskede metadata
            metadatas = [
                {
                    "url": url,
                    "doc_id": doc_id,
                    "chunk_index": i,
                    "scraped_at": scraped_timestamp,
                    "source": "jobindex"
                }
                for i in range(len(chunks_list))
            ]
            
            self.collection.add(
                ids=ids,
                documents=chunks_list,
                embeddings=vectors,
                metadatas=metadatas
            )
            logger.debug(f"Stored {len(chunks_list)} chunks for {url}")
        except Exception as e:
            logger.error(f"Error storing in Chroma for {url}: {e}")

    async def scrape_all_jobs(self, max_pages: int, start_page: int):
        self.init_chroma()
        await self.init_browser()
        
        logger.info(f"Starting job scraping: {max_pages} pages from page {start_page}")
        logger.info(f"Estimated jobs to process: {max_pages * 20}")
        
        total_stored = 0
        page_errors = 0
        max_page_errors = 3  # Allow some page errors before giving up
        
        try:
            for page_num in range(start_page, start_page + max_pages):
                progress = ((page_num - start_page) / max_pages) * 100
                logger.info(f"Progress: {progress:.1f}% - Processing page {page_num}/{start_page + max_pages - 1}")
                
                try:
                    job_urls = await self.extract_job_urls_from_page(page_num)
                    if not job_urls:
                        logger.info("No more job URLs found, stopping.")
                        break
                    
                    # Reset page error counter on successful page
                    page_errors = 0
                    
                    logger.info(f"Processing {len(job_urls)} jobs from page {page_num}")
                    
                    for i, job_url in enumerate(job_urls):
                        if job_url in self.processed_urls:
                            continue
                        self.processed_urls.add(job_url)

                        try:
                            existing = self.collection.get(where={"url": job_url}, limit=1)
                            if existing['ids']:
                                logger.debug(f"Job already in DB, skipping: {job_url}")
                                continue
                        except Exception as e:
                            logger.warning(f"Could not check for existing job: {e}")

                        logger.info(f"Job {i+1}/{len(job_urls)}: Processing {job_url}")
                        content = await self.extract_job_content(job_url)
                        
                        if content:
                            self.store_job_in_chroma(job_url, content)
                            total_stored += 1
                            logger.info(f"Job {i+1}/{len(job_urls)}: Stored successfully")
                        else:
                            self.failed_urls.add(job_url)
                            logger.error(f"Job {i+1}/{len(job_urls)}: Failed to get content")
                        
                        # Periodically clean up page interferences
                        if total_stored % 10 == 0:  # Every 10 jobs
                            await self.cleanup_page_interferences()
                        
                        await asyncio.sleep(DELAY_BETWEEN_JOB_REQUESTS)
                    
                    logger.info(f"Completed page {page_num}, total jobs stored: {total_stored}")
                    await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
                    
                except Exception as e:
                    page_errors += 1
                    logger.error(f"Error processing page {page_num}: {e}")
                    
                    if page_errors >= max_page_errors:
                        logger.error(f"Too many page errors ({page_errors}), stopping scraping.")
                        break
                    
                    # Try to recover browser if there are persistent issues
                    if page_errors >= 2:
                        logger.info("Attempting browser recovery due to persistent errors...")
                        await self._recover_browser()
                        await asyncio.sleep(5)  # Wait longer after recovery
                    
                    continue
                    
        finally:
            if self.browser:
                await self.browser.close()
            logger.info(f"Scraping completed - stored {total_stored} new jobs")
            if self.failed_urls:
                logger.warning(f"Failed URLs: {len(self.failed_urls)}")
            if page_errors > 0:
                logger.warning(f"Page errors encountered: {page_errors}")

async def main():
    parser = argparse.ArgumentParser(description="Jobindex Scraper")
    parser.add_argument("--scrape", action="store_true", help="Start scraping")
    parser.add_argument("--max-pages", type=int, default=100, help="Max pages to scrape")
    parser.add_argument("--start-page", type=int, default=1, help="Page to start from")
    args = parser.parse_args()

    if not OPENAI_API_KEY or "your_openai_api_key_here" in OPENAI_API_KEY:
        logger.error("OpenAI API key is not set. Please set it in your .env file.")
        return

    scraper = JobindexScraper()

    if args.scrape:
        await scraper.scrape_all_jobs(max_pages=args.max_pages, start_page=args.start_page)
    else:
        print("Usage: python jobindex_scraper.py --scrape [--max-pages 10] [--start-page 1]")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user.")