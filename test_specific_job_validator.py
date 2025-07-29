#!/usr/bin/env python3
"""
Test Specific Job Validator - Test validation on a specific job

This script tests the validator on a specific job to see what happens during validation.
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
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SpecificJobValidator:
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
    
    def get_specific_job(self, job_id):
        """Get a specific job from the database"""
        try:
            result = self.supabase.table('jobs').select('*').eq('job_id', job_id).is_('deleted_at', 'null').execute()
            
            if result.data:
                job = result.data[0]
                logger.info(f"Found job {job_id}: {job.get('title', 'N/A')}")
                return job
            else:
                logger.error(f"Job {job_id} not found or already deleted")
                return None
                
        except Exception as e:
            logger.error(f"Error getting job: {e}")
            return None
    
    async def check_job_validity(self, job):
        """
        Check if a job is still valid by visiting its URL
        
        Returns:
            bool: True if job is still valid, False if expired/not found
        """
        job_id = job.get('job_id')
        if not job_id:
            logger.warning(f"No job_id for job")
            return True  # Keep jobs without job_id to be safe
        
        # Construct the Jobindex URL directly from job_id
        job_url = f"https://www.jobindex.dk/vis-job/{job_id}"
        
        logger.info(f"Checking job {job_id} at URL: {job_url}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            try:
                # Navigate to the job page with shorter timeout
                logger.info("Navigating to job page...")
                response = await page.goto(job_url, wait_until='domcontentloaded', timeout=8000)
                
                # Wait for page to load completely
                logger.info("Waiting for page to load...")
                await page.wait_for_load_state('domcontentloaded', timeout=3000)
                
                # Get the visible text content of the page (not HTML)
                logger.info("Getting page content...")
                page_text = await page.inner_text('body')
                
                # ONLY check for "Annoncen er udløbet!" - nothing else
                if "Annoncen er udløbet!" in page_text:
                    logger.info(f"Job {job_id} is expired (found: Annoncen er udløbet!)")
                    await browser.close()
                    return False
                
                # If we reach here, the job is valid (we only check for "Annoncen er udløbet!")
                logger.info(f"Job {job_id} - no 'Annoncen er udløbet!' found, keeping job")
                await browser.close()
                return True
                
            except Exception as e:
                # For ANY error, keep the job to be safe
                logger.error(f"Error checking job {job_id}: {e}")
                logger.info(f"Job {job_id} - error occurred, keeping job to be safe")
                await browser.close()
                return True
    
    def soft_delete_job(self, job_id):
        """Soft delete a job by setting deleted_at timestamp"""
        try:
            logger.info(f"Attempting to soft delete job {job_id}...")
            result = self.supabase.table('jobs').update({
                'deleted_at': datetime.now().isoformat()
            }).eq('job_id', job_id).execute()
            
            if result.data:
                logger.info(f"Successfully soft deleted job {job_id}")
                return True
            else:
                logger.error(f"Failed to soft delete job {job_id} - no rows affected")
                return False
                
        except Exception as e:
            logger.error(f"Error soft deleting job {job_id}: {e}")
            return False
    
    async def validate_specific_job(self, job_id):
        """Validate a specific job and delete if expired"""
        logger.info(f"Starting validation for job {job_id}")
        
        # Get the job
        job = self.get_specific_job(job_id)
        if not job:
            logger.error(f"Could not get job {job_id}")
            return False
        
        # Check validity
        is_valid = await self.check_job_validity(job)
        
        if not is_valid:
            logger.info(f"Job {job_id} is expired, attempting to delete...")
            success = self.soft_delete_job(job_id)
            if success:
                logger.info(f"✅ Successfully deleted expired job {job_id}")
                return True
            else:
                logger.error(f"❌ Failed to delete expired job {job_id}")
                return False
        else:
            logger.info(f"Job {job_id} is still valid, keeping it")
            return True

async def main():
    """Main function to test validation on a specific job"""
    job_id = "h1570748"  # The job you want to test
    
    try:
        validator = SpecificJobValidator()
        
        print(f"🧪 Testing validation for job: {job_id}")
        print("=" * 50)
        
        # Run the validation
        result = await validator.validate_specific_job(job_id)
        
        print()
        print("=" * 50)
        print("📊 TEST RESULT:")
        print(f"Job ID: {job_id}")
        print(f"Validation result: {'Success' if result else 'Failed'}")
        
        if result:
            print("✅ Job was processed successfully")
        else:
            print("❌ Job validation failed")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 