#!/usr/bin/env python3
"""
Jobindex Scraper using Playwright
Handles JavaScript-rendered content and dynamic loading
"""

import asyncio
import json
import csv
from datetime import datetime
import re
from urllib.parse import urljoin
import logging
import os
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

class JobindexPlaywrightScraper:
    def __init__(self, supabase_url=None, supabase_key=None):
        self.base_url = "https://www.jobindex.dk"
        self.search_url = "https://www.jobindex.dk/jobsoegning/kontor"
        self.jobs = []
        
        # Initialize Supabase client
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_ANON_KEY')
        
        if self.supabase_url and self.supabase_key:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            logger.info("Supabase client initialized")
        else:
            self.supabase = None
            logger.warning("Supabase credentials not provided. Data will only be saved locally.")
    
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
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            try:
                logger.info(f"Navigating to: {self.search_url}")
                
                # Try multiple navigation strategies
                navigation_success = False
                
                # Strategy 1: Try with domcontentloaded (faster)
                try:
                    logger.info("Attempting navigation with domcontentloaded...")
                    await page.goto(self.search_url, wait_until='domcontentloaded', timeout=15000)
                    await page.wait_for_load_state('domcontentloaded', timeout=5000)
                    navigation_success = True
                    logger.info("Navigation successful with domcontentloaded")
                except Exception as e:
                    logger.warning(f"domcontentloaded navigation failed: {e}")
                
                # Strategy 2: Try with load (fallback)
                if not navigation_success:
                    try:
                        logger.info("Attempting navigation with load...")
                        await page.goto(self.search_url, wait_until='load', timeout=20000)
                        await page.wait_for_load_state('load', timeout=5000)
                        navigation_success = True
                        logger.info("Navigation successful with load")
                    except Exception as e:
                        logger.warning(f"load navigation failed: {e}")
                
                # Strategy 3: Try without wait_until (last resort)
                if not navigation_success:
                    try:
                        logger.info("Attempting navigation without wait_until...")
                        await page.goto(self.search_url, timeout=25000)
                        await asyncio.sleep(3)  # Wait a bit for page to load
                        navigation_success = True
                        logger.info("Navigation successful without wait_until")
                    except Exception as e:
                        logger.error(f"All navigation strategies failed: {e}")
                        return []
                
                # Wait for job listings to load with multiple selectors
                job_selectors = [
                    '[id^="jobad-wrapper-"]',
                    '.job-listing',
                    '.job-item',
                    '[data-testid="job-listing"]'
                ]
                
                job_found = False
                for selector in job_selectors:
                    try:
                        logger.info(f"Waiting for job listings with selector: {selector}")
                        await page.wait_for_selector(selector, timeout=10000)
                        job_found = True
                        logger.info(f"Job listings found with selector: {selector}")
                        break
                    except Exception as e:
                        logger.debug(f"Selector {selector} not found: {e}")
                        continue
                
                if not job_found:
                    logger.warning("No job listings found with any selector, but continuing...")
                
                all_jobs = []
                seen_job_ids = set()  # Track seen job IDs to avoid duplicates
                page_num = 1
                total_saved_to_supabase = 0
                
                while True:
                    logger.info(f"Scraping page {page_num}")
                    
                    if page_num > 1:
                        # Try to go to next page using URL parameter
                        try:
                            next_url = f"{self.search_url}?page={page_num}"
                            logger.info(f"Navigating to: {next_url}")
                            
                            # Use the same navigation strategy as initial page
                            await page.goto(next_url, wait_until='domcontentloaded', timeout=15000)
                            await page.wait_for_load_state('domcontentloaded', timeout=5000)
                            
                            # Wait for job listings again
                            job_found = False
                            for selector in job_selectors:
                                try:
                                    await page.wait_for_selector(selector, timeout=10000)
                                    job_found = True
                                    break
                                except Exception:
                                    continue
                            
                            if not job_found:
                                logger.warning(f"No job listings found on page {page_num}, stopping")
                                break
                                
                        except Exception as e:
                            logger.warning(f"Could not navigate to page {page_num}: {e}")
                            break
                    
                    # Extract jobs from current page
                    page_jobs = await self.extract_jobs_from_page(page)
                    
                    if not page_jobs:
                        logger.info(f"No jobs found on page {page_num}, stopping")
                        break
                    
                    # Filter out duplicates
                    new_jobs = []
                    for job in page_jobs:
                        if job['job_id'] not in seen_job_ids:
                            seen_job_ids.add(job['job_id'])
                            new_jobs.append(job)
                        else:
                            logger.debug(f"Skipping duplicate job: {job['job_id']}")
                    
                    if new_jobs:
                        all_jobs.extend(new_jobs)
                        logger.info(f"Found {len(new_jobs)} new jobs on page {page_num} (total unique: {len(all_jobs)})")
                        
                        # Save new jobs to Supabase immediately
                        if self.supabase:
                            new_count, existing_count = self.save_jobs_to_supabase(new_jobs)
                            total_saved_to_supabase += new_count
                            logger.info(f"Page {page_num} results: {new_count} new jobs saved, {existing_count} already existed (total new saved: {total_saved_to_supabase})")
                    else:
                        logger.info(f"No new jobs found on page {page_num}, stopping")
                        break
                    
                    # Small delay between pages
                    await asyncio.sleep(1)
                    page_num += 1
                
                self.jobs = all_jobs
                logger.info(f"Total unique jobs scraped: {len(all_jobs)} from {page_num - 1} pages")
                if self.supabase:
                    logger.info(f"Total NEW jobs saved to Supabase: {total_saved_to_supabase}")
                
            except Exception as e:
                logger.error(f"Error during scraping: {e}")
                # Return any jobs we managed to scrape before the error
                return self.jobs
            finally:
                await browser.close()
        
        return self.jobs
    
    def save_jobs_to_supabase(self, jobs_to_save, table_name='jobs'):
        """Save a batch of jobs to Supabase database with duplicate detection and logging"""
        if not self.supabase:
            logger.error("Supabase client not initialized")
            return 0, 0
        
        if not jobs_to_save:
            return 0, 0
        
        try:
            # Get existing job IDs to check for duplicates
            job_ids = [job['job_id'] for job in jobs_to_save]
            
            # Check which jobs already exist
            existing_jobs_result = self.supabase.table(table_name).select('job_id').in_('job_id', job_ids).execute()
            existing_job_ids = {job['job_id'] for job in existing_jobs_result.data}
            
            # Separate new and existing jobs
            new_jobs = []
            existing_jobs = []
            
            for job in jobs_to_save:
                if job['job_id'] in existing_job_ids:
                    existing_jobs.append(job)
                else:
                    new_jobs.append(job)
            
            # Log the breakdown
            logger.info(f"Batch analysis: {len(new_jobs)} new jobs, {len(existing_jobs)} existing jobs")
            
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
                logger.info(f"Successfully inserted {len(new_jobs)} new jobs to Supabase")
            
            return len(new_jobs), len(existing_jobs)
            
        except Exception as e:
            logger.error(f"Error saving to Supabase: {e}")
            return 0, 0
    
    def save_to_supabase(self, table_name='jobs'):
        """Save all scraped jobs to Supabase database with duplicate detection and logging"""
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
            logger.info(f"Total jobs analysis: {len(new_jobs)} new jobs, {len(existing_jobs)} existing jobs")
            
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
                logger.info(f"Successfully inserted {len(new_jobs)} new jobs to Supabase table '{table_name}'")
            else:
                logger.info("No new jobs to insert - all jobs already exist in database")
            
            # Update last_seen for existing jobs to indicate they were found during scraping
            if existing_jobs:
                self._update_last_seen_for_existing_jobs(existing_jobs)
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving to Supabase: {e}")
            return False
    
    def _update_last_seen_for_existing_jobs(self, existing_jobs):
        """Update last_seen timestamp for existing jobs that were found during scraping"""
        try:
            from datetime import datetime, timezone
            current_time = datetime.now(timezone.utc).isoformat()
            
            # Get job IDs of existing jobs
            job_ids = [job['job_id'] for job in existing_jobs]
            
            # Update last_seen for all existing jobs
            result = self.supabase.table('jobs').update({
                'last_seen': current_time
            }).in_('job_id', job_ids).execute()
            
            logger.info(f"Updated last_seen for {len(existing_jobs)} existing jobs")
            
        except Exception as e:
            logger.error(f"Error updating last_seen for existing jobs: {e}")
    
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
            
            job_wrappers = []
            for selector in job_selectors:
                try:
                    logger.debug(f"Trying selector: {selector}")
                    wrappers = await page.query_selector_all(selector)
                    if wrappers:
                        job_wrappers = wrappers
                        logger.info(f"Found {len(wrappers)} job listings with selector: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not job_wrappers:
                logger.warning("No job wrappers found with any selector")
                return jobs
            
            logger.info(f"Processing {len(job_wrappers)} job listings")
            
            for i, wrapper in enumerate(job_wrappers):
                try:
                    job = await self.parse_job_listing(wrapper)
                    if job:
                        jobs.append(job)
                        logger.debug(f"Successfully parsed job {i+1}/{len(job_wrappers)}: {job.get('title', 'Unknown')}")
                    else:
                        logger.debug(f"Failed to parse job {i+1}/{len(job_wrappers)}")
                except Exception as e:
                    logger.warning(f"Error parsing job {i+1}/{len(job_wrappers)}: {e}")
                    continue
            
            logger.info(f"Successfully extracted {len(jobs)} jobs from page")
            
        except Exception as e:
            logger.error(f"Error extracting jobs from page: {e}")
        
        return jobs
    
    async def parse_job_listing(self, job_wrapper):
        """Parse a single job listing"""
        try:
            job = {}
            
            # Get job ID
            job_id = await job_wrapper.get_attribute('id')
            if job_id:
                job['job_id'] = job_id.replace('jobad-wrapper-', '')
            
            # Extract job title and URL
            title_element = await job_wrapper.query_selector('h4 a')
            if title_element:
                job['title'] = await title_element.inner_text()
                job['job_url'] = await title_element.get_attribute('href')
                if job['job_url']:
                    job['job_url'] = urljoin(self.base_url, job['job_url'])
            else:
                job['title'] = ''
                job['job_url'] = ''
            
            # Extract company name
            company_element = await job_wrapper.query_selector('.jix-toolbar-top__company a')
            if company_element:
                job['company'] = await company_element.inner_text()
                company_url = await company_element.get_attribute('href')
                job['company_url'] = urljoin(self.base_url, company_url) if company_url else ''
            else:
                job['company'] = ''
                job['company_url'] = ''
            
            # Extract location
            location_element = await job_wrapper.query_selector('.jix_robotjob--area')
            if location_element:
                job['location'] = await location_element.inner_text()
            else:
                job['location'] = ''
            
            # Extract publication date
            date_element = await job_wrapper.query_selector('time')
            if date_element:
                job['publication_date'] = await date_element.get_attribute('datetime') or ''
            else:
                job['publication_date'] = ''
            
            # Extract description (simplified)
            desc_elements = await job_wrapper.query_selector_all('.PaidJob-inner p')
            descriptions = []
            for desc_elem in desc_elements[:3]:  # Take first 3 paragraphs
                text = await desc_elem.inner_text()
                if text.strip():
                    descriptions.append(text.strip())
            job['description'] = ' '.join(descriptions)
            
            # Add timestamp
            job['scraped_at'] = datetime.now().isoformat()
            
            return job
            
        except Exception as e:
            logger.error(f"Error parsing job listing: {e}")
            return None
    
    def save_to_json(self, filename=None):
        """Save scraped jobs to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"jobindex_playwright_jobs_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.jobs, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(self.jobs)} jobs to {filename}")
        return filename
    
    def save_to_csv(self, filename=None):
        """Save scraped jobs to CSV file"""
        if not self.jobs:
            logger.warning("No jobs to save")
            return None
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"jobindex_playwright_jobs_{timestamp}.csv"
        
        # Get all possible fields from all jobs
        fieldnames = set()
        for job in self.jobs:
            fieldnames.update(job.keys())
        
        fieldnames = sorted(list(fieldnames))
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.jobs)
        
        logger.info(f"Saved {len(self.jobs)} jobs to {filename}")
        return filename
    
    def print_summary(self):
        """Print a summary of scraped jobs"""
        if not self.jobs:
            print("No jobs scraped")
            return
        
        print(f"\n=== Jobindex Playwright Scraping Summary ===")
        print(f"Total jobs scraped: {len(self.jobs)}")
        
        # If Supabase is available, show database stats
        if self.supabase:
            try:
                # Get total jobs in database
                total_in_db = self.supabase.table('jobs').select('*', count='exact').execute()
                total_count = total_in_db.count if hasattr(total_in_db, 'count') else len(total_in_db.data)
                print(f"Total jobs in database: {total_count}")
                
                # Get active jobs in database
                active_in_db = self.supabase.table('jobs').select('*', count='exact').is_('deleted_at', 'null').execute()
                active_count = active_in_db.count if hasattr(active_in_db, 'count') else len(active_in_db.data)
                print(f"Active jobs in database: {active_count}")
                
            except Exception as e:
                print(f"Could not retrieve database stats: {e}")
        
        # Count by company
        companies = {}
        for job in self.jobs:
            company = job.get('company', 'Unknown')
            companies[company] = companies.get(company, 0) + 1
        
        print(f"\nTop companies:")
        for company, count in sorted(companies.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {company}: {count} jobs")
        
        # Count by location
        locations = {}
        for job in self.jobs:
            location = job.get('location', 'Unknown')
            locations[location] = locations.get(location, 0) + 1
        
        print(f"\nTop locations:")
        for location, count in sorted(locations.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {location}: {count} jobs")
        

        
        # Show some sample job titles
        print(f"\nSample job titles:")
        for i, job in enumerate(self.jobs[:5]):
            print(f"  {i+1}. {job.get('title', 'No title')} - {job.get('company', 'Unknown company')}")


async def main():
    """Main function to run the Playwright scraper"""
    print("Jobindex Playwright Scraper with Supabase Integration")
    print("=" * 60)
    print(f"Target URL: https://www.jobindex.dk/jobsoegning/kontor")
    
    # Initialize scraper with Supabase credentials
    scraper = JobindexPlaywrightScraper()
    
    # Scrape jobs
    jobs = await scraper.scrape_jobs()
    
    if jobs:
        # Jobs are already saved to Supabase during scraping
        if scraper.supabase:
            print("✅ Jobs processed and new ones saved to Supabase during scraping!")

        # Save results locally as backup
        json_file = scraper.save_to_json()
        csv_file = scraper.save_to_csv()
        
        # Print summary
        scraper.print_summary()
        
        print(f"\nResults saved to:")
        if scraper.supabase:
            print(f"  Supabase: jobs table")
        print(f"  JSON: {json_file}")
        print(f"  CSV: {csv_file}")
        
        # Show first job as example
        if jobs:
            print(f"\nExample job data:")
            print(json.dumps(jobs[0], indent=2, ensure_ascii=False))
    else:
        print("No jobs were scraped")


if __name__ == "__main__":
    asyncio.run(main()) 