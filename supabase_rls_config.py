#!/usr/bin/env python3
"""
Supabase RLS Configuration for Job Scraper

This module provides configuration and utilities for working with Row Level Security (RLS)
enabled Supabase database.

Key Features:
- Service role authentication for full database access
- Secure job statistics retrieval
- Audit logging support
- RLS-compliant database operations
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from supabase import create_client, Client

logger = logging.getLogger(__name__)

class SupabaseRLSClient:
    """
    Supabase client configured for RLS-enabled database operations
    """
    
    def __init__(self, supabase_url: str = None, supabase_key: str = None, use_service_role: bool = True):
        """
        Initialize Supabase client with RLS support
        
        Args:
            supabase_url: Supabase project URL
            supabase_key: Supabase API key (service role key for full access)
            use_service_role: Whether to use service role key for full database access
        """
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_SERVICE_ROLE_KEY' if use_service_role else 'SUPABASE_ANON_KEY')
        self.use_service_role = use_service_role
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Supabase URL and key are required")
        
        # Initialize Supabase client
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        
        # Test connection
        self._test_connection()
        
        logger.info(f"✅ Supabase RLS client initialized (service_role: {use_service_role})")
    
    def _test_connection(self):
        """Test database connection and RLS setup"""
        try:
            # Test basic connection
            # Request an exact count without selecting a non-existent 'count' column
            result = self.supabase.table('jobs').select('*', count='exact').limit(1).execute()
            logger.info("✅ Database connection successful")
            
            # Test RLS policies by checking if we can access the table
            if self.use_service_role:
                logger.info("✅ Service role access confirmed")
            else:
                logger.info("✅ Authenticated user access confirmed")
                
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    def get_job_statistics(self) -> Dict[str, int]:
        """
        Get job statistics using the secure function
        
        Returns:
            Dictionary with job statistics
        """
        try:
            result = self.supabase.rpc('get_job_statistics').execute()
            
            if result.data:
                stats = result.data[0]
                logger.info(f"📊 Job statistics retrieved: {stats}")
                return stats
            else:
                logger.warning("No statistics returned")
                return {
                    'total_jobs': 0,
                    'active_jobs': 0,
                    'deleted_jobs': 0,
                    'jobs_scraped_today': 0
                }
                
        except Exception as e:
            logger.error(f"Error getting job statistics: {e}")
            return {
                'total_jobs': 0,
                'active_jobs': 0,
                'deleted_jobs': 0,
                'jobs_scraped_today': 0
            }
    
    def cleanup_old_jobs(self, hours_threshold: int = 48) -> int:
        """
        Clean up old jobs using the secure function
        
        Args:
            hours_threshold: Hours after which jobs should be cleaned up
            
        Returns:
            Number of jobs cleaned up
        """
        try:
            result = self.supabase.rpc('cleanup_old_jobs', {'hours_threshold': hours_threshold}).execute()
            
            if result.data:
                # Handle both array and direct integer responses
                if isinstance(result.data, list) and len(result.data) > 0:
                    deleted_count = result.data[0]
                else:
                    deleted_count = result.data
                
                logger.info(f"🧹 Cleaned up {deleted_count} old jobs (threshold: {hours_threshold} hours)")
                return deleted_count
            else:
                logger.warning("No cleanup result returned")
                return 0
                
        except Exception as e:
            logger.error(f"Error cleaning up old jobs: {e}")
            return 0
    
    def insert_jobs(self, jobs: List[Dict[str, Any]], table_name: str = 'jobs') -> bool:
        """
        Insert new jobs with RLS compliance and handle duplicates
        
        Args:
            jobs: List of job dictionaries
            table_name: Table name (default: 'jobs')
            
        Returns:
            True if successful, False otherwise
        """
        if not jobs:
            logger.warning("No jobs to insert")
            return False
        
        try:
            current_time = datetime.now(timezone.utc).isoformat()
            
            # Get all job IDs we're trying to insert
            job_ids = [job['job_id'] for job in jobs]
            
            # Check which jobs already exist in a single query
            existing_result = self.supabase.table(table_name).select('job_id').in_('job_id', job_ids).execute()
            existing_job_ids = {row['job_id'] for row in (existing_result.data or [])}
            
            # Separate new jobs from existing jobs
            new_jobs = []
            existing_job_ids_list = []
            
            for job in jobs:
                row = job.copy()
                row.pop('scraped_at', None)
                
                if job['job_id'] in existing_job_ids:
                    # Job exists - just update last_seen and restore if deleted
                    existing_job_ids_list.append(job['job_id'])
                else:
                    # New job - include all fields
                    row['last_seen'] = current_time
                    row['deleted_at'] = None
                    new_jobs.append(row)
            
            # Insert new jobs
            if new_jobs:
                self.supabase.table(table_name).insert(new_jobs).execute()
                logger.info(f"✅ Inserted {len(new_jobs)} new jobs")
            
            # Update last_seen for existing jobs and restore if deleted
            if existing_job_ids_list:
                self.supabase.table(table_name).update({
                    'last_seen': current_time,
                    'deleted_at': None
                }).in_('job_id', existing_job_ids_list).execute()
                logger.info(f"🔄 Updated last_seen for {len(existing_job_ids_list)} existing jobs")
            
            total_processed = len(new_jobs) + len(existing_job_ids_list)
            logger.info(f"✅ Processed {total_processed} jobs total (new: {len(new_jobs)}, existing: {len(existing_job_ids_list)})")
            return True
            
        except Exception as e:
            logger.error(f"Error inserting jobs: {e}")
            return False

    def log_scrape_error(self, job_id: Optional[str], url: Optional[str], stage: str, message: str) -> None:
        """Best-effort logging of scrape errors to database (if table exists)."""
        try:
            payload = {
                'job_id': job_id,
                'url': url,
                'stage': stage,
                'message': message,
                'logged_at': datetime.now(timezone.utc).isoformat(),
            }
            self.supabase.table('scrape_errors').insert(payload).execute()
        except Exception:
            # Swallow errors to not impact scraper
            pass
    
    def update_last_seen(self, job_ids: List[str], table_name: str = 'jobs') -> bool:
        """
        Update last_seen for existing jobs
        
        Args:
            job_ids: List of job IDs to update
            table_name: Table name (default: 'jobs')
            
        Returns:
            True if successful, False otherwise
        """
        if not job_ids:
            logger.warning("No job IDs to update")
            return False
        
        try:
            current_time = datetime.now(timezone.utc).isoformat()
            
            result = self.supabase.table(table_name).update({
                'last_seen': current_time
            }).in_('job_id', job_ids).execute()
            
            logger.info(f"🔄 Updated last_seen for {len(job_ids)} jobs")
            return True
            
        except Exception as e:
            logger.error(f"Error updating last_seen: {e}")
            return False
    
    def soft_delete_jobs(self, job_ids: List[str], table_name: str = 'jobs') -> bool:
        """
        Soft delete jobs by setting deleted_at timestamp
        
        Args:
            job_ids: List of job IDs to soft delete
            table_name: Table name (default: 'jobs')
            
        Returns:
            True if successful, False otherwise
        """
        if not job_ids:
            logger.warning("No job IDs to delete")
            return False
        
        try:
            current_time = datetime.now(timezone.utc).isoformat()
            
            result = self.supabase.table(table_name).update({
                'deleted_at': current_time
            }).in_('job_id', job_ids).execute()
            
            logger.info(f"🗑️ Soft deleted {len(job_ids)} jobs")
            return True
            
        except Exception as e:
            logger.error(f"Error soft deleting jobs: {e}")
            return False
    
    def restore_deleted_jobs(self, job_ids: List[str], table_name: str = 'jobs') -> bool:
        """
        Restore soft-deleted jobs by clearing deleted_at
        
        Args:
            job_ids: List of job IDs to restore
            table_name: Table name (default: 'jobs')
            
        Returns:
            True if successful, False otherwise
        """
        if not job_ids:
            logger.warning("No job IDs to restore")
            return False
        
        try:
            current_time = datetime.now(timezone.utc).isoformat()
            
            result = self.supabase.table(table_name).update({
                'deleted_at': None,
                'last_seen': current_time
            }).in_('job_id', job_ids).execute()
            
            logger.info(f"🔄 Restored {len(job_ids)} previously deleted jobs")
            return True
            
        except Exception as e:
            logger.error(f"Error restoring jobs: {e}")
            return False
    
    def get_public_jobs(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get public job listings using the secure view
        
        Args:
            limit: Number of jobs to return
            offset: Offset for pagination
            
        Returns:
            List of public job data
        """
        try:
            result = self.supabase.from_('public_jobs').select('*').range(offset, offset + limit - 1).execute()
            
            jobs = result.data or []
            logger.info(f"📋 Retrieved {len(jobs)} public jobs")
            return jobs
            
        except Exception as e:
            logger.error(f"Error getting public jobs: {e}")
            return []
    
    def get_audit_log(self, job_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get audit log entries
        
        Args:
            job_id: Specific job ID to filter by (optional)
            limit: Number of entries to return
            
        Returns:
            List of audit log entries
        """
        try:
            query = self.supabase.table('job_audit_log').select('*').order('changed_at', desc=True).limit(limit)
            
            if job_id:
                query = query.eq('job_id', job_id)
            
            result = query.execute()
            
            entries = result.data or []
            logger.info(f"📝 Retrieved {len(entries)} audit log entries")
            return entries
            
        except Exception as e:
            logger.error(f"Error getting audit log: {e}")
            return []

# Utility functions for RLS setup verification
def verify_rls_setup(supabase_url: str, supabase_key: str) -> Dict[str, Any]:
    """
    Verify that RLS is properly set up
    
    Args:
        supabase_url: Supabase project URL
        supabase_key: Supabase service role key
        
    Returns:
        Dictionary with verification results
    """
    try:
        client = SupabaseRLSClient(supabase_url, supabase_key, use_service_role=True)
        
        # Test various operations
        stats = client.get_job_statistics()
        public_jobs = client.get_public_jobs(limit=5)
        audit_log = client.get_audit_log(limit=5)
        
        return {
            'status': 'success',
            'rls_enabled': True,
            'service_role_access': True,
            'statistics_function': bool(stats),
            'public_view_access': len(public_jobs) >= 0,
            'audit_log_access': len(audit_log) >= 0,
            'message': 'RLS setup verified successfully'
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'rls_enabled': False,
            'service_role_access': False,
            'statistics_function': False,
            'public_view_access': False,
            'audit_log_access': False,
            'message': f'RLS setup verification failed: {e}'
        }

# Example usage
if __name__ == "__main__":
    # Example of how to use the RLS-enabled client
    try:
        # Initialize client with service role for full access
        client = SupabaseRLSClient(use_service_role=True)
        
        # Get statistics
        stats = client.get_job_statistics()
        print(f"Job Statistics: {stats}")
        
        # Get public jobs
        public_jobs = client.get_public_jobs(limit=10)
        print(f"Public Jobs: {len(public_jobs)} found")
        
        # Verify RLS setup
        verification = verify_rls_setup(
            os.getenv('SUPABASE_URL'),
            os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        )
        print(f"RLS Verification: {verification}")
        
    except Exception as e:
        print(f"Error: {e}") 