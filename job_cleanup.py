#!/usr/bin/env python3
"""
Job Cleanup Utility - Replaces the job validator

This utility cleans up old jobs based on their last_seen timestamp instead of
visiting each job URL individually. Much more efficient than the previous validator.

Jobs are soft-deleted if they haven't been seen in the last 48 hours.
"""

import logging
import os
import sys
from datetime import datetime, timedelta
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

class JobCleanup:
    """
    Job Cleanup Utility
    
    Replaces the job validator by using last_seen timestamps to identify
    and clean up old jobs that haven't been accessed recently.
    """
    
    def __init__(self, supabase_url=None, supabase_key=None, cleanup_hours=48):
        """
        Initialize the job cleanup utility
        
        Args:
            supabase_url: Supabase URL
            supabase_key: Supabase API key
            cleanup_hours: Hours after which jobs should be cleaned up (default: 48)
        """
        self.cleanup_hours = cleanup_hours
        
        # Initialize Supabase client
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_ANON_KEY')
        
        if self.supabase_url and self.supabase_key:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            logger.info("✅ Supabase client initialized for job cleanup")
        else:
            self.supabase = None
            logger.error("❌ Supabase credentials not provided")
            raise ValueError("Supabase credentials required")
    
    def get_old_jobs(self):
        """
        Get jobs that haven't been seen in the specified number of hours
        
        Returns:
            List of job dictionaries that should be cleaned up
        """
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
        """
        Clean up old jobs by soft-deleting them
        
        Returns:
            dict: Statistics about the cleanup operation
        """
        # Get old jobs
        old_jobs = self.get_old_jobs()
        
        if not old_jobs:
            logger.info("ℹ️ No old jobs found to clean up")
            return {
                "total_checked": 0,
                "total_deleted": 0,
                "errors": 0
            }
        
        logger.info(f"🚀 Starting cleanup of {len(old_jobs)} old jobs")
        
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
    
    def get_cleanup_stats(self):
        """Get statistics about job cleanup and database state"""
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
                "cleanup_hours": self.cleanup_hours
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting cleanup stats: {e}")
            return {
                "total_jobs": 0,
                "active_jobs": 0,
                "deleted_jobs": 0,
                "old_jobs_count": 0,
                "cleanup_hours": self.cleanup_hours
            }

def main():
    """Main function to run the job cleanup"""
    try:
        logger.info("🚀 Starting Job Cleanup Utility")
        logger.info("=" * 60)
        
        # Initialize the cleanup utility
        cleanup = JobCleanup()
        
        # Run cleanup
        logger.info("🔍 Cleaning up old jobs based on last_seen timestamp")
        stats = cleanup.cleanup_old_jobs()
        
        # Get and display cleanup statistics
        db_stats = cleanup.get_cleanup_stats()
        logger.info("📊 CLEANUP STATISTICS:")
        logger.info(f"  Total jobs in database: {db_stats['total_jobs']}")
        logger.info(f"  Active jobs: {db_stats['active_jobs']}")
        logger.info(f"  Deleted jobs: {db_stats['deleted_jobs']}")
        logger.info(f"  Jobs that would be cleaned up next run: {db_stats['old_jobs_count']}")
        logger.info(f"  Cleanup threshold: {db_stats['cleanup_hours']} hours")
        logger.info(f"  Jobs processed this run: {stats['total_checked']}")
        logger.info(f"  Jobs deleted this run: {stats['total_deleted']}")
        logger.info(f"  Errors this run: {stats['errors']}")
        
        logger.info("\n🎉 Job Cleanup Utility completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Error in main: {e}")
        raise

if __name__ == "__main__":
    main() 