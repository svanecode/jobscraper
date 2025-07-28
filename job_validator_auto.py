#!/usr/bin/env python3
"""
Automated Job Validator - Runs without user interaction for GitHub Actions

This script checks all jobs in the database and marks them as deleted if they're no longer available
on Jobindex (e.g., "Annoncen er udløbet!" - The ad has expired).
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

class AutomatedJobValidator:
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
    
    async def validate_jobs(self, batch_size=20, max_jobs=None):
        """
        Validate all jobs in the database and soft delete expired ones
        
        Args:
            batch_size: Number of jobs to process in parallel
            max_jobs: Maximum number of jobs to check (for testing)
        """
        # Get all active jobs from database
        jobs = self.get_active_jobs(max_jobs)
        
        if not jobs:
            logger.info("No active jobs found in database")
            return {
                'total_checked': 0,
                'total_deleted': 0,
                'total_errors': 0
            }
        
        logger.info(f"Found {len(jobs)} active jobs to validate")
        
        # Process jobs in batches
        total_checked = 0
        total_deleted = 0
        total_errors = 0
        
        # Set start time for progress tracking
        self.start_time = datetime.now()
        
        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            batch_num = i//batch_size + 1
            total_batches = (len(jobs) + batch_size - 1)//batch_size
            
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} jobs)")
            
            # Check jobs in parallel
            results = await asyncio.gather(*[self.check_job_validity(job) for job in batch], return_exceptions=True)
            
            # Process results
            for job, result in zip(batch, results):
                total_checked += 1
                
                if isinstance(result, Exception):
                    logger.error(f"Error checking job {job['job_id']}: {result}")
                    total_errors += 1
                    continue
                
                if not result:  # Job is expired
                    if self.soft_delete_job(job['job_id']):
                        total_deleted += 1
                        logger.info(f"Soft deleted expired job: {job['title']} ({job['job_id']})")
                    else:
                        logger.error(f"Failed to soft delete job: {job['job_id']}")
                else:
                    logger.debug(f"Job still valid: {job['title']} ({job['job_id']})")
            
            # Progress update every 5 batches or at the end
            if batch_num % 5 == 0 or batch_num == total_batches:
                progress = (total_checked / len(jobs)) * 100
                elapsed_time = (datetime.now() - self.start_time).total_seconds()
                jobs_per_second = total_checked / elapsed_time if elapsed_time > 0 else 0
                estimated_remaining = (len(jobs) - total_checked) / jobs_per_second if jobs_per_second > 0 else 0
                
                logger.info(f"Progress: {progress:.1f}% ({total_checked}/{len(jobs)}) - "
                          f"Deleted: {total_deleted}, Errors: {total_errors} - "
                          f"Rate: {jobs_per_second:.1f} jobs/sec - "
                          f"ETA: {estimated_remaining/60:.1f} min")
            
            # Small delay between batches to be respectful
            await asyncio.sleep(0.5)
        
        logger.info(f"Validation complete: {total_checked} jobs checked, {total_deleted} jobs soft deleted, {total_errors} errors")
        return {
            'total_checked': total_checked,
            'total_deleted': total_deleted,
            'total_errors': total_errors
        }
    
    def get_active_jobs(self, max_jobs=None):
        """Get all active (non-deleted) jobs from the database"""
        try:
            # First, get the total count of active jobs
            count_result = self.supabase.table('jobs').select('*', count='exact').is_('deleted_at', 'null').execute()
            total_active = count_result.count or 0
            
            logger.info(f"Found {total_active} total active jobs in database")
            
            if total_active == 0:
                logger.info("No active jobs found in database")
                return []
            
            # If max_jobs is specified and less than total, use it
            if max_jobs and max_jobs < total_active:
                limit = max_jobs
                logger.info(f"Limiting to {limit} jobs for testing")
            else:
                limit = total_active
            
            # Fetch jobs in chunks to handle large datasets
            all_jobs = []
            chunk_size = 1000  # Supabase default limit
            
            for offset in range(0, limit, chunk_size):
                current_chunk_size = min(chunk_size, limit - offset)
                
                query = self.supabase.table('jobs').select('*').is_('deleted_at', 'null').range(offset, offset + current_chunk_size - 1)
                result = query.execute()
                
                if result.data:
                    all_jobs.extend(result.data)
                    logger.info(f"Retrieved chunk {offset//chunk_size + 1}: {len(result.data)} jobs (total: {len(all_jobs)})")
                else:
                    logger.warning(f"No data returned for chunk starting at offset {offset}")
                    break
            
            logger.info(f"Retrieved {len(all_jobs)} active jobs from database")
            return all_jobs
                
        except Exception as e:
            logger.error(f"Error retrieving jobs from database: {e}")
            return []
    
    async def check_job_validity(self, job):
        """
        Check if a job is still valid by visiting its URL
        
        Returns:
            bool: True if job is still valid, False if expired/not found
        """
        job_url = job.get('job_url')
        if not job_url:
            logger.warning(f"No URL for job {job['job_id']}")
            return True  # Keep jobs without URLs to be safe
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            try:
                # Navigate to the job page with shorter timeout
                response = await page.goto(job_url, wait_until='domcontentloaded', timeout=8000)
                
                # Wait for page to load completely
                await page.wait_for_load_state('domcontentloaded', timeout=3000)
                
                # Get the visible text content of the page (not HTML)
                page_text = await page.inner_text('body')
                
                # ONLY check for "Annoncen er udløbet!" - nothing else
                if "Annoncen er udløbet!" in page_text:
                    logger.debug(f"Job {job['job_id']} is expired (found: Annoncen er udløbet!)")
                    await browser.close()
                    return False
                
                # If we reach here, the job is valid (we only check for "Annoncen er udløbet!")
                logger.debug(f"Job {job['job_id']} - no 'Annoncen er udløbet!' found, keeping job")
                await browser.close()
                return True
                
            except Exception as e:
                # For ANY error, keep the job to be safe
                logger.debug(f"Error checking job {job['job_id']}: {e}")
                logger.debug(f"Job {job['job_id']} - error occurred, keeping job to be safe")
                await browser.close()
                return True
    
    def soft_delete_job(self, job_id):
        """Soft delete a job by setting deleted_at timestamp"""
        try:
            result = self.supabase.table('jobs').update({
                'deleted_at': datetime.now().isoformat()
            }).eq('job_id', job_id).execute()
            
            if result.data:
                return True
            else:
                logger.warning(f"No rows updated for job_id: {job_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error soft deleting job {job_id}: {e}")
            return False
    
    def get_deletion_stats(self):
        """Get statistics about deleted jobs"""
        try:
            # Count total jobs
            total_result = self.supabase.table('jobs').select('*', count='exact').execute()
            total_jobs = total_result.count or 0
            
            # Count deleted jobs
            deleted_result = self.supabase.table('jobs').select('*', count='exact').not_.is_('deleted_at', 'null').execute()
            deleted_jobs = deleted_result.count or 0
            
            # Count active jobs
            active_jobs = total_jobs - deleted_jobs
            
            return {
                'total_jobs': total_jobs,
                'active_jobs': active_jobs,
                'deleted_jobs': deleted_jobs,
                'deletion_rate': (deleted_jobs / total_jobs * 100) if total_jobs > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting deletion stats: {e}")
            return None


async def main():
    """Main function to run the automated job validator"""
    print("Automated Jobindex Job Validator")
    print("=" * 50)
    
    try:
        # Initialize validator
        validator = AutomatedJobValidator()
        
        # Show current stats
        stats = validator.get_deletion_stats()
        if stats:
            print(f"\nCurrent Database Stats:")
            print(f"  Total jobs: {stats['total_jobs']}")
            print(f"  Active jobs: {stats['active_jobs']}")
            print(f"  Deleted jobs: {stats['deleted_jobs']}")
            print(f"  Deletion rate: {stats['deletion_rate']:.1f}%")
        
        # Run validation
        print(f"\nStarting job validation...")
        results = await validator.validate_jobs(batch_size=20, max_jobs=None)
        
        if results:
            print(f"\nValidation Results:")
            print(f"  Jobs checked: {results['total_checked']}")
            print(f"  Jobs soft deleted: {results['total_deleted']}")
            print(f"  Errors: {results['total_errors']}")
            
            # Show updated stats
            updated_stats = validator.get_deletion_stats()
            if updated_stats:
                print(f"\nUpdated Database Stats:")
                print(f"  Total jobs: {updated_stats['total_jobs']}")
                print(f"  Active jobs: {updated_stats['active_jobs']}")
                print(f"  Deleted jobs: {updated_stats['deleted_jobs']}")
                print(f"  Deletion rate: {updated_stats['deletion_rate']:.1f}%")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 