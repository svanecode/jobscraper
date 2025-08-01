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
        AND have not been processed by job_info scraper (no job_info timestamp)
        Ordered by created_at descending (newest first)
        
        Returns:
            List of job dictionaries with missing information, newest first
        """
        try:
            # Query for jobs with missing information AND no job_info timestamp, ordered by created_at descending
            response = self.supabase.table('jobs').select('*').or_(
                'company.is.null,company.eq.,company_url.is.null,company_url.eq.,description.is.null,description.eq.'
            ).is_('deleted_at', 'null').is_('job_info', 'null').order('created_at', desc=True).execute()
            
            if response.data:
                logger.info(f"Found {len(response.data)} jobs with missing information and no job_info timestamp (ordered by newest first)")
                return response.data
            else:
                logger.info("No jobs with missing information and no job_info timestamp found")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching jobs with missing info: {e}")
            return []
    
    def get_jobs_with_missing_info_limited(self, limit: int = 100) -> List[Dict]:
        """
        Get jobs from database that have missing company, company_url, or description
        AND have not been processed by job_info scraper (no job_info timestamp)
        Limited to the newest N jobs, ordered by created_at descending
        
        Args:
            limit: Maximum number of jobs to return (default: 100)
        
        Returns:
            List of job dictionaries with missing information, newest first
        """
        try:
            # Query for jobs with missing information AND no job_info timestamp, ordered by created_at descending, limited
            response = self.supabase.table('jobs').select('*').or_(
                'company.is.null,company.eq.,company_url.is.null,company_url.eq.,description.is.null,description.eq.'
            ).is_('deleted_at', 'null').is_('job_info', 'null').order('created_at', desc=True).limit(limit).execute()
            
            if response.data:
                logger.info(f"Found {len(response.data)} jobs with missing information and no job_info timestamp (newest {limit}, ordered by newest first)")
                return response.data
            else:
                logger.info("No jobs with missing information and no job_info timestamp found")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching jobs with missing info (limited): {e}")
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
                
                # Extract job title - use proper selectors and clean up
                title = None
                
                # First try the main job title in h4 tag
                try:
                    title_element = await page.query_selector('h4 a')
                    if title_element:
                        title = await title_element.inner_text()
                        if title and title.strip():
                            title = title.strip()
                            logger.debug(f"Found title in h4: '{title}'")
                except Exception as e:
                    logger.debug(f"Error getting title from h4: {e}")
                
                # If no title found, try the sr-only h1 (but clean it up)
                if not title:
                    try:
                        title_element = await page.query_selector('h1.sr-only')
                        if title_element:
                            title = await title_element.inner_text()
                            if title and title.strip():
                                # Remove "Jobannonce: " prefix if present
                                title = title.strip()
                                if title.startswith('Jobannonce: '):
                                    title = title[12:]  # Remove "Jobannonce: " prefix
                                logger.debug(f"Found title in sr-only h1: '{title}'")
                    except Exception as e:
                        logger.debug(f"Error getting title from sr-only h1: {e}")
                
                # If still no title, try the page title
                if not title:
                    try:
                        page_title = await page.title()
                        if page_title and '| Jobindex' in page_title:
                            # Extract title from page title (format: "Title - JobID | Jobindex")
                            title = page_title.split(' - ')[0].strip()
                            logger.debug(f"Found title from page title: '{title}'")
                    except Exception as e:
                        logger.debug(f"Error getting title from page title: {e}")
                
                job_info['title'] = title
                
                # Extract company name - use the proper selector
                company_name = None
                company_url = None
                
                # Try the company div in the toolbar
                try:
                    company_element = await page.query_selector('.jix-toolbar-top__company')
                    if company_element:
                        company_name = await company_element.inner_text()
                        if company_name and company_name.strip():
                            company_name = company_name.strip()
                            logger.debug(f"Found company in toolbar: '{company_name}'")
                except Exception as e:
                    logger.debug(f"Error getting company from toolbar: {e}")
                
                # If no company found, try to find it in the job link
                if not company_name:
                    try:
                        job_link_element = await page.query_selector('h4 a')
                        if job_link_element:
                            href = await job_link_element.get_attribute('href')
                            if href and 'frivilligjob.dk' in href:
                                # This is a volunteer job, extract company from the link or title
                                if title and ' - ' in title:
                                    company_name = title.split(' - ')[-1].strip()
                                    logger.debug(f"Extracted company from title: '{company_name}'")
                    except Exception as e:
                        logger.debug(f"Error extracting company from job link: {e}")
                
                # If still no company, try to find it in the page text
                if not company_name:
                    try:
                        page_text = await page.inner_text('body')
                        
                        # Look for specific company patterns
                        company_patterns = [
                            r'Mental Talk',  # Specific company from the example
                            r'([A-ZÆØÅ][a-zæøå\s&]+?)\s*-\s*([A-ZÆØÅ][a-zæøå\s&]+?)\s*-\s*([A-ZÆØÅ][a-zæøå\s&]+?)',  # Pattern with dashes
                            r'([A-ZÆØÅ][a-zæøå\s&]+?)\s+A/S',  # Company with A/S
                            r'([A-ZÆØÅ][a-zæøå\s&]+?)\s+APS',  # Company with APS
                        ]
                        
                        for pattern in company_patterns:
                            matches = re.findall(pattern, page_text, re.IGNORECASE)
                            if matches:
                                if isinstance(matches[0], tuple):
                                    potential_company = ' '.join(matches[0]).strip()
                                else:
                                    potential_company = matches[0].strip()
                                
                                # Filter out job titles and navigation text
                                if not any(keyword in potential_company.lower() for keyword in ['specialist', 'assistant', 'worker', 'manager', 'consultant', 'analyst', 'coordinator', 'bæredygtighed', 'indkøb', 'gem', 'del', 'kopier']):
                                    company_name = potential_company
                                    logger.debug(f"Found company via text pattern: '{company_name}'")
                                    break
                    except Exception as e:
                        logger.debug(f"Error finding company in text: {e}")
                
                job_info['company'] = company_name
                job_info['company_url'] = company_url
                
                # Extract job description - use the proper selector
                description = None
                
                # Try to find the description in the job content area
                try:
                    # Look for the description paragraph
                    desc_element = await page.query_selector('.jix_robotjob-inner p')
                    if desc_element:
                        description = await desc_element.inner_text()
                        if description and description.strip():
                            description = description.strip()
                            logger.debug(f"Found description in p tag: '{description[:100]}...'")
                except Exception as e:
                    logger.debug(f"Error getting description from p tag: {e}")
                
                # If no description found, try to find it in the job content area
                if not description:
                    try:
                        job_content = await page.query_selector('.jix_robotjob-inner')
                        if job_content:
                            # Get all text from the job content area
                            content_text = await job_content.inner_text()
                            
                            # Look for the actual job description (not metadata)
                            lines = content_text.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and len(line) > 20:
                                    # Skip metadata lines
                                    if any(skip in line.lower() for skip in ['indrykket:', 'hentet fra', 'se jobbet', 'se rejsetid']):
                                        continue
                                    # Skip if it's just the title or company
                                    if line == title or line == company_name:
                                        continue
                                    # This looks like a description
                                    description = line
                                    logger.debug(f"Found description in job content: '{description[:100]}...'")
                                    break
                    except Exception as e:
                        logger.debug(f"Error getting description from job content: {e}")
                
                # If still no description, try to find it in the page text
                if not description:
                    try:
                        page_text = await page.inner_text('body')
                        
                        # Look for job description patterns
                        desc_patterns = [
                            r'At bidrage.*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:Vi søger|We are looking for|We seek).*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:Jobbet|The position|The role).*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:Ansvar|Responsibilities|Duties).*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:We are|Vi er).*?(?:seeking|søger).*?(?=\n\n|\n[A-Z]|$)',
                            r'(?:We invite you|Vi inviterer dig).*?(?=\n\n|\n[A-Z]|$)',
                        ]
                        
                        for pattern in desc_patterns:
                            matches = re.findall(pattern, page_text, re.DOTALL | re.IGNORECASE)
                            if matches:
                                potential_desc = matches[0].strip()
                                if len(potential_desc) > 20:
                                    description = re.sub(r'\s+', ' ', potential_desc)
                                    logger.debug(f"Found description via text pattern: '{description[:100]}...'")
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
                        r'30\.400 job i dag.*?(?=\n|$)',
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
                    
                    # Only keep if it's still meaningful
                    if len(description) < 10:
                        description = None
                
                job_info['description'] = description
                
                # Extract location
                location = None
                try:
                    location_element = await page.query_selector('.jix_robotjob--area')
                    if location_element:
                        location = await location_element.inner_text()
                        if location and location.strip():
                            location = location.strip()
                            logger.debug(f"Found location: '{location}'")
                except Exception as e:
                    logger.debug(f"Error getting location: {e}")
                
                if location:
                    job_info['location'] = location
                
                logger.info(f"Successfully scraped info for job {job_id}")
                logger.info(f"Title: '{job_info.get('title')}'")
                logger.info(f"Company: '{job_info.get('company')}'")
                logger.info(f"Description: '{job_info.get('description', '')[:100]}...'")
                logger.info(f"Location: '{job_info.get('location')}'")
                
                return job_info
                
            except Exception as e:
                logger.error(f"Error scraping job {job_id}: {e}")
                return None
            finally:
                await browser.close()
    
    def update_job_info(self, job_id: str, job_info: Dict) -> bool:
        """
        Update job information in the database and set job_info timestamp
        
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
            
            # Always add the job_info timestamp to mark this job as processed
            from datetime import datetime, timezone
            update_data['job_info'] = datetime.now(timezone.utc).isoformat()
            
            if not update_data:
                logger.warning(f"No valid data to update for job {job_id}")
                return False
            
            response = self.supabase.table('jobs').update(update_data).eq('job_id', job_id).execute()
            
            if response.data:
                logger.info(f"Updated job {job_id} with: {list(update_data.keys())} (including job_info timestamp)")
                return True
            else:
                logger.error(f"Failed to update job {job_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating job {job_id}: {e}")
            return False
    
    async def process_jobs_with_missing_info(self, max_jobs=None, delay=1.0, newest_first=True, limit_newest=None):
        """
        Process jobs with missing information, prioritizing newest jobs
        
        Args:
            max_jobs: Maximum number of jobs to process (for testing)
            delay: Delay between requests in seconds
            newest_first: Whether to prioritize newest jobs (default: True)
            limit_newest: Limit to newest N jobs (default: None, processes all)
        """
        # Get jobs with missing information
        if newest_first and limit_newest:
            # Get only the newest N jobs
            jobs = self.get_jobs_with_missing_info_limited(limit_newest)
        elif newest_first:
            # Get all jobs, but they're already ordered by newest first
            jobs = self.get_jobs_with_missing_info()
        else:
            # Get all jobs without ordering (original behavior)
            jobs = self.get_jobs_with_missing_info()
        
        if not jobs:
            logger.info("No jobs with missing information found")
            return
        
        if max_jobs:
            jobs = jobs[:max_jobs]
            logger.info(f"Processing {len(jobs)} jobs (limited for testing)")
        else:
            if newest_first and limit_newest:
                logger.info(f"Processing {len(jobs)} newest jobs with missing information (limited to {limit_newest})")
            elif newest_first:
                logger.info(f"Processing {len(jobs)} jobs with missing information (newest first)")
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
            
            # Check if job already has job_info timestamp (already processed)
            if job.get('job_info'):
                logger.info(f"Skipping job {job_id} - already processed (job_info timestamp: {job.get('job_info')})")
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
            all_jobs_response = self.supabase.table('jobs').select('company,company_url,description,job_info').is_('deleted_at', 'null').execute()
            
            if not all_jobs_response.data:
                return {"total_jobs": 0, "missing_info": 0, "missing_fields": {}, "processed_by_job_info": 0}
            
            total_jobs = len(all_jobs_response.data)
            missing_info_count = 0
            processed_by_job_info_count = 0
            missing_fields = {'company': 0, 'company_url': 0, 'description': 0}
            
            for job in all_jobs_response.data:
                # Count jobs processed by job_info scraper
                if job.get('job_info'):
                    processed_by_job_info_count += 1
                
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
                "missing_percentage": (missing_info_count / total_jobs * 100) if total_jobs > 0 else 0,
                "processed_by_job_info": processed_by_job_info_count,
                "processed_percentage": (processed_by_job_info_count / total_jobs * 100) if total_jobs > 0 else 0
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
        logger.info(f"Jobs processed by job_info scraper: {stats['processed_by_job_info']} ({stats['processed_percentage']:.1f}%)")
        logger.info("Missing fields breakdown:")
        for field, count in stats['missing_fields'].items():
            percentage = (count / stats['total_jobs'] * 100) if stats['total_jobs'] > 0 else 0
            logger.info(f"  {field}: {count} jobs ({percentage:.1f}%)")
        
        # Process jobs with missing information (prioritizing newest jobs)
        await scraper.process_jobs_with_missing_info(
            max_jobs=None,  # Set to a number for testing
            delay=2.0,  # 2 second delay between requests
            newest_first=True,  # Prioritize newest jobs
            limit_newest=50  # Process only the newest 50 jobs (adjust as needed)
        )
        
        # Print final statistics
        final_stats = scraper.get_missing_info_stats()
        logger.info("=== FINAL STATISTICS ===")
        logger.info(f"Total active jobs: {final_stats['total_jobs']}")
        logger.info(f"Jobs with missing info: {final_stats['missing_info']} ({final_stats['missing_percentage']:.1f}%)")
        logger.info(f"Jobs processed by job_info scraper: {final_stats['processed_by_job_info']} ({final_stats['processed_percentage']:.1f}%)")
        logger.info("Missing fields breakdown:")
        for field, count in final_stats['missing_fields'].items():
            percentage = (count / final_stats['total_jobs'] * 100) if final_stats['total_jobs'] > 0 else 0
            logger.info(f"  {field}: {count} jobs ({percentage:.1f}%)")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 