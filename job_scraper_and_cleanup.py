#!/usr/bin/env python3
"""
Job Scraper and Cleanup - Combined Script

This script combines job scraping and cleanup into a single workflow:
1. Scrapes new jobs from Jobindex
2. Updates last_seen for existing jobs found during scraping
3. Cleans up old jobs that haven't been seen recently

This replaces the need for separate scraper and cleanup scripts.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from supabase import create_client, Client

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
    
    def __init__(self, supabase_url=None, supabase_key=None, cleanup_hours=48):
        """
        Initialize the combined scraper and cleanup utility
        
        Args:
            supabase_url: Supabase URL
            supabase_key: Supabase API key
            cleanup_hours: Hours after which jobs should be cleaned up (default: 48)
        """
        self.base_url = "https://www.jobindex.dk"
        self.search_url = "https://www.jobindex.dk/jobsoegning/kontor"
        self.jobs = []
        self.cleanup_hours = cleanup_hours
        
        # Initialize Supabase client
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_ANON_KEY')
        
        if self.supabase_url and self.supabase_key:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            logger.info("✅ Supabase client initialized for combined scraper and cleanup")
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
                }
            )
            page = await context.new_page()
            
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
                has_more_pages = True
                max_pages = None  # No limit - scrape all available pages
                
                while has_more_pages and (max_pages is None or page_num <= max_pages):
                    logger.info(f"📄 Scraping page {page_num}")
                    
                    # Extract jobs from current page
                    page_jobs = await self.extract_jobs_from_page(page)
                    if page_jobs:
                        self.jobs.extend(page_jobs)
                        total_jobs += len(page_jobs)
                        logger.info(f"Found {len(page_jobs)} jobs on page {page_num}")
                        
                        # Save jobs from this page to database in real-time
                        save_success = self.save_page_jobs_to_supabase(page_jobs)
                        if save_success:
                            logger.info(f"💾 Real-time save: Successfully saved {len(page_jobs)} jobs from page {page_num}")
                        else:
                            logger.warning(f"⚠️ Real-time save: Failed to save jobs from page {page_num}")
                        
                        # Update last_seen for jobs from this page in real-time
                        self._update_last_seen_for_all_jobs(page_jobs)
                        logger.info(f"✅ Updated last_seen for {len(page_jobs)} jobs from page {page_num}")
                    else:
                        logger.warning(f"No jobs found on page {page_num}")
                        break  # No jobs on current page, stop
                    
                    # Try to go to next page using URL parameter
                    try:
                        next_url = f"{self.search_url}?page={page_num + 1}"
                        logger.info(f"Attempting to navigate to: {next_url}")
                        
                        # Navigate to next page with robust timeout
                        await page.goto(next_url, wait_until='domcontentloaded', timeout=30000)
                        await page.wait_for_load_state('domcontentloaded', timeout=10000)
                        
                        # Small delay between pages to be respectful
                        await asyncio.sleep(1)
                        
                        page_num += 1
                        logger.info(f"Successfully navigated to page {page_num}")
                        
                        # Check if we've reached the maximum pages
                        if max_pages is not None and page_num > max_pages:
                            logger.info(f"Reached maximum page limit ({max_pages}), stopping pagination")
                            has_more_pages = False
                            
                    except Exception as e:
                        logger.warning(f"Failed to navigate to page {page_num + 1}: {e}")
                        has_more_pages = False
                
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
                company_element = await job_wrapper.query_selector('.company, .employer, .job-company')
                if company_element:
                    company = await company_element.inner_text()
                    company = company.strip() if company else None
            except Exception as e:
                logger.debug(f"Error extracting company: {e}")
            
            # Extract location
            location = None
            try:
                location_element = await job_wrapper.query_selector('.location, .job-location, .place')
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
            
            # Create job data
            job_data = {
                'job_id': job_id,
                'title': title or 'Unknown Title',
                'company': company or 'Unknown Company',
                'location': location or 'Unknown Location',
                'publication_date': publication_date or datetime.now().strftime('%Y-%m-%d'),
                'job_url': f"https://www.jobindex.dk/vis-job/{job_id}",
                'company_url': None,  # Will be filled by job_info_scraper if needed
                'description': None,  # Will be filled by job_info_scraper if needed
            }
            
            return job_data
            
        except Exception as e:
            logger.debug(f"Error parsing job listing: {e}")
            return None
    
    def save_jobs_to_supabase(self, table_name='jobs'):
        """Save scraped jobs to Supabase database with duplicate detection and last_seen updates"""
        if not self.supabase:
            logger.error("Supabase client not initialized")
            return False
        
        if not self.jobs:
            logger.warning("No jobs to save to Supabase")
            return False
        
        try:
            # Get existing job IDs to check for duplicates
            job_ids = [job['job_id'] for job in self.jobs]
            
            # Check which jobs already exist
            existing_jobs_result = self.supabase.table(table_name).select('job_id').in_('job_id', job_ids).execute()
            existing_job_ids = {job['job_id'] for job in existing_jobs_result.data}
            
            # Separate new and existing jobs
            new_jobs = []
            existing_jobs = []
            
            for job in self.jobs:
                if job['job_id'] in existing_job_ids:
                    existing_jobs.append(job)
                else:
                    new_jobs.append(job)
            
            # Log the breakdown
            logger.info(f"📊 Job analysis: {len(new_jobs)} new jobs, {len(existing_jobs)} existing jobs")
            
            if new_jobs:
                # Prepare data for Supabase (remove scraped_at timestamp as it will be set by database)
                jobs_data = []
                for job in new_jobs:
                    job_data = job.copy()
                    # Remove scraped_at as it will be handled by database
                    job_data.pop('scraped_at', None)
                    jobs_data.append(job_data)
                
                # Insert only new jobs
                result = self.supabase.table(table_name).insert(jobs_data).execute()
                logger.info(f"✅ Successfully inserted {len(new_jobs)} new jobs to Supabase")
            else:
                logger.info("ℹ️ No new jobs to insert - all jobs already exist in database")
            
            # Note: last_seen is already updated in real-time during scraping
            # No need to update again here
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving to Supabase: {e}")
            return False
    
    def save_page_jobs_to_supabase(self, page_jobs, table_name='jobs'):
        """Save jobs from a single page to Supabase in real-time"""
        if not self.supabase:
            logger.error("Supabase client not initialized")
            return False
        
        if not page_jobs:
            logger.warning("No jobs to save from this page")
            return False
        
        try:
            # Get existing job IDs to check for duplicates
            job_ids = [job['job_id'] for job in page_jobs]
            
            # Check which jobs already exist
            existing_jobs_result = self.supabase.table(table_name).select('job_id').in_('job_id', job_ids).execute()
            existing_job_ids = {job['job_id'] for job in existing_jobs_result.data}
            
            # Separate new and existing jobs
            new_jobs = []
            existing_jobs = []
            
            for job in page_jobs:
                if job['job_id'] in existing_job_ids:
                    existing_jobs.append(job)
                else:
                    new_jobs.append(job)
            
            # Log the breakdown for this page
            logger.info(f"📄 Page analysis: {len(new_jobs)} new jobs, {len(existing_jobs)} existing jobs")
            
            if new_jobs:
                # Prepare data for Supabase (remove scraped_at timestamp as it will be set by database)
                jobs_data = []
                for job in new_jobs:
                    job_data = job.copy()
                    # Remove scraped_at as it will be handled by database
                    job_data.pop('scraped_at', None)
                    jobs_data.append(job_data)
                
                # Insert only new jobs from this page
                result = self.supabase.table(table_name).insert(jobs_data).execute()
                logger.info(f"💾 Real-time save: Inserted {len(new_jobs)} new jobs to Supabase")
            else:
                logger.info("ℹ️ No new jobs to insert from this page - all jobs already exist in database")
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving page jobs to Supabase: {e}")
            return False
    
    def _update_last_seen_for_all_jobs(self, jobs):
        """Update last_seen timestamp for ALL jobs found during scraping (new, existing, and soft deleted)"""
        try:
            from datetime import datetime, timezone
            current_time = datetime.now(timezone.utc).isoformat()
            
            # Get job IDs of all jobs found during scraping
            job_ids = [job['job_id'] for job in jobs]
            
            # Update last_seen for ALL jobs (including soft deleted ones)
            result = self.supabase.table('jobs').update({
                'last_seen': current_time
            }).in_('job_id', job_ids).execute()
            
            logger.info(f"🔄 Updated last_seen for {len(jobs)} jobs (including soft deleted)")
            
        except Exception as e:
            logger.error(f"Error updating last_seen for all jobs: {e}")
    
    def get_old_jobs(self):
        """Get jobs that haven't been seen in the specified number of hours"""
        try:
            # Calculate the cutoff time
            cutoff_time = datetime.now() - timedelta(hours=self.cleanup_hours)
            cutoff_iso = cutoff_time.isoformat()
            
            logger.info(f"🔍 Looking for jobs not seen since {cutoff_iso} ({self.cleanup_hours} hours ago)")
            
            # Get jobs that are active (not deleted) and haven't been seen recently
            response = self.supabase.table('jobs').select('*').is_('deleted_at', 'null').lt('last_seen', cutoff_iso).execute()
            
            old_jobs = response.data or []
            logger.info(f"📊 Found {len(old_jobs)} jobs to clean up")
            
            return old_jobs
            
        except Exception as e:
            logger.error(f"❌ Error retrieving old jobs: {e}")
            return []
    
    def soft_delete_job(self, job_id):
        """Soft delete a job by setting deleted_at timestamp"""
        try:
            result = self.supabase.table('jobs').update({
                'deleted_at': datetime.now().isoformat()
            }).eq('job_id', job_id).execute()
            
            if result.data:
                logger.info(f"🗑️ Successfully soft deleted job {job_id}")
                return True
            else:
                logger.error(f"❌ Failed to soft delete job {job_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error soft deleting job {job_id}: {e}")
            return False
    
    def cleanup_old_jobs(self):
        """Clean up old jobs by soft-deleting them"""
        # Get old jobs
        old_jobs = self.get_old_jobs()
        
        if not old_jobs:
            logger.info("ℹ️ No old jobs found to clean up")
            return {
                "total_checked": 0,
                "total_deleted": 0,
                "errors": 0
            }
        
        logger.info(f"🧹 Starting cleanup of {len(old_jobs)} old jobs")
        
        total_deleted = 0
        total_errors = 0
        
        for job in old_jobs:
            job_id = job.get('job_id')
            title = job.get('title', 'Unknown')
            last_seen = job.get('last_seen', 'Unknown')
            
            logger.info(f"🗑️ Cleaning up job: {title} ({job_id}) - Last seen: {last_seen}")
            
            if self.soft_delete_job(job_id):
                total_deleted += 1
            else:
                total_errors += 1
        
        # Final summary
        logger.info("🎉 CLEANUP COMPLETE")
        logger.info(f"📊 Total jobs processed: {len(old_jobs)}")
        logger.info(f"🗑️ Jobs deleted: {total_deleted}")
        logger.info(f"❌ Errors: {total_errors}")
        
        return {
            "total_checked": len(old_jobs),
            "total_deleted": total_deleted,
            "errors": total_errors
        }
    
    def get_stats(self):
        """Get comprehensive statistics about the database"""
        try:
            # Get total jobs
            total_result = self.supabase.table('jobs').select('*', count='exact').execute()
            total_jobs = total_result.count or 0
            
            # Get active jobs
            active_result = self.supabase.table('jobs').select('*', count='exact').is_('deleted_at', 'null').execute()
            active_jobs = active_result.count or 0
            
            # Get deleted jobs
            deleted_result = self.supabase.table('jobs').select('*', count='exact').not_.is_('deleted_at', 'null').execute()
            deleted_jobs = deleted_result.count or 0
            
            # Get jobs that would be cleaned up in next run
            cutoff_time = datetime.now() - timedelta(hours=self.cleanup_hours)
            cutoff_iso = cutoff_time.isoformat()
            old_jobs_result = self.supabase.table('jobs').select('*', count='exact').is_('deleted_at', 'null').lt('last_seen', cutoff_iso).execute()
            old_jobs_count = old_jobs_result.count or 0
            
            return {
                "total_jobs": total_jobs,
                "active_jobs": active_jobs,
                "deleted_jobs": deleted_jobs,
                "old_jobs_count": old_jobs_count,
                "cleanup_hours": self.cleanup_hours,
                "scraped_jobs": len(self.jobs)
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {
                "total_jobs": 0,
                "active_jobs": 0,
                "deleted_jobs": 0,
                "old_jobs_count": 0,
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
        logger.info("📥 STEP 1: Scraping jobs from Jobindex")
        scraping_success = await scraper_cleanup.scrape_jobs()
        
        # Step 2: Clean up old jobs (jobs are now saved in real-time during scraping)
        if len(scraper_cleanup.jobs) > 0:
            logger.info("🧹 STEP 2: Cleaning up old jobs")
            cleanup_stats = scraper_cleanup.cleanup_old_jobs()
            
            # Get and display comprehensive statistics
            stats = scraper_cleanup.get_stats()
            logger.info("📊 COMPREHENSIVE STATISTICS:")
            logger.info(f"  Total jobs in database: {stats['total_jobs']}")
            logger.info(f"  Active jobs: {stats['active_jobs']}")
            logger.info(f"  Deleted jobs: {stats['deleted_jobs']}")
            logger.info(f"  Jobs scraped this run: {stats['scraped_jobs']}")
            logger.info(f"  Jobs that would be cleaned up next run: {stats['old_jobs_count']}")
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