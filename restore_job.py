#!/usr/bin/env python3
"""
Restore Job - Restore a soft deleted job for testing purposes
"""

import os
from supabase import create_client, Client

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, continue without it

def restore_job(job_id):
    """Restore a soft deleted job by clearing deleted_at timestamp"""
    try:
        # Initialize Supabase client
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_ANON_KEY')
        
        if not supabase_url or not supabase_key:
            print("❌ Supabase credentials not provided")
            return False
        
        supabase: Client = create_client(supabase_url, supabase_key)
        
        # Restore the job
        result = supabase.table('jobs').update({
            'deleted_at': None
        }).eq('job_id', job_id).execute()
        
        if result.data:
            print(f"✅ Successfully restored job {job_id}")
            return True
        else:
            print(f"❌ Failed to restore job {job_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error restoring job {job_id}: {e}")
        return False

if __name__ == "__main__":
    job_id = "h1570748"
    print(f"🔄 Restoring job: {job_id}")
    restore_job(job_id) 