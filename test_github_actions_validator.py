#!/usr/bin/env python3
"""
GitHub Actions Validator Test - Debug validator issues in CI environment

This script is specifically designed to test the validator in GitHub Actions
and identify common issues that occur in CI environments.
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

class GitHubActionsValidatorTester:
    def __init__(self, supabase_url=None, supabase_key=None):
        # Initialize Supabase client
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_ANON_KEY')
        
        if self.supabase_url and self.supabase_key:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            logger.info("✅ Supabase client initialized successfully")
        else:
            self.supabase = None
            logger.error("❌ Supabase credentials not provided")
            raise ValueError("Supabase credentials required")
    
    def test_database_connection(self):
        """Test basic database connectivity"""
        try:
            logger.info("🔍 Testing database connection...")
            
            # Test basic query
            result = self.supabase.table('jobs').select('job_id', count='exact').limit(1).execute()
            
            if result.data is not None:
                logger.info("✅ Database connection successful")
                return True
            else:
                logger.error("❌ Database query returned no data")
                return False
                
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            return False
    
    def test_job_retrieval(self):
        """Test retrieving jobs from database"""
        try:
            logger.info("🔍 Testing job retrieval...")
            
            # Get total count of active jobs
            count_result = self.supabase.table('jobs').select('*', count='exact').is_('deleted_at', 'null').execute()
            total_active = count_result.count if hasattr(count_result, 'count') else len(count_result.data)
            
            logger.info(f"📊 Total active jobs in database: {total_active}")
            
            if total_active == 0:
                logger.warning("⚠️ No active jobs found in database")
                return False
            
            # Get oldest jobs
            oldest_jobs = self.supabase.table('jobs').select('job_id,title,publication_date').is_('deleted_at', 'null').order('publication_date', desc=False).limit(5).execute()
            
            if oldest_jobs.data:
                logger.info("✅ Successfully retrieved oldest jobs:")
                for job in oldest_jobs.data:
                    logger.info(f"  - {job['job_id']}: {job['title']} ({job['publication_date']})")
                return True
            else:
                logger.error("❌ Failed to retrieve oldest jobs")
                return False
                
        except Exception as e:
            logger.error(f"❌ Job retrieval failed: {e}")
            return False
    
    async def test_playwright_setup(self):
        """Test Playwright setup in GitHub Actions"""
        try:
            logger.info("🔍 Testing Playwright setup...")
            
            async with async_playwright() as p:
                # Test browser launch
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor'
                    ]
                )
                
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                
                page = await context.new_page()
                
                # Test navigation to a simple page
                await page.goto('https://www.jobindex.dk', wait_until='domcontentloaded', timeout=10000)
                title = await page.title()
                
                logger.info(f"✅ Playwright setup successful - Page title: {title}")
                
                await browser.close()
                return True
                
        except Exception as e:
            logger.error(f"❌ Playwright setup failed: {e}")
            return False
    
    async def test_job_validation_logic(self):
        """Test the actual job validation logic"""
        try:
            logger.info("🔍 Testing job validation logic...")
            
            # Get a few oldest jobs to test
            oldest_jobs = self.supabase.table('jobs').select('job_id,title,publication_date').is_('deleted_at', 'null').order('publication_date', desc=False).limit(3).execute()
            
            if not oldest_jobs.data:
                logger.warning("⚠️ No jobs to test validation with")
                return False
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor'
                    ]
                )
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = await context.new_page()
                
                for job in oldest_jobs.data:
                    job_id = job['job_id']
                    logger.info(f"🔍 Testing job {job_id}: {job['title']}")
                    
                    try:
                        # Construct the Jobindex URL
                        job_url = f"https://www.jobindex.dk/vis-job/{job_id}"
                        
                        # Navigate to the job page
                        response = await page.goto(job_url, wait_until='domcontentloaded', timeout=8000)
                        await page.wait_for_load_state('domcontentloaded', timeout=3000)
                        
                        # Get the visible text content
                        page_text = await page.inner_text('body')
                        
                        # Check for "Annoncen er udløbet!"
                        if "Annoncen er udløbet!" in page_text:
                            logger.info(f"✅ Job {job_id} is EXPIRED - should be deleted")
                        else:
                            logger.info(f"✅ Job {job_id} is VALID - should be kept")
                            
                    except Exception as e:
                        logger.error(f"❌ Error testing job {job_id}: {e}")
                        logger.info(f"⚠️ Job {job_id} - error occurred, should be kept (safety mechanism)")
                
                await browser.close()
                logger.info("✅ Job validation logic test completed")
                return True
                
        except Exception as e:
            logger.error(f"❌ Job validation logic test failed: {e}")
            return False
    
    def test_environment_variables(self):
        """Test environment variables"""
        logger.info("🔍 Testing environment variables...")
        
        required_vars = ['SUPABASE_URL', 'SUPABASE_ANON_KEY']
        optional_vars = ['OPENAI_API_KEY']
        
        all_good = True
        
        for var in required_vars:
            value = os.getenv(var)
            if value:
                logger.info(f"✅ {var}: Configured")
            else:
                logger.error(f"❌ {var}: Not configured")
                all_good = False
        
        for var in optional_vars:
            value = os.getenv(var)
            if value:
                logger.info(f"✅ {var}: Configured")
            else:
                logger.warning(f"⚠️ {var}: Not configured (optional)")
        
        return all_good

async def main():
    """Main function to run all GitHub Actions tests"""
    try:
        print("🧪 GitHub Actions Validator Test")
        print("=" * 50)
        
        # Initialize tester
        tester = GitHubActionsValidatorTester()
        
        # Run all tests
        tests = [
            ("Environment Variables", tester.test_environment_variables),
            ("Database Connection", tester.test_database_connection),
            ("Job Retrieval", tester.test_job_retrieval),
            ("Playwright Setup", tester.test_playwright_setup),
            ("Job Validation Logic", tester.test_job_validation_logic),
        ]
        
        results = []
        
        for test_name, test_func in tests:
            print(f"\n🔍 Running: {test_name}")
            print("-" * 30)
            
            try:
                if asyncio.iscoroutinefunction(test_func):
                    result = await test_func()
                else:
                    result = test_func()
                
                results.append((test_name, result))
                
                if result:
                    print(f"✅ {test_name}: PASSED")
                else:
                    print(f"❌ {test_name}: FAILED")
                    
            except Exception as e:
                print(f"❌ {test_name}: ERROR - {e}")
                results.append((test_name, False))
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 TEST SUMMARY:")
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"  {test_name}: {status}")
        
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed! Validator should work in GitHub Actions")
        else:
            print("⚠️ Some tests failed. Check the logs above for issues")
        
    except Exception as e:
        logger.error(f"❌ Test suite failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 