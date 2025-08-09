#!/usr/bin/env python3
"""
Job Scraper and Cleanup - Combined Script

This script combines job scraping and cleanup into a single workflow:
1. Scrapes new jobs from job websites
2. Updates last_seen for existing jobs found during scraping
3. Cleans up old jobs that haven't been seen recently

This replaces the need for separate scraper and cleanup scripts.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from playwright.async_api import async_playwright
from supabase_rls_config import SupabaseRLSClient

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, continue without it

# Set up logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class JobScraperAndCleanup:
    """
    Combined Job Scraper and Cleanup
    
    Handles both scraping new jobs and cleaning up old ones in a single workflow.
    """
    
    def __init__(self, supabase_url=None, supabase_key=None, cleanup_hours=24):
        """
        Initialize the combined scraper and cleanup utility
        
        Args:
            supabase_url: Supabase URL
            supabase_key: Supabase API key
            cleanup_hours: Hours after which jobs should be cleaned up (default: 24)
        """
        self.base_url = "https://www.jobindex.dk"
        self.search_url = "https://www.jobindex.dk/jobsoegning/kontor"
        self.jobs = []
        self.cleanup_hours = cleanup_hours
        
        # Initialize Supabase client with RLS support
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        
        if self.supabase_url and self.supabase_key:
            # Use RLS-enabled client for better security
            self.supabase = SupabaseRLSClient(
                supabase_url=self.supabase_url,
                supabase_key=self.supabase_key,
                use_service_role=True
            )
            logger.info("✅ Supabase RLS client initialized for combined scraper and cleanup")
        else:
            self.supabase = None
            logger.error("❌ Supabase credentials not provided")
            raise ValueError("Supabase credentials required")
    
    async def scrape_jobs(self):
        """Scrape job listings using Playwright with pagination and duplicate detection"""
        async with async_playwright() as p:
            # Launch browser with better settings
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-background-networking',
                    '--disable-default-apps',
                    '--disable-extensions',
                    '--disable-sync',
                    '--disable-translate',
                    '--hide-scrollbars',
                    '--mute-audio',
                    '--no-first-run',
                    '--safebrowsing-disable-auto-update',
                    '--ignore-certificate-errors',
                    '--ignore-ssl-errors',
                    '--ignore-certificate-errors-spki-list',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-zygote',
                    '--single-process'
                ]
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                },
                record_video_dir=None,
                bypass_csp=True
            )
            page = await context.new_page()

            # Block heavy assets to speed up navigation
            async def route_interceptor(route):
                req = route.request
                if req.resource_type in {"image", "font", "media", "stylesheet"}:
                    return await route.abort()
                return await route.continue_()
            await context.route("**/*", route_interceptor)
            
            try:
                logger.info(f"🔍 Starting job scraping from: {self.search_url}")
                
                # Try multiple navigation strategies
                navigation_success = False
                
                # Strategy 1: Try with domcontentloaded (faster)
                try:
                    logger.info("Attempting navigation with domcontentloaded...")
                    await page.goto(self.search_url, wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_load_state('domcontentloaded', timeout=10000)
                    navigation_success = True
                    logger.info("Navigation successful with domcontentloaded")
                except Exception as e:
                    logger.warning(f"domcontentloaded navigation failed: {e}")
                
                # Strategy 2: Try with load (fallback)
                if not navigation_success:
                    try:
                        logger.info("Attempting navigation with load...")
                        await page.goto(self.search_url, wait_until='load', timeout=45000)
                        await page.wait_for_load_state('load', timeout=10000)
                        navigation_success = True
                        logger.info("Navigation successful with load")
                    except Exception as e:
                        logger.warning(f"load navigation failed: {e}")
                
                # Strategy 3: Try without wait_until (last resort)
                if not navigation_success:
                    try:
                        logger.info("Attempting navigation without wait_until...")
                        await page.goto(self.search_url, timeout=60000)
                        await asyncio.sleep(5)  # Wait longer for page to load
                        navigation_success = True
                        logger.info("Navigation successful without wait_until")
                    except Exception as e:
                        logger.warning(f"navigation without wait_until failed: {e}")
                
                # Strategy 4: Try with networkidle (most reliable for slow connections)
                if not navigation_success:
                    try:
                        logger.info("Attempting navigation with networkidle...")
                        await page.goto(self.search_url, wait_until='networkidle', timeout=90000)
                        await asyncio.sleep(3)
                        navigation_success = True
                        logger.info("Navigation successful with networkidle")
                    except Exception as e:
                        logger.warning(f"networkidle navigation failed: {e}")
                
                if not navigation_success:
                    logger.error("All navigation strategies failed")
                    return False
                
                # Scrape jobs from all available pages
                total_jobs = 0
                page_num = 1
                consecutive_nav_failures = 0
                has_more_pages = True
                max_pages = None  # No limit - scrape all available pages

                # Helper: wait for at least one job selector to appear before parsing
                async def wait_for_any_selector(selectors, timeout_ms=10000):
                    for selector in selectors:
                        try:
                            await page.wait_for_selector(selector, timeout=timeout_ms, state='attached')
                            return True
                        except Exception:
                            continue
                    return False
                
                while has_more_pages and (max_pages is None or page_num <= max_pages):
                    logger.info(f"📄 Scraping page {page_num}")
                    
                    # Ensure content is ready
                    ready = await wait_for_any_selector([
                        '[id^="jobad-wrapper-"]', '.job-listing', '.job-item',
                        '[data-testid="job-listing"]', '.job-card', '.job-ad'
                    ], timeout_ms=15000)

                    # Dismiss cookie banners if present
                    async def try_dismiss_cookies():
                        try:
                            # Common cookie buttons
                            selectors = [
                                'button:has-text("Accepter")',
                                'button:has-text("Acceptér")',
                                'button:has-text("OK")',
                                'text="Accepter alle"',
                            ]
                            for sel in selectors:
                                try:
                                    el = await page.query_selector(sel)
                                    if el:
                                        await el.click()
                                        await asyncio.sleep(0.5)
                                        break
                                except Exception:
                                    continue
                        except Exception:
                            pass

                    await try_dismiss_cookies()

                    # Extract jobs from current page
                    page_jobs = await self.extract_jobs_from_page(page)
                    if page_jobs:
                        self.jobs.extend(page_jobs)
                        total_jobs += len(page_jobs)
                        logger.info(f"Found {len(page_jobs)} jobs on page {page_num}")
                        
                        # Save jobs from this page in real-time
                        logger.info(f"💾 Saving {len(page_jobs)} jobs from page {page_num} to database...")
                        save_success = self.supabase.insert_jobs(page_jobs)
                        if save_success:
                            logger.info(f"✅ Successfully saved {len(page_jobs)} jobs from page {page_num}")
                        else:
                            logger.warning(f"⚠️ Failed to save jobs from page {page_num}")
                    else:
                        logger.warning(f"No jobs found on page {page_num}")
                        break  # No jobs on current page, stop
                    
                    # Try to go to next page using multiple strategies and retries
                    next_url = f"{self.search_url}?page={page_num + 1}"
                    logger.info(f"Attempting to navigate to: {next_url}")

                    navigated = False
                    for attempt in range(3):
                        # Strategy A: normal domcontentloaded
                        try:
                            await page.goto(next_url, wait_until='domcontentloaded', timeout=30000)
                            await try_dismiss_cookies()
                            navigated = True
                            break
                        except Exception as e_a:
                            logger.warning(f"Attempt {attempt + 1}/3: domcontentloaded navigation failed: {e_a}")

                        # Strategy B: no wait_until + manual settle
                        try:
                            await page.goto(next_url, timeout=60000)
                            await asyncio.sleep(3)
                            await try_dismiss_cookies()
                            navigated = True
                            break
                        except Exception as e_b:
                            logger.warning(f"Attempt {attempt + 1}/3: basic navigation failed: {e_b}")

                        # Strategy C: networkidle + short settle
                        try:
                            await page.goto(next_url, wait_until='networkidle', timeout=90000)
                            await asyncio.sleep(2)
                            await try_dismiss_cookies()
                            navigated = True
                            break
                        except Exception as e_c:
                            logger.warning(f"Attempt {attempt + 1}/3: networkidle navigation failed: {e_c}")

                        # Strategy D (last attempt only): try clicking a Next button
                        if attempt == 2:
                            try:
                                next_loc = page.get_by_text("Næste", exact=False)
                                if await next_loc.count() > 0:
                                    await next_loc.first.click()
                                    await page.wait_for_load_state('domcontentloaded', timeout=15000)
                                    await try_dismiss_cookies()
                                    navigated = True
                                    break
                            except Exception as e_d:
                                logger.warning(f"Attempt {attempt + 1}/3: next-button navigation failed: {e_d}")

                        await asyncio.sleep(1)

                    if navigated:
                        page_num += 1
                        logger.info(f"Successfully navigated to page {page_num}")
                        consecutive_nav_failures = 0

                        if max_pages is not None and page_num > max_pages:
                            logger.info(f"Reached maximum page limit ({max_pages}), stopping pagination")
                            has_more_pages = False
                    else:
                        consecutive_nav_failures += 1
                        logger.warning(f"Could not navigate to next page after multiple retries (consecutive failures: {consecutive_nav_failures})")
                        if consecutive_nav_failures >= 3:
                            logger.warning("Max consecutive navigation failures reached; assuming end of pagination")
                            has_more_pages = False
                        else:
                            # Try skipping this page index and attempt the next one
                            page_num += 1
                            logger.info(f"Skipping to page {page_num} and continuing")
                
                logger.info(f"🎉 Scraping completed! Total jobs found: {total_jobs} across {page_num - 1} pages")
                logger.info("⏳ Now proceeding to save jobs and update last_seen...")
                return True
                
            except Exception as e:
                logger.error(f"Error during scraping: {e}")
                return False
            finally:
                await browser.close()
    
    async def extract_jobs_from_page(self, page):
        """Extract job listings from the current page"""
        jobs = []
        
        try:
            # Try multiple selectors to find job listings
            job_selectors = [
                '[id^="jobad-wrapper-"]',
                '.job-listing',
                '.job-item',
                '[data-testid="job-listing"]',
                '.job-card',
                '.job-ad'
            ]
            
            job_elements = []
            for selector in job_selectors:
                job_elements = await page.query_selector_all(selector)
                if job_elements:
                    logger.debug(f"Found {len(job_elements)} jobs using selector: {selector}")
                    break
            
            if not job_elements:
                logger.warning("No job elements found with any selector")
                return []
            
            # Parse each job listing
            for job_element in job_elements:
                try:
                    job_data = await self.parse_job_listing(job_element)
                    if job_data:
                        jobs.append(job_data)
                except Exception as e:
                    logger.debug(f"Error parsing job listing: {e}")
                    continue
            
            return jobs
            
        except Exception as e:
            logger.error(f"Error extracting jobs from page: {e}")
            return []
    
    async def parse_job_listing(self, job_wrapper):
        """Parse a single job listing element"""
        try:
            # Extract job ID from the wrapper
            job_id = None
            try:
                # Try to get job ID from the wrapper's id attribute
                wrapper_id = await job_wrapper.get_attribute('id')
                if wrapper_id and 'jobad-wrapper-' in wrapper_id:
                    job_id = wrapper_id.replace('jobad-wrapper-', '')
                else:
                    # Try to find job ID in a link
                    link_element = await job_wrapper.query_selector('a[href*="/vis-job/"]')
                    if link_element:
                        href = await link_element.get_attribute('href')
                        if href and '/vis-job/' in href:
                            job_id = href.split('/vis-job/')[-1].split('/')[0]
            except Exception as e:
                logger.debug(f"Error extracting job ID: {e}")
            
            if not job_id:
                return None
            
            # Extract job title
            title = None
            try:
                title_element = await job_wrapper.query_selector('h4 a, .job-title a, .title a')
                if title_element:
                    title = await title_element.inner_text()
                    title = title.strip() if title else None
            except Exception as e:
                logger.debug(f"Error extracting title: {e}")
            
            # Extract company name
            company = None
            try:
                company_element = await job_wrapper.query_selector('.jix-toolbar-top__company, .company, .employer, .job-company')
                if company_element:
                    company = await company_element.inner_text()
                    company = company.strip() if company else None
            except Exception as e:
                logger.debug(f"Error extracting company: {e}")
            
            # Extract location
            location = None
            try:
                location_element = await job_wrapper.query_selector('.jix_robotjob--area, .location, .job-location, .place')
                if location_element:
                    location = await location_element.inner_text()
                    location = location.strip() if location else None
            except Exception as e:
                logger.debug(f"Error extracting location: {e}")
            
            # Extract publication date
            publication_date = None
            try:
                date_element = await job_wrapper.query_selector('.date, .job-date, .published')
                if date_element:
                    date_text = await date_element.inner_text()
                    if date_text:
                        # Try to parse the date (this is a simplified version)
                        publication_date = datetime.now().strftime('%Y-%m-%d')
            except Exception as e:
                logger.debug(f"Error extracting publication date: {e}")
            
            # Extract description
            description = None
            try:
                description_element = await job_wrapper.query_selector('.jix_robotjob--description, .description, .job-description, .summary, .job-summary')
                if description_element:
                    description = await description_element.inner_text()
                    description = description.strip() if description else None
            except Exception as e:
                logger.debug(f"Error extracting description: {e}")
            
            # Create job data
            job_data = {
                'job_id': job_id,
                'title': title or 'Unknown Title',
                'company': company,  # Leave as None if unknown
                'location': location,  # Leave as None if unknown
                'publication_date': publication_date or datetime.now().strftime('%Y-%m-%d'),
                'job_url': f"https://www.jobindex.dk/vis-job/{job_id}",
                'company_url': None,  # Will be filled by job_info_scraper if needed
                'description': description,  # Extract description from listing
            }
            
            return job_data
            
        except Exception as e:
            logger.debug(f"Error parsing job listing: {e}")
            return None
    
    def save_jobs_to_supabase(self, table_name='jobs'):
        """Save scraped jobs to Supabase database with RLS compliance"""
        if not self.supabase:
            logger.error("Supabase client not initialized")
            return False
        
        if not self.jobs:
            logger.warning("No jobs to save to Supabase")
            return False
        
        try:
            # Use RLS-enabled client methods (handles duplicates and last_seen updates)
            success = self.supabase.insert_jobs(self.jobs)
            
            if success:
                logger.info(f"✅ Successfully saved {len(self.jobs)} jobs with RLS compliance")
                
                # Restore any previously deleted jobs
                job_ids = [job['job_id'] for job in self.jobs]
                self.supabase.restore_deleted_jobs(job_ids)
                
                return True
            else:
                logger.error("Failed to save jobs with RLS compliance")
                return False
            
        except Exception as e:
            logger.error(f"Error saving to Supabase: {e}")
            return False
    

    

    
    def cleanup_old_jobs(self, batch_size=1000, process_chunk_size=100):
        """Clean up old jobs using RLS-enabled client"""
        try:
            # Use RLS-enabled cleanup function
            deleted_count = self.supabase.cleanup_old_jobs(self.cleanup_hours)
            
            logger.info(f"🧹 RLS cleanup completed: {deleted_count} jobs cleaned up")
            
            return {
                "total_checked": deleted_count,
                "total_deleted": deleted_count,
                "errors": 0
            }
            
        except Exception as e:
            logger.error(f"Error during RLS cleanup: {e}")
            return {
                "total_checked": 0,
                "total_deleted": 0,
                "errors": 1
            }
    
    def get_stats(self):
        """Get comprehensive statistics about the database using RLS-enabled client"""
        try:
            # Use RLS-enabled statistics function
            stats = self.supabase.get_job_statistics()
            
            # Add additional info
            stats.update({
                "cleanup_hours": self.cleanup_hours,
                "scraped_jobs": len(self.jobs)
            })
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {
                "total_jobs": 0,
                "active_jobs": 0,
                "deleted_jobs": 0,
                "jobs_scraped_today": 0,
                "cleanup_hours": self.cleanup_hours,
                "scraped_jobs": len(self.jobs)
            }

async def main():
    """Main function to run the combined scraper and cleanup"""
    try:
        logger.info("🚀 Starting Combined Job Scraper and Cleanup")
        logger.info("=" * 60)
        
        # Initialize the combined utility
        scraper_cleanup = JobScraperAndCleanup()
        
        # Step 1: Scrape jobs
        logger.info("📥 STEP 1: Scraping jobs from job websites")
        scraping_success = await scraper_cleanup.scrape_jobs()
        
        if scraping_success and len(scraper_cleanup.jobs) > 0:
            # Step 2: Clean up old jobs (jobs are already saved in real-time during scraping)
            logger.info("🧹 STEP 2: Cleaning up old jobs")
            cleanup_stats = scraper_cleanup.cleanup_old_jobs()
            
            # Get and display comprehensive statistics
            stats = scraper_cleanup.get_stats()
            logger.info("📊 COMPREHENSIVE STATISTICS:")
            logger.info(f"  Total jobs in database: {stats['total_jobs']}")
            logger.info(f"  Active jobs: {stats['active_jobs']}")
            logger.info(f"  Deleted jobs: {stats['deleted_jobs']}")
            logger.info(f"  Jobs scraped this run: {stats['scraped_jobs']}")
            logger.info(f"  Jobs scraped today: {stats['jobs_scraped_today']}")
            logger.info(f"  Cleanup threshold: {stats['cleanup_hours']} hours")
            logger.info(f"  Jobs deleted this run: {cleanup_stats['total_deleted']}")
            
            logger.info("\n🎉 Combined scraper and cleanup completed successfully!")
        else:
            logger.warning("⚠️ No jobs scraped, skipping cleanup steps")
            if not scraping_success:
                logger.error("❌ Failed to scrape jobs")
        
    except Exception as e:
        logger.error(f"❌ Error in main: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 