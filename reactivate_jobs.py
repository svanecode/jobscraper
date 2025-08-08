#!/usr/bin/env python3
"""
Job Reactivation Script

This script reactivates jobs that have been deleted but have a more recent last_seen timestamp.
This can happen when jobs are accidentally deleted or when they should be reactivated.
"""

import logging
import os
from typing import List, Dict
from supabase import create_client, Client
from datetime import datetime, timezone

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, continue without it

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class JobReactivator:
    def __init__(self, supabase_url=None, supabase_key=None):
        # Initialize Supabase client
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY')
        
        if self.supabase_url and self.supabase_key:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            # Log which key type is being used
            if os.getenv('SUPABASE_SERVICE_ROLE_KEY'):
                logger.info("Supabase client initialized with SERVICE_ROLE_KEY (RLS bypass)")
            else:
                logger.info("Supabase client initialized with ANON_KEY")
        else:
            self.supabase = None
            logger.error("Supabase credentials not provided. Cannot proceed.")
            raise ValueError("Supabase credentials required")
    
    def get_jobs_to_reactivate(self, max_jobs=None) -> List[Dict]:
        """
        Get jobs that should be reactivated (last_seen > deleted_at)
        
        Args:
            max_jobs: Maximum number of jobs to fetch (for testing)
        
        Returns:
            List of job dictionaries
        """
        try:
            # Get jobs where last_seen is more recent than deleted_at
            # This means the job was seen after it was deleted, so it should be reactivated
            query = self.supabase.table('jobs').select('*').not_.is_('deleted_at', 'null').not_.is_('last_seen', 'null')
            
            if max_jobs:
                query = query.limit(max_jobs)
            
            response = query.execute()
            
            if not response.data:
                logger.info("No deleted jobs found")
                return []
            
            # Filter jobs where last_seen > deleted_at using proper datetime parsing
            jobs_to_reactivate = []
            def parse_ts(value):
                if not value:
                    return None
                # Handle ISO strings with trailing 'Z'
                if isinstance(value, str) and value.endswith('Z'):
                    value = value.replace('Z', '+00:00')
                try:
                    return datetime.fromisoformat(value)
                except Exception:
                    return None
            for job in response.data:
                deleted_at_raw = job.get('deleted_at')
                last_seen_raw = job.get('last_seen')
                deleted_at = parse_ts(deleted_at_raw)
                last_seen = parse_ts(last_seen_raw)
                if deleted_at and last_seen and last_seen > deleted_at:
                    jobs_to_reactivate.append(job)
            
            if jobs_to_reactivate:
                logger.info(f"Found {len(jobs_to_reactivate)} jobs to reactivate")
            else:
                logger.info("No jobs found that need reactivation")
            
            return jobs_to_reactivate
                
        except Exception as e:
            logger.error(f"Error fetching jobs to reactivate: {e}")
            return []
    
    def reactivate_job(self, job_id: str) -> bool:
        """
        Reactivate a single job by setting deleted_at to null
        
        Args:
            job_id: Job ID to reactivate
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.supabase.table('jobs').update({
                'deleted_at': None
            }).eq('job_id', job_id).execute()
            
            if response.data:
                logger.debug(f"Reactivated job {job_id}")
                return True
            else:
                logger.error(f"Failed to reactivate job {job_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error reactivating job {job_id}: {e}")
            return False
    
    def reactivate_all_jobs(self, max_jobs=None, dry_run=False):
        """
        Reactivate all jobs that should be reactivated
        
        Args:
            max_jobs: Maximum number of jobs to process (for testing)
            dry_run: If True, only show what would be reactivated without making changes
        """
        # Get jobs to reactivate
        jobs = self.get_jobs_to_reactivate(max_jobs)
        
        if not jobs:
            logger.info("No jobs need reactivation")
            return
        
        logger.info(f"Found {len(jobs)} jobs to reactivate")
        
        if dry_run:
            logger.info("=== DRY RUN - NO CHANGES WILL BE MADE ===")
            for job in jobs:
                title = job.get('title', 'N/A')
                company = job.get('company', 'N/A')
                deleted_at = job.get('deleted_at')
                last_seen = job.get('last_seen')
                logger.info(f"Would reactivate: {title} at {company}")
                logger.info(f"  Deleted at: {deleted_at}")
                logger.info(f"  Last seen: {last_seen}")
                logger.info("")
            return
        
        # Reactivate jobs
        total_reactivated = 0
        total_errors = 0
        
        for job in jobs:
            job_id = job.get('job_id')
            title = job.get('title', 'N/A')
            company = job.get('company', 'N/A')
            
            logger.info(f"Reactivating: {title} at {company} ({job_id})")
            
            if self.reactivate_job(job_id):
                total_reactivated += 1
                logger.info(f"✅ Successfully reactivated: {title}")
            else:
                total_errors += 1
                logger.error(f"❌ Failed to reactivate: {title}")
        
        # Final summary
        logger.info("=== REACTIVATION COMPLETE ===")
        logger.info(f"Total jobs processed: {len(jobs)}")
        logger.info(f"Successfully reactivated: {total_reactivated}")
        logger.info(f"Errors: {total_errors}")
    
    def get_reactivation_stats(self) -> Dict:
        """
        Get statistics about jobs that could be reactivated
        
        Returns:
            Dictionary with reactivation statistics
        """
        try:
            # Get all deleted jobs
            deleted_response = self.supabase.table('jobs').select('id', count='exact').not_.is_('deleted_at', 'null').execute()
            total_deleted = deleted_response.count if deleted_response.count is not None else 0
            
            # Get jobs that could be reactivated
            jobs_to_reactivate = self.get_jobs_to_reactivate()
            reactivation_candidates = len(jobs_to_reactivate)
            
            return {
                "total_deleted_jobs": total_deleted,
                "jobs_to_reactivate": reactivation_candidates,
                "reactivation_percentage": (reactivation_candidates / total_deleted * 100) if total_deleted > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting reactivation stats: {e}")
            return {
                "total_deleted_jobs": 0,
                "jobs_to_reactivate": 0,
                "reactivation_percentage": 0
            }

def main():
    """Main function to run the job reactivator"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Reactivate jobs where last_seen > deleted_at')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be reactivated without making changes')
    parser.add_argument('--max-jobs', type=int, default=None, help='Maximum number of jobs to process')
    parser.add_argument('--stats-only', action='store_true', help='Only show statistics, do not reactivate')
    
    args = parser.parse_args()
    
    try:
        # Initialize the reactivator
        reactivator = JobReactivator()
        
        if args.stats_only:
            # Show statistics only
            stats = reactivator.get_reactivation_stats()
            logger.info("=== REACTIVATION STATISTICS ===")
            logger.info(f"Total deleted jobs: {stats['total_deleted_jobs']}")
            logger.info(f"Jobs to reactivate: {stats['jobs_to_reactivate']}")
            logger.info(f"Reactivation percentage: {stats['reactivation_percentage']:.1f}%")
        else:
            # Reactivate jobs
            reactivator.reactivate_all_jobs(
                max_jobs=args.max_jobs,
                dry_run=args.dry_run
            )
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    main() 