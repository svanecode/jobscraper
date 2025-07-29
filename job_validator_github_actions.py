#!/usr/bin/env python3
"""
GitHub Actions Job Validator - Optimized for CI environment

This is a GitHub Actions-specific version of the job validator with:
- Shorter timeouts for CI environment
- Enhanced error handling
- Better logging for CI
- Optimized browser settings
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from playwright.async_api import async_playwright
from supabase import create_client, Client

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, continue without it

# Set up logging for GitHub Actions
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class GitHubActionsJobValidator:
    def __init__(self, supabase_url=None, supabase_key=None):
        self.base_url = "https://www.jobindex.dk"
        
        # Initialize Supabase client
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_ANON_KEY')
        
        if self.supabase_url and self.supabase_key:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            logger.info("✅ Supabase client initialized for GitHub Actions")
        else:
            self.supabase = None
            logger.error("❌ Supabase credentials not provided")
            raise ValueError("Supabase credentials required")
    
    def get_active_jobs(self, max_jobs=None):
        """Get all active (non-deleted) jobs from the database"""
        try:
            # First, get the total count of active jobs
            count_result = self.supabase.table('jobs').select('*', count='exact').is_('deleted_at', 'null').execute()
            total_active = count_result.count or 0
            
            logger.info(f"📊 Found {total_active} total active jobs in database")
            
            if total_active == 0:
                logger.warning("⚠️ No active jobs found in database")
                return []
            
            # If max_jobs is specified and less than total, use it
            if max_jobs and max_jobs < total_active:
                limit = max_jobs
                logger.info(f"🔧 Limiting to {limit} jobs for GitHub Actions testing")
            else:
                limit = total_active
            
            # Fetch jobs in chunks to handle large datasets
            all_jobs = []
            chunk_size = 1000  # Supabase default limit
            
            for offset in range(0, limit, chunk_size):
                current_chunk_size = min(chunk_size, limit - offset)
                
                query = self.supabase.table('jobs').select('*').is_('deleted_at', 'null').order('publication_date', desc=False).range(offset, offset + current_chunk_size - 1)
                result = query.execute()
                
                if result.data:
                    all_jobs.extend(result.data)
                    logger.info(f"📥 Retrieved chunk {offset//chunk_size + 1}: {len(result.data)} jobs (total: {len(all_jobs)})")
                else:
                    logger.warning(f"⚠️ No data returned for chunk starting at offset {offset}")
                    break
            
            logger.info(f"✅ Retrieved {len(all_jobs)} active jobs from database")
            return all_jobs
                
        except Exception as e:
            logger.error(f"❌ Error retrieving jobs from database: {e}")
            return []
    
    async def check_job_validity(self, job):
        """
        Check if a job is still valid by visiting its URL
        
        Returns:
            bool: True if job is still valid, False if expired/not found
        """
        job_id = job.get('job_id')
        if not job_id:
            logger.warning(f"⚠️ No job_id for job")
            return True  # Keep jobs without job_id to be safe
        
        # Construct the Jobindex URL directly from job_id
        job_url = f"https://www.jobindex.dk/vis-job/{job_id}"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-extensions',
                    '--disable-plugins',
                    '--disable-images',
                    '--disable-javascript',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding'
                ]
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            
            try:
                # Navigate to the job page with shorter timeout for CI
                logger.debug(f"🔍 Checking job {job_id}")
                response = await page.goto(job_url, wait_until='domcontentloaded', timeout=5000)
                
                # Wait for page to load completely with shorter timeout
                await page.wait_for_load_state('domcontentloaded', timeout=2000)
                
                # Get the visible text content of the page (not HTML)
                page_text = await page.inner_text('body')
                
                # ONLY check for "Annoncen er udløbet!" - nothing else
                if "Annoncen er udløbet!" in page_text:
                    logger.info(f"✅ Job {job_id} is expired (found: Annoncen er udløbet!)")
                    await browser.close()
                    return False
                
                # If we reach here, the job is valid (we only check for "Annoncen er udløbet!")
                logger.debug(f"✅ Job {job_id} - no 'Annoncen er udløbet!' found, keeping job")
                await browser.close()
                return True
                
            except Exception as e:
                # For ANY error, keep the job to be safe
                logger.warning(f"⚠️ Error checking job {job_id}: {e}")
                logger.info(f"🛡️ Job {job_id} - error occurred, keeping job to be safe")
                await browser.close()
                return True
    
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
    
    async def validate_jobs(self, batch_size=10, max_jobs=None):
        """
        Validate all jobs in the database and soft delete expired ones
        
        Args:
            batch_size: Number of jobs to process in parallel (smaller for CI)
            max_jobs: Maximum number of jobs to check (for testing)
        """
        # Get all active jobs from database
        jobs = self.get_active_jobs(max_jobs)
        
        if not jobs:
            logger.info("ℹ️ No active jobs found in database")
            return
        
        logger.info(f"🚀 Starting validation of {len(jobs)} jobs with batch_size={batch_size}")
        
        # Process jobs in batches
        total_checked = 0
        total_deleted = 0
        total_errors = 0
        
        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            batch_num = i//batch_size + 1
            total_batches = (len(jobs) + batch_size - 1)//batch_size
            
            logger.info(f"📦 Processing batch {batch_num}/{total_batches} ({len(batch)} jobs)")
            
            # Check jobs in parallel
            results = await asyncio.gather(*[self.check_job_validity(job) for job in batch], return_exceptions=True)
            
            # Process results
            for job, result in zip(batch, results):
                total_checked += 1
                
                if isinstance(result, Exception):
                    logger.error(f"❌ Error checking job {job['job_id']}: {result}")
                    total_errors += 1
                    continue
                
                if not result:  # Job is expired
                    if self.soft_delete_job(job['job_id']):
                        total_deleted += 1
                        logger.info(f"🗑️ Soft deleted expired job: {job['title']} ({job['job_id']})")
                    else:
                        logger.error(f"❌ Failed to soft delete job: {job['job_id']}")
                else:
                    logger.debug(f"✅ Job still valid: {job['title']} ({job['job_id']})")
            
            # Progress update every batch for CI
            progress = (total_checked / len(jobs)) * 100
            logger.info(f"📊 Progress: {progress:.1f}% ({total_checked}/{len(jobs)}) - Deleted: {total_deleted}, Errors: {total_errors}")
            
            # Small delay between batches for CI
            if i + batch_size < len(jobs):
                await asyncio.sleep(1)
        
        # Final summary
        logger.info("🎉 VALIDATION COMPLETE")
        logger.info(f"📊 Total jobs processed: {len(jobs)}")
        logger.info(f"✅ Successfully checked: {total_checked}")
        logger.info(f"🗑️ Jobs deleted: {total_deleted}")
        logger.info(f"❌ Errors: {total_errors}")
    
    def get_deletion_stats(self):
        """Get statistics about job deletions"""
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
            
            return {
                "total_jobs": total_jobs,
                "active_jobs": active_jobs,
                "deleted_jobs": deleted_jobs
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting deletion stats: {e}")
            return {"total_jobs": 0, "active_jobs": 0, "deleted_jobs": 0}

async def main():
    """Main function to run the GitHub Actions validator"""
    try:
        logger.info("🚀 Starting GitHub Actions Job Validator")
        logger.info("=" * 50)
        
        # Initialize the validator
        validator = GitHubActionsJobValidator()
        
        # Run validation with CI-optimized settings
        await validator.validate_jobs(
            batch_size=5,  # Smaller batch size for CI
            max_jobs=100   # Limit for testing in CI
        )
        
        # Get and display statistics
        stats = validator.get_deletion_stats()
        logger.info("📊 FINAL STATISTICS:")
        logger.info(f"  Total jobs: {stats['total_jobs']}")
        logger.info(f"  Active jobs: {stats['active_jobs']}")
        logger.info(f"  Deleted jobs: {stats['deleted_jobs']}")
        
    except Exception as e:
        logger.error(f"❌ Error in main: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 