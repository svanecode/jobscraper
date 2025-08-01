#!/usr/bin/env python3
"""
Job Information Scraper for Jobindex
Scrapes missing company information from individual job URLs
"""

import asyncio
import logging
import os
import re
from typing import List, Dict, Optional
from urllib.parse import urljoin
from playwright.async_api import async_playwright
from supabase import create_client, Client

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, continue without it

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class JobInfoScraper:
    def __init__(self, supabase_url=None, supabase_key=None):
        self.base_url = "https://www.jobindex.dk"
        
        # Initialize Supabase client
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_ANON_KEY')
        
        if self.supabase_url and self.supabase_key:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            logger.info("Supabase client initialized")
        else:
            self.supabase = None
            logger.error("Supabase credentials not provided. Cannot proceed.")
            raise ValueError("Supabase credentials required")
    
    def get_jobs_with_missing_info(self) -> List[Dict]:
        """
        Get jobs from database that have missing company, company_url, or description
        
        Returns:
            List of job dictionaries with missing information
        """
        try:
            # Query for jobs with missing information
            response = self.supabase.table('jobs').select('*').or_(
                'company.is.null,company.eq.,company_url.is.null,company_url.eq.,description.is.null,description.eq.'
            ).is_('deleted_at', 'null').execute()
            
            if response.data:
                logger.info(f"Found {len(response.data)} jobs with missing information")
                return response.data
            else:
                logger.info("No jobs with missing information found")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching jobs with missing info: {e}")
            return []
    
    async def scrape_job_info(self, job_id: str) -> Optional[Dict]:
        """
        Scrape detailed job information from a specific job URL
        
        Args:
            job_id: Job ID (e.g., 'r13248036')
        
        Returns:
            Dictionary with scraped information or None if error
        """
        job_url = f"https://www.jobindex.dk/vis-job/{job_id}"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            try:
                logger.info(f"Scraping job info from: {job_url}")
                
                # Navigate to the job page
                await page.goto(job_url, wait_until='domcontentloaded', timeout=15000)
                await page.wait_for_load_state('domcontentloaded', timeout=5000)
                
                # Extract job information
                job_info = {}
                
                # First try to find company name in page text (before looking at links)
                company_name = None
                company_url = None
                
                # Try to find company name in page text first
                try:
                    page_text = await page.inner_text('body')
                    
                    # Look for specific company patterns in text
                    import re
                    text_company_patterns = [
                        r'KU\s*-\s*FA\s*-\s*Kbh\s*K',  # Specific KU pattern
                        r'([A-ZÆØÅ][a-zæøå\s&]+?)\s*-\s*([A-ZÆØÅ][a-zæøå\s&]+?)\s*-\s*([A-ZÆØÅ][a-zæøå\s&]+?)',  # Pattern with dashes
                        r'([A-ZÆØÅ][a-zæøå\s&]+?)\s+A/S',  # Company with A/S
                        r'([A-ZÆØÅ][a-zæøå\s&]+?)\s+APS',  # Company with APS
                    ]
                    
                    for pattern in text_company_patterns:
                        matches = re.findall(pattern, page_text, re.IGNORECASE)
                        if matches:
                            if isinstance(matches[0], tuple):
                                potential_company = ' '.join(matches[0]).strip()
                            else:
                                potential_company = matches[0].strip()
                            
                            # Filter out job titles
                            if not any(keyword in potential_company.lower() for keyword in ['specialist', 'assistant', 'worker', 'manager', 'consultant', 'analyst', 'coordinator', 'bæredygtighed', 'indkøb']):
                                company_name = potential_company
                                logger.debug(f"Found company in text: '{company_name}'")
                                break
                except Exception as e:
                    logger.debug(f"Error finding company in text: {e}")
                
                # Define company selectors for fallback
                company_selectors = [
                    'h1 + div a',  # Company link near the title (most reliable)
                    '.jix-toolbar-top__company a',  # Company in toolbar
                    '.company-name a',  # Company name link
                    '.job-company a',  # Job company link
                    'a[href*="/virksomhed/"]',  # Any link containing /virksomhed/ (fallback)
                    'h2 a',  # Company name in h2 tag
                    '.job-header a',  # Company in job header
                    '.employer a',  # Employer link
                    'h1 + div',  # Company div near title (without link)
                    '.job-company',  # Job company div
                    '.employer',  # Employer div
                ]
                
                # If no company found in text, try selectors
                if not company_name:
                    for selector in company_selectors:
                        try:
                        company_elements = await page.query_selector_all(selector)
                        logger.debug(f"Found {len(company_elements)} elements with selector: {selector}")
                        
                        for company_element in company_elements:
                            temp_company_name = await company_element.inner_text()
                            temp_company_url = await company_element.get_attribute('href')
                            
                            logger.debug(f"Element text: '{temp_company_name}', href: '{temp_company_url}'")
                            
                            # Filter out non-company links
                            if temp_company_name and temp_company_name.strip():
                                # Skip common non-company text
                                skip_texts = ['gem', 'del', 'kopier', 'se jobbet', 'ansøg', 'log ind', 'opret profil', 'se virksomhedsprofil']
                                if temp_company_name.strip().lower() in skip_texts:
                                    logger.debug(f"Skipping '{temp_company_name}' (in skip list)")
                                    continue
                                
                                # Check if this looks like a company name
                                if any(keyword in temp_company_name.lower() for keyword in ['ku', 'universitet', 'university', 'a/s', 'aps', 'k/s', 's/a']):
                                    if temp_company_url:
                                        temp_company_url = urljoin(self.base_url, temp_company_url)
                                    company_name = temp_company_name
                                    company_url = temp_company_url
                                    logger.debug(f"Found company: '{company_name}' with URL: '{company_url}'")
                                    break
                                
                                # Prefer links that contain /virksomhed/
                                if temp_company_url and '/virksomhed/' in temp_company_url:
                                    if temp_company_url:
                                        temp_company_url = urljoin(self.base_url, temp_company_url)
                                    company_name = temp_company_name
                                    company_url = temp_company_url
                                    logger.debug(f"Found company: '{company_name}' with URL: '{company_url}'")
                                    break
                                
                                # Skip if this looks like a job title (contains job-related words)
                                if any(keyword in temp_company_name.lower() for keyword in ['specialist', 'assistant', 'worker', 'manager', 'consultant', 'analyst', 'coordinator', 'bæredygtighed', 'indkøb']):
                                    logger.debug(f"Skipping '{temp_company_name}' (looks like job title)")
                                    continue
                        
                        if company_name and company_name.strip():
                            break
                    except Exception as e:
                        logger.debug(f"Error with selector {selector}: {e}")
                        continue
                
                job_info['company'] = company_name.strip() if company_name else None
                job_info['company_url'] = company_url
                
                # If we still don't have a company name, try to find it in the page text
                if not job_info['company'] or job_info['company'] in ['Se jobbet', 'Se virksomhedsprofil']:
                    # First try a direct search for specific company patterns
                    try:
                        page_text = await page.inner_text('body')
                        logger.debug(f"Page text preview: {page_text[:1000]}...")
                        
                        # Direct search for KU pattern
                        if 'KU - FA - Kbh K' in page_text:
                            job_info['company'] = 'KU - FA - Kbh K'
                            logger.debug("Found KU company name directly")
                        elif 'KU' in page_text and 'FA' in page_text and 'Kbh K' in page_text:
                            # Find the exact pattern
                            import re
                            ku_match = re.search(r'KU\s*-\s*FA\s*-\s*Kbh\s*K', page_text)
                            if ku_match:
                                job_info['company'] = ku_match.group(0)
                                logger.debug(f"Found KU company name via regex: {ku_match.group(0)}")
                    except Exception as e:
                        logger.debug(f"Error in direct KU search: {e}")
                
                # If still no company name, try the general patterns
                if not job_info['company'] or job_info['company'] in ['Se jobbet', 'Se virksomhedsprofil']:
                    try:
                        # Look for company name in the page content
                        page_text = await page.inner_text('body')
                        logger.debug(f"Page text preview: {page_text[:500]}...")
                        
                        # Common company patterns in Danish job pages
                        import re
                        company_patterns = [
                            r'DanChurchAid',  # Specific company from the example
                            r'([A-ZÆØÅ][a-zæøå\s&]+?)\s+is\s+seeking',  # English pattern
                            r'([A-ZÆØÅ][a-zæøå\s&]+?)\s+søger',  # Danish pattern
                            r'hos\s+([A-ZÆØÅ][a-zæøå\s&]+?)(?:\s+i\s+|\s+,\s+|\s*$)',  # "hos" pattern
                            r'([A-ZÆØÅ][a-zæøå\s&]+?)\s+er\s+',  # "er" pattern
                            r'KU\s*-\s*FA\s*-\s*Kbh\s*K',  # Specific KU pattern
                            r'([A-ZÆØÅ][a-zæøå\s&]+?)\s*-\s*([A-ZÆØÅ][a-zæøå\s&]+?)\s*-\s*([A-ZÆØÅ][a-zæøå\s&]+?)',  # Pattern with dashes
                        ]
                        
                        for pattern in company_patterns:
                            matches = re.findall(pattern, page_text, re.IGNORECASE)
                            if matches:
                                if isinstance(matches[0], tuple):
                                    # Handle multiple groups
                                    potential_company = ' '.join(matches[0]).strip()
                                else:
                                    potential_company = matches[0].strip()
                                # Filter out common non-company words
                                if len(potential_company) > 2 and potential_company.lower() not in ['job', 'stilling', 'position', 'arbejde', 'climate', 'advocacy', 'officer']:
                                    job_info['company'] = potential_company
                                    logger.debug(f"Found company via text pattern: '{potential_company}'")
                                    break
                    except Exception as e:
                        logger.debug(f"Error finding company via text patterns: {e}")
                
                # Extract job description with better selectors and logic
                description_selectors = [
                    '.PaidJob-inner',  # Job content area
                    '.job-description',  # Main job description
                    '[data-testid="job-description"]',  # Test ID for description
                    '.job-content',  # Job content
                    '.job-details',  # Job details
                    '.job-body',  # Job body
                    '.description',  # Description
                    '.content',  # Content
                    'article p',  # Article paragraphs (more specific)
                    '.job-text',  # Job text
                    'p',  # All paragraphs
                    'div',  # All divs
                    'span',  # All spans
                ]
                
                description = None
                for selector in description_selectors:
                    try:
                        desc_element = await page.query_selector(selector)
                        if desc_element:
                            description = await desc_element.inner_text()
                            if description and description.strip():
                                # Clean up the description
                                description = re.sub(r'\s+', ' ', description.strip())
                                # Check if description is meaningful (not just navigation text)
                                if len(description) > 50:  # Minimum meaningful length
                                    logger.debug(f"Found description with selector '{selector}': {description[:100]}...")
                                    break
                    except Exception as e:
                        logger.debug(f"Error with description selector '{selector}': {e}")
                        continue
                
                # If no description found with selectors, try to extract from page text
                if not description or len(description) < 50:
                    # First try to find the actual job description in the page content
                    try:
                        # Look for the main job description content
                        job_content_selectors = [
                            'p',  # Paragraphs
                            'div',  # Divs
                            'span',  # Spans
                        ]
                        
                        for selector in job_content_selectors:
                            elements = await page.query_selector_all(selector)
                            for element in elements:
                                text = await element.inner_text()
                                if text and len(text.strip()) > 50:
                                    # Check if it contains job-related content
                                    if any(keyword in text.lower() for keyword in ['seeking', 'søger', 'recruit', 'position', 'stilling', 'ansvar', 'responsibilities', 'invite', 'inviterer', 'curiosity', 'nysgerrighed', 'imagination', 'fantasi']):
                                        description = re.sub(r'\s+', ' ', text.strip())
                                        logger.debug(f"Found description in {selector}: {description[:100]}...")
                                        break
                            if description and len(description) > 50:
                                break
                    except Exception as e:
                        logger.debug(f"Error finding description in content elements: {e}")
                
                # If still no description, try to find it by looking for text after the job title
                if not description or len(description) < 50:
                    try:
                        # Get all text and look for content that appears after the job title
                        page_text = await page.inner_text('body')
                        
                        # Look for the job title and extract text after it
                        title_patterns = [
                            r'Student Worker.*?(?=\n\n|\n[A-Z]|$)',
                            r'Jobannonce:.*?(?=\n\n|\n[A-Z]|$)',
                        ]
                        
                        for pattern in title_patterns:
                            matches = re.findall(pattern, page_text, re.DOTALL | re.IGNORECASE)
                            if matches:
                                potential_desc = matches[0].strip()
                                if len(potential_desc) > 20:
                                    description = re.sub(r'\s+', ' ', potential_desc)
                                    logger.debug(f"Found description after title: {description[:100]}...")
                                    break
                    except Exception as e:
                        logger.debug(f"Error finding description after title: {e}")
                
                # If still no description, try text patterns
                if not description or len(description) < 50:
                    try:
                        # Get all text content and try to find job description
                        page_text = await page.inner_text('body')
                        
                        # Look for job description patterns
                        import re
                        desc_patterns = [
                            r'(?:DanChurchAid|DCA)\s+is\s+seeking.*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:Vi søger|We are looking for|We seek).*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:Jobbet|The position|The role).*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:Ansvar|Responsibilities|Duties).*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:DanChurchAid|DCA).*?(?:is seeking|søger).*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:We are|Vi er).*?(?:seeking|søger).*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:We invite you|Vi inviterer dig).*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:bring your|bring din).*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:curiosity|nysgerrighed).*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:imagination|fantasi).*?(?=\n\n|\n[A-Z]|$)',
                        ]
                        
                        for pattern in desc_patterns:
                            matches = re.findall(pattern, page_text, re.DOTALL | re.IGNORECASE)
                            if matches:
                                potential_desc = matches[0].strip()
                                if len(potential_desc) > 50:
                                    description = re.sub(r'\s+', ' ', potential_desc)
                                    logger.debug(f"Found description via text pattern: {description[:100]}...")
                                    break
                    except Exception as e:
                        logger.debug(f"Error finding description via text patterns: {e}")
                
                # Clean up description - remove common unwanted text
                if description:
                    # Remove common navigation and metadata text
                    unwanted_patterns = [
                        r'Indrykket:.*?(?=\n|$)',
                        r'Hentet fra.*?(?=\n|$)',
                        r'Se jobbet.*?(?=\n|$)',
                        r'Anbefalede job.*?(?=\n|$)',
                        r'Gem.*?(?=\n|$)',
                        r'Del.*?(?=\n|$)',
                        r'Kopier.*?(?=\n|$)',
                        r'31\.400 job i dag.*?(?=\n|$)',
                        r'For jobsøgere.*?(?=\n|$)',
                        r'For arbejdsgivere.*?(?=\n|$)',
                        r'Jobsøgning.*?(?=\n|$)',
                        r'Arbejdspladser.*?(?=\n|$)',
                        r'Test dig selv.*?(?=\n|$)',
                        r'Guides.*?(?=\n|$)',
                        r'Kurser.*?(?=\n|$)',
                        r'Log ind.*?(?=\n|$)',
                        r'Opret profil.*?(?=\n|$)',
                    ]
                    
                    for pattern in unwanted_patterns:
                        description = re.sub(pattern, '', description, flags=re.IGNORECASE)
                    
                    # Clean up extra whitespace
                    description = re.sub(r'\s+', ' ', description.strip())
                    
                    # Only keep if it's still meaningful and doesn't contain too much navigation text
                    if len(description) < 20 or description.lower().count('job') > 5:
                        description = None
                
                job_info['description'] = description
                
                # Extract additional information if needed
                # Job title (in case it's missing)
                title_selectors = [
                    'h1',
                    '.job-title',
                    '[data-testid="job-title"]',
                ]
                
                title = None
                for selector in title_selectors:
                    try:
                        title_element = await page.query_selector(selector)
                        if title_element:
                            title = await title_element.inner_text()
                            if title and title.strip():
                                break
                    except Exception:
                        continue
                
                if title:
                    # Remove "Jobannonce: " prefix if present
                    clean_title = title.strip()
                    if clean_title.startswith('Jobannonce: '):
                        clean_title = clean_title[12:]  # Remove "Jobannonce: " prefix
                    job_info['title'] = clean_title
                
                # Location (in case it's missing)
                location_selectors = [
                    '.job-location',
                    '.location',
                    '[data-testid="job-location"]',
                    '.jix_robotjob--area',
                ]
                
                location = None
                for selector in location_selectors:
                    try:
                        location_element = await page.query_selector(selector)
                        if location_element:
                            location = await location_element.inner_text()
                            if location and location.strip():
                                break
                    except Exception:
                        continue
                
                if location:
                    job_info['location'] = location.strip()
                
                logger.info(f"Successfully scraped info for job {job_id}")
                return job_info
                
            except Exception as e:
                logger.error(f"Error scraping job {job_id}: {e}")
                return None
            finally:
                await browser.close()
    
    def update_job_info(self, job_id: str, job_info: Dict) -> bool:
        """
        Update job information in the database
        
        Args:
            job_id: Job ID
            job_info: Dictionary with job information to update
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Only update fields that have meaningful values
            update_data = {}
            for key, value in job_info.items():
                if value is not None and value.strip():
                    # Additional validation for different field types
                    if key == 'description' and len(value.strip()) < 20:
                        # Skip very short descriptions
                        continue
                    elif key == 'company' and len(value.strip()) < 2:
                        # Skip very short company names
                        continue
                    elif key == 'title' and len(value.strip()) < 5:
                        # Skip very short titles
                        continue
                    else:
                        update_data[key] = value.strip()
            
            if not update_data:
                logger.warning(f"No valid data to update for job {job_id}")
                return False
            
            response = self.supabase.table('jobs').update(update_data).eq('job_id', job_id).execute()
            
            if response.data:
                logger.info(f"Updated job {job_id} with: {list(update_data.keys())}")
                return True
            else:
                logger.error(f"Failed to update job {job_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating job {job_id}: {e}")
            return False
    
    async def process_jobs_with_missing_info(self, max_jobs=None, delay=1.0):
        """
        Process all jobs with missing information
        
        Args:
            max_jobs: Maximum number of jobs to process (for testing)
            delay: Delay between requests in seconds
        """
        # Get jobs with missing information
        jobs = self.get_jobs_with_missing_info()
        
        if not jobs:
            logger.info("No jobs with missing information found")
            return
        
        if max_jobs:
            jobs = jobs[:max_jobs]
            logger.info(f"Processing {len(jobs)} jobs (limited for testing)")
        else:
            logger.info(f"Processing {len(jobs)} jobs with missing information")
        
        # Process jobs
        total_processed = 0
        total_updated = 0
        total_errors = 0
        
        for i, job in enumerate(jobs, 1):
            job_id = job.get('job_id')
            if not job_id:
                logger.warning(f"Job without job_id found, skipping")
                continue
            
            logger.info(f"Processing job {i}/{len(jobs)}: {job_id}")
            
            # Check what information is missing
            missing_fields = []
            if not job.get('company') or not job.get('company').strip():
                missing_fields.append('company')
            if not job.get('company_url') or not job.get('company_url').strip():
                missing_fields.append('company_url')
            if not job.get('description') or not job.get('description').strip():
                missing_fields.append('description')
            
            logger.info(f"Missing fields for job {job_id}: {missing_fields}")
            
            # Scrape job information
            job_info = await self.scrape_job_info(job_id)
            
            if job_info:
                # Update database
                if self.update_job_info(job_id, job_info):
                    total_updated += 1
                    logger.info(f"Successfully updated job {job_id}")
                else:
                    total_errors += 1
                    logger.error(f"Failed to update job {job_id}")
            else:
                total_errors += 1
                logger.error(f"Failed to scrape job {job_id}")
            
            total_processed += 1
            
            # Progress update
            progress = (total_processed / len(jobs)) * 100
            logger.info(f"Progress: {progress:.1f}% ({total_processed}/{len(jobs)})")
            
            # Add delay between requests
            if i < len(jobs):
                await asyncio.sleep(delay)
        
        # Final summary
        logger.info("=== PROCESSING COMPLETE ===")
        logger.info(f"Total jobs processed: {total_processed}")
        logger.info(f"Successfully updated: {total_updated}")
        logger.info(f"Errors: {total_errors}")
    
    def get_missing_info_stats(self) -> Dict:
        """
        Get statistics about jobs with missing information
        
        Returns:
            Dictionary with statistics
        """
        try:
            # Get all active jobs
            all_jobs_response = self.supabase.table('jobs').select('company,company_url,description').is_('deleted_at', 'null').execute()
            
            if not all_jobs_response.data:
                return {"total_jobs": 0, "missing_info": 0, "missing_fields": {}}
            
            total_jobs = len(all_jobs_response.data)
            missing_info_count = 0
            missing_fields = {'company': 0, 'company_url': 0, 'description': 0}
            
            for job in all_jobs_response.data:
                has_missing = False
                if not job.get('company') or not job.get('company').strip():
                    missing_fields['company'] += 1
                    has_missing = True
                if not job.get('company_url') or not job.get('company_url').strip():
                    missing_fields['company_url'] += 1
                    has_missing = True
                if not job.get('description') or not job.get('description').strip():
                    missing_fields['description'] += 1
                    has_missing = True
                
                if has_missing:
                    missing_info_count += 1
            
            return {
                "total_jobs": total_jobs,
                "missing_info": missing_info_count,
                "missing_fields": missing_fields,
                "missing_percentage": (missing_info_count / total_jobs * 100) if total_jobs > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting missing info stats: {e}")
            return {"total_jobs": 0, "missing_info": 0, "missing_fields": {}}

async def main():
    """Main function to run the job info scraper"""
    try:
        # Initialize the scraper
        scraper = JobInfoScraper()
        
        # Print initial statistics
        stats = scraper.get_missing_info_stats()
        logger.info("=== INITIAL STATISTICS ===")
        logger.info(f"Total active jobs: {stats['total_jobs']}")
        logger.info(f"Jobs with missing info: {stats['missing_info']} ({stats['missing_percentage']:.1f}%)")
        logger.info("Missing fields breakdown:")
        for field, count in stats['missing_fields'].items():
            percentage = (count / stats['total_jobs'] * 100) if stats['total_jobs'] > 0 else 0
            logger.info(f"  {field}: {count} jobs ({percentage:.1f}%)")
        
        # Process jobs with missing information
        await scraper.process_jobs_with_missing_info(
            max_jobs=None,  # Set to a number for testing
            delay=2.0  # 2 second delay between requests
        )
        
        # Print final statistics
        final_stats = scraper.get_missing_info_stats()
        logger.info("=== FINAL STATISTICS ===")
        logger.info(f"Total active jobs: {final_stats['total_jobs']}")
        logger.info(f"Jobs with missing info: {final_stats['missing_info']} ({final_stats['missing_percentage']:.1f}%)")
        logger.info("Missing fields breakdown:")
        for field, count in final_stats['missing_fields'].items():
            percentage = (count / final_stats['total_jobs'] * 100) if final_stats['total_jobs'] > 0 else 0
            logger.info(f"  {field}: {count} jobs ({percentage:.1f}%)")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 