#!/usr/bin/env python3
"""
GitHub Actions Job Validator V2 - Enhanced for CI environment

This version addresses the timeout issues by:
- Using more realistic browser settings
- Implementing fallback strategies
- Better error handling
- Alternative validation methods
"""

import asyncio
import logging
import os
import sys
import time
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

class GitHubActionsJobValidatorV2:
    """
    GitHub Actions Job Validator V2
    
    This enhanced version:
    - Validates ALL jobs for expiration (no limit)
    - Orders jobs by publication date (oldest first) to check expired jobs first
    - Optimized for CI/CD environments
    """
    def __init__(self, supabase_url=None, supabase_key=None):
        self.base_url = "https://www.jobindex.dk"
        
        # Initialize Supabase client
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_ANON_KEY')
        
        if self.supabase_url and self.supabase_key:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            logger.info("✅ Supabase client initialized for GitHub Actions V2")
        else:
            self.supabase = None
            logger.error("❌ Supabase credentials not provided")
            raise ValueError("Supabase credentials required")
    
    def get_active_jobs(self):
        """Get ALL active (non-deleted) jobs from the database for validation"""
        try:
            # First, get the total count of active jobs
            count_result = self.supabase.table('jobs').select('*', count='exact').is_('deleted_at', 'null').execute()
            total_active = count_result.count or 0
            
            logger.info(f"📊 Found {total_active} total active jobs in database")
            
            if total_active == 0:
                logger.warning("⚠️ No active jobs found in database")
                return []
            
            # Get ALL jobs for validation, ordered by publication date (oldest first to check expired jobs first)
            logger.info("🔍 Fetching ALL jobs for validation, ordered by publication date (oldest first)")
            
            # Query for ALL active jobs, ordered by publication date ascending (oldest first)
            jobs_query = self.supabase.table('jobs').select('*').is_('deleted_at', 'null').order('publication_date')
            jobs_result = jobs_query.execute()
            
            jobs = jobs_result.data or []
            logger.info(f"📥 Found {len(jobs)} jobs for validation (checking ALL jobs)")
            
            return jobs
                
        except Exception as e:
            logger.error(f"❌ Error retrieving jobs from database: {e}")
            return []
    
    async def check_job_validity_robust(self, job):
        """
        Check if a job is still valid with multiple fallback strategies
        
        Returns:
            bool: True if job is still valid, False if expired/not found
        """
        job_id = job.get('job_id')
        if not job_id:
            logger.warning(f"⚠️ No job_id for job")
            return True  # Keep jobs without job_id to be safe
        
        # Construct the Jobindex URL directly from job_id
        job_url = f"https://www.jobindex.dk/vis-job/{job_id}"
        
        # Try multiple strategies
        strategies = [
            self._strategy_1_standard_browser,
            self._strategy_2_minimal_browser,
            self._strategy_3_headless_only,
        ]
        
        for i, strategy in enumerate(strategies, 1):
            try:
                logger.debug(f"🔍 Job {job_id}: Trying strategy {i}")
                result = await strategy(job_url, job_id)
                if result is not None:  # Strategy succeeded
                    return result
            except Exception as e:
                logger.debug(f"⚠️ Job {job_id}: Strategy {i} failed: {e}")
                continue
        
        # If all strategies fail, keep the job to be safe
        logger.warning(f"🛡️ Job {job_id}: All strategies failed, keeping job to be safe")
        return True
    
    async def _strategy_1_standard_browser(self, job_url, job_id):
        """Strategy 1: Standard browser with realistic settings"""
        async with async_playwright() as p:
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
                    '--disable-ipc-flooding-protection',
                    '--disable-hang-monitor',
                    '--disable-prompt-on-repost',
                    '--disable-domain-reliability',
                    '--disable-component-extensions-with-background-pages',
                    '--disable-default-apps',
                    '--disable-sync',
                    '--disable-translate',
                    '--hide-scrollbars',
                    '--mute-audio',
                    '--no-first-run',
                    '--safebrowsing-disable-auto-update',
                    '--disable-client-side-phishing-detection',
                    '--disable-component-update',
                    '--disable-default-apps',
                    '--disable-extensions',
                    '--disable-sync',
                    '--disable-translate',
                    '--no-default-browser-check',
                    '--no-first-run',
                    '--disable-background-networking',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-breakpad',
                    '--disable-component-extensions-with-background-pages',
                    '--disable-features=TranslateUI',
                    '--disable-ipc-flooding-protection',
                    '--disable-renderer-backgrounding',
                    '--disable-sync',
                    '--force-color-profile=srgb',
                    '--metrics-recording-only',
                    '--no-first-run',
                    '--password-store=basic',
                    '--use-mock-keychain',
                ]
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
            page = await context.new_page()
            
            try:
                # Set longer timeout for first strategy
                response = await page.goto(job_url, wait_until='domcontentloaded', timeout=15000)
                
                # Wait for page to load
                await page.wait_for_load_state('domcontentloaded', timeout=5000)
                
                # Get the visible text content
                page_text = await page.inner_text('body')
                
                # Check for "Annoncen er udløbet!"
                if "Annoncen er udløbet!" in page_text:
                    logger.info(f"✅ Job {job_id} is expired (Strategy 1)")
                    await browser.close()
                    return False
                
                # If we reach here, the job is valid
                logger.debug(f"✅ Job {job_id} - valid (Strategy 1)")
                await browser.close()
                return True
                
            except Exception as e:
                await browser.close()
                raise e
    
    async def _strategy_2_minimal_browser(self, job_url, job_id):
        """Strategy 2: Minimal browser with basic settings"""
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
                # Shorter timeout for minimal strategy
                response = await page.goto(job_url, wait_until='domcontentloaded', timeout=10000)
                
                # Wait for page to load
                await page.wait_for_load_state('domcontentloaded', timeout=3000)
                
                # Get the visible text content
                page_text = await page.inner_text('body')
                
                # Check for "Annoncen er udløbet!"
                if "Annoncen er udløbet!" in page_text:
                    logger.info(f"✅ Job {job_id} is expired (Strategy 2)")
                    await browser.close()
                    return False
                
                # If we reach here, the job is valid
                logger.debug(f"✅ Job {job_id} - valid (Strategy 2)")
                await browser.close()
                return True
                
            except Exception as e:
                await browser.close()
                raise e
    
    async def _strategy_3_headless_only(self, job_url, job_id):
        """Strategy 3: Ultra-minimal approach"""
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
                    '--disable-renderer-backgrounding',
                    '--disable-ipc-flooding-protection',
                    '--disable-hang-monitor',
                    '--disable-prompt-on-repost',
                    '--disable-domain-reliability',
                    '--disable-component-extensions-with-background-pages',
                    '--disable-default-apps',
                    '--disable-sync',
                    '--disable-translate',
                    '--hide-scrollbars',
                    '--mute-audio',
                    '--no-first-run',
                    '--safebrowsing-disable-auto-update',
                    '--disable-client-side-phishing-detection',
                    '--disable-component-update',
                    '--disable-default-apps',
                    '--disable-extensions',
                    '--disable-sync',
                    '--disable-translate',
                    '--no-default-browser-check',
                    '--no-first-run',
                    '--disable-background-networking',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-breakpad',
                    '--disable-component-extensions-with-background-pages',
                    '--disable-features=TranslateUI',
                    '--disable-ipc-flooding-protection',
                    '--disable-renderer-backgrounding',
                    '--disable-sync',
                    '--force-color-profile=srgb',
                    '--metrics-recording-only',
                    '--no-first-run',
                    '--password-store=basic',
                    '--use-mock-keychain',
                ]
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1024, 'height': 768}
            )
            page = await context.new_page()
            
            try:
                # Very short timeout for ultra-minimal strategy
                response = await page.goto(job_url, wait_until='domcontentloaded', timeout=8000)
                
                # Wait for page to load
                await page.wait_for_load_state('domcontentloaded', timeout=2000)
                
                # Get the visible text content
                page_text = await page.inner_text('body')
                
                # Check for "Annoncen er udløbet!"
                if "Annoncen er udløbet!" in page_text:
                    logger.info(f"✅ Job {job_id} is expired (Strategy 3)")
                    await browser.close()
                    return False
                
                # If we reach here, the job is valid
                logger.debug(f"✅ Job {job_id} - valid (Strategy 3)")
                await browser.close()
                return True
                
            except Exception as e:
                await browser.close()
                raise e
    
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
    
    async def validate_jobs(self, batch_size=3):
        """
        Validate jobs in the database and soft delete expired ones
        
        Args:
            batch_size: Number of jobs to process in parallel (smaller for CI)
        """
        # Get ALL active jobs from database
        jobs = self.get_active_jobs()
        
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
            results = await asyncio.gather(*[self.check_job_validity_robust(job) for job in batch], return_exceptions=True)
            
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
                await asyncio.sleep(2)
        
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
    """Main function to run the GitHub Actions validator V2"""
    try:
        logger.info("🚀 Starting GitHub Actions Job Validator V2")
        logger.info("=" * 60)
        
        # Initialize the validator
        validator = GitHubActionsJobValidatorV2()
        
        # Run validation with CI-optimized settings (checking ALL jobs)
        logger.info("🔍 Validating job validity (checking for expired jobs)")
        await validator.validate_jobs(
            batch_size=3  # Small batch size for CI
        )
        
        # Get and display validation statistics
        stats = validator.get_deletion_stats()
        logger.info("📊 VALIDATION STATISTICS:")
        logger.info(f"  Total jobs: {stats['total_jobs']}")
        logger.info(f"  Active jobs: {stats['active_jobs']}")
        logger.info(f"  Deleted jobs: {stats['deleted_jobs']}")
        
        logger.info("\n🎉 GitHub Actions Job Validator V2 completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Error in main: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 