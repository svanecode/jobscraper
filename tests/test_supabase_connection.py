#!/usr/bin/env python3
"""
Test Supabase Connection
Verifies that the Supabase connection is working before running the main scripts
"""

import os
import sys
from supabase import create_client, Client

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, continue without it

def test_supabase_connection():
    """Test the Supabase connection and basic operations"""
    print("🔍 Testing Supabase Connection...")
    
    # Get credentials from environment
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_ANON_KEY')
    
    # Check if credentials are provided
    if not supabase_url:
        print("❌ Error: SUPABASE_URL environment variable is not set")
        print("   Please set SUPABASE_URL in your .env file or environment")
        return False
        
    if not supabase_key:
        print("❌ Error: SUPABASE_ANON_KEY environment variable is not set")
        print("   Please set SUPABASE_ANON_KEY in your .env file or environment")
        return False
    
    print(f"✅ SUPABASE_URL: {supabase_url}")
    print(f"✅ SUPABASE_ANON_KEY: {supabase_key[:20]}...")
    
    try:
        # Create Supabase client
        print("🔗 Creating Supabase client...")
        supabase: Client = create_client(supabase_url, supabase_key)
        
        # Test basic connection by trying to access the jobs table
        print("🔍 Testing database connection...")
        response = supabase.table('jobs').select('count', count='exact').limit(1).execute()
        
        print("✅ Supabase connection successful!")
        print(f"✅ Jobs table accessible (found {response.count} records)")
        
        # Test if deleted_at column exists
        print("🔍 Checking for deleted_at column...")
        try:
            # Try to query with deleted_at filter
            test_response = supabase.table('jobs').select('job_id').is_('deleted_at', 'null').limit(1).execute()
            print("✅ deleted_at column exists and is working")
        except Exception as e:
            if "column" in str(e).lower() and "deleted_at" in str(e).lower():
                print("⚠️  Warning: deleted_at column may not exist")
                print("   Run the add_deleted_at_column.sql script if needed")
            else:
                print(f"✅ deleted_at column check completed")
        
        return True
        
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        print("\n🔧 Troubleshooting tips:")
        print("1. Check your SUPABASE_URL and SUPABASE_ANON_KEY are correct")
        print("2. Verify your Supabase project is active")
        print("3. Ensure the 'jobs' table exists in your database")
        print("4. Check your network connection")
        return False

def main():
    """Main function to run the connection test"""
    print("=" * 50)
    print("SUPABASE CONNECTION TEST")
    print("=" * 50)
    
    success = test_supabase_connection()
    
    print("=" * 50)
    if success:
        print("✅ CONNECTION TEST PASSED")
        print("   Ready to run scraper and validator scripts")
        sys.exit(0)
    else:
        print("❌ CONNECTION TEST FAILED")
        print("   Please fix the issues above before running scripts")
        sys.exit(1)

if __name__ == "__main__":
    main() 