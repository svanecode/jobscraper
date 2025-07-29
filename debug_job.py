#!/usr/bin/env python3
"""
Debug Job Script - Investigate why a specific job is not being deleted

This script helps debug why a specific job is not being deleted by the validator.
"""

import asyncio
import logging
import os
from datetime import datetime
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

class JobDebugger:
    def __init__(self, supabase_url=None, supabase_key=None):
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
    
    def get_job_info(self, job_id):
        """Get detailed information about a specific job"""
        try:
            result = self.supabase.table('jobs').select('*').eq('job_id', job_id).execute()
            
            if result.data:
                job = result.data[0]
                logger.info(f"=== Job Information for {job_id} ===")
                logger.info(f"Title: {job.get('title', 'N/A')}")
                logger.info(f"Company: {job.get('company', 'N/A')}")
                logger.info(f"Location: {job.get('location', 'N/A')}")
                logger.info(f"Publication Date: {job.get('publication_date', 'N/A')}")
                logger.info(f"Created At: {job.get('created_at', 'N/A')}")
                logger.info(f"Deleted At: {job.get('deleted_at', 'N/A')}")
                logger.info(f"CFO Score: {job.get('cfo_score', 'N/A')}")
                logger.info(f"Scored At: {job.get('scored_at', 'N/A')}")
                logger.info(f"Job URL: {job.get('job_url', 'N/A')}")
                return job
            else:
                logger.error(f"Job {job_id} not found in database")
                return None
                
        except Exception as e:
            logger.error(f"Error getting job info: {e}")
            return None
    
    async def check_job_validity(self, job_id):
        """Check if a job is still valid by visiting its URL"""
        # Construct the Jobindex URL directly from job_id
        job_url = f"https://www.jobindex.dk/vis-job/{job_id}"
        
        logger.info(f"Checking job validity for {job_id}")
        logger.info(f"URL: {job_url}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            try:
                # Navigate to the job page
                logger.info("Navigating to job page...")
                response = await page.goto(job_url, wait_until='domcontentloaded', timeout=10000)
                
                # Wait for page to load completely
                await page.wait_for_load_state('domcontentloaded', timeout=5000)
                
                # Get the page title
                page_title = await page.title()
                logger.info(f"Page title: {page_title}")
                
                # Get the visible text content of the page
                page_text = await page.inner_text('body')
                
                # Check for "Annoncen er udløbet!"
                if "Annoncen er udløbet!" in page_text:
                    logger.info("✅ Job is EXPIRED - found 'Annoncen er udløbet!'")
                    logger.info("This job SHOULD be deleted by the validator")
                    await browser.close()
                    return False
                else:
                    logger.info("❌ Job is NOT expired - no 'Annoncen er udløbet!' found")
                    logger.info("This job should NOT be deleted by the validator")
                    
                    # Show some context around where we might expect to find the text
                    lines = page_text.split('\n')
                    for i, line in enumerate(lines):
                        if 'annonce' in line.lower() or 'udløbet' in line.lower():
                            logger.info(f"Line {i}: {line.strip()}")
                    
                    await browser.close()
                    return True
                
            except Exception as e:
                logger.error(f"Error checking job {job_id}: {e}")
                logger.info("Due to error, job should be kept (validator safety mechanism)")
                await browser.close()
                return True
    
    def check_job_in_validation_queue(self, job_id):
        """Check if the job would be processed by the validator"""
        try:
            # Get the job's publication date
            result = self.supabase.table('jobs').select('publication_date').eq('job_id', job_id).execute()
            
            if not result.data:
                logger.error(f"Job {job_id} not found")
                return False
            
            job_date = result.data[0]['publication_date']
            logger.info(f"Job publication date: {job_date}")
            
            # Check how many jobs are older than this one
            older_jobs_result = self.supabase.table('jobs').select('job_id', count='exact').is_('deleted_at', 'null').lt('publication_date', job_date).execute()
            older_count = older_jobs_result.count if hasattr(older_jobs_result, 'count') else len(older_jobs_result.data)
            
            logger.info(f"Jobs older than {job_id}: {older_count}")
            
            # Check total active jobs
            total_result = self.supabase.table('jobs').select('*', count='exact').is_('deleted_at', 'null').execute()
            total_active = total_result.count if hasattr(total_result, 'count') else len(total_result.data)
            
            logger.info(f"Total active jobs: {total_active}")
            
            # Check if this job would be in the first batch (assuming 20 jobs per batch)
            batch_size = 20
            if older_count < batch_size:
                logger.info(f"✅ Job {job_id} would be processed in first batch (position {older_count + 1})")
                return True
            else:
                logger.info(f"❌ Job {job_id} would NOT be processed in first batch (position {older_count + 1})")
                return False
                
        except Exception as e:
            logger.error(f"Error checking job in validation queue: {e}")
            return False

async def main():
    """Main function to debug a specific job"""
    job_id = "h1570748"  # The job you want to debug
    
    try:
        debugger = JobDebugger()
        
        print(f"🔍 Debugging job: {job_id}")
        print("=" * 50)
        
        # Get job information from database
        job = debugger.get_job_info(job_id)
        if not job:
            return
        
        print()
        
        # Check if job would be processed by validator
        print("📋 Checking if job would be processed by validator...")
        in_queue = debugger.check_job_in_validation_queue(job_id)
        
        print()
        
        # Check job validity
        print("🌐 Checking job validity on Jobindex...")
        is_valid = await debugger.check_job_validity(job_id)
        
        print()
        print("=" * 50)
        print("📊 SUMMARY:")
        print(f"Job ID: {job_id}")
        print(f"In validation queue: {'Yes' if in_queue else 'No'}")
        print(f"Currently valid: {'Yes' if is_valid else 'No'}")
        print(f"Should be deleted: {'No' if is_valid else 'Yes'}")
        
        if not in_queue:
            print("\n💡 REASON: Job is not being processed because it's not in the first batch")
            print("   The validator processes jobs by oldest publication_date first")
        elif is_valid:
            print("\n💡 REASON: Job is still valid (not expired), so it won't be deleted")
        else:
            print("\n💡 REASON: Job should be deleted but isn't - this might be a bug")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 