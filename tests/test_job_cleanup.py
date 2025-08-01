#!/usr/bin/env python3
"""
Test script for the new job cleanup system
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from job_cleanup import JobCleanup
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_cleanup_stats():
    """Test getting cleanup statistics"""
    try:
        cleanup = JobCleanup()
        stats = cleanup.get_cleanup_stats()
        
        print("📊 Cleanup Statistics:")
        print(f"  Total jobs: {stats['total_jobs']}")
        print(f"  Active jobs: {stats['active_jobs']}")
        print(f"  Deleted jobs: {stats['deleted_jobs']}")
        print(f"  Jobs that would be cleaned up next run: {stats['old_jobs_count']}")
        print(f"  Cleanup threshold: {stats['cleanup_hours']} hours")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error testing cleanup stats: {e}")
        return False

def test_old_jobs_query():
    """Test querying for old jobs"""
    try:
        cleanup = JobCleanup()
        old_jobs = cleanup.get_old_jobs()
        
        print(f"🔍 Found {len(old_jobs)} old jobs to clean up")
        
        if old_jobs:
            print("Sample old jobs:")
            for i, job in enumerate(old_jobs[:3]):  # Show first 3
                print(f"  {i+1}. {job.get('title', 'Unknown')} ({job.get('job_id', 'Unknown')})")
                print(f"     Last seen: {job.get('last_seen', 'Unknown')}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error testing old jobs query: {e}")
        return False

def test_cleanup_dry_run():
    """Test cleanup without actually deleting (dry run)"""
    try:
        cleanup = JobCleanup()
        old_jobs = cleanup.get_old_jobs()
        
        if not old_jobs:
            print("ℹ️ No old jobs found to clean up")
            return True
        
        print(f"🧹 Would clean up {len(old_jobs)} jobs:")
        for job in old_jobs[:5]:  # Show first 5
            print(f"  - {job.get('title', 'Unknown')} ({job.get('job_id', 'Unknown')})")
        
        if len(old_jobs) > 5:
            print(f"  ... and {len(old_jobs) - 5} more")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error testing cleanup dry run: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Testing Job Cleanup System")
    print("=" * 50)
    
    tests = [
        ("Cleanup Statistics", test_cleanup_stats),
        ("Old Jobs Query", test_old_jobs_query),
        ("Cleanup Dry Run", test_cleanup_dry_run),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running: {test_name}")
        print("-" * 30)
        
        try:
            if test_func():
                print(f"✅ {test_name}: PASSED")
                passed += 1
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The cleanup system is working correctly.")
    else:
        print("⚠️ Some tests failed. Please check the errors above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 