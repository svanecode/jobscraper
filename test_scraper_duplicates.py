#!/usr/bin/env python3
"""
Test Scraper Duplicate Detection

This script tests the new duplicate detection functionality in the scraper
to ensure it properly identifies and logs new vs existing jobs.
"""

import asyncio
import logging
from playwright_scraper import JobindexPlaywrightScraper

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_duplicate_detection():
    """Test the duplicate detection functionality"""
    try:
        print("Testing scraper duplicate detection...")
        print("=" * 50)
        
        # Initialize scraper
        scraper = JobindexPlaywrightScraper()
        
        if not scraper.supabase:
            print("❌ Supabase not configured. Please set up environment variables.")
            return
        
        # Test with a small number of pages
        print("Running scraper with duplicate detection...")
        print("This will show how many jobs are new vs existing in the database.")
        print()
        
        # Modify the scraper to only process 2 pages for testing
        original_scrape_jobs = scraper.scrape_jobs
        
        async def test_scrape_jobs():
            """Modified scrape method for testing"""
            from playwright.async_api import async_playwright
            
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
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()
                
                try:
                    logger.info(f"Navigating to: {scraper.search_url}")
                    
                    # Navigate to the page
                    await page.goto(scraper.search_url, wait_until='domcontentloaded', timeout=15000)
                    await page.wait_for_load_state('domcontentloaded', timeout=5000)
                    
                    # Process only 2 pages for testing
                    all_jobs = []
                    seen_job_ids = set()
                    page_num = 1
                    total_saved_to_supabase = 0
                    
                    for page_num in range(1, 3):  # Only 2 pages
                        logger.info(f"Processing page {page_num}...")
                        
                        # Extract jobs from current page
                        page_jobs = await scraper.extract_jobs_from_page(page)
                        
                        if not page_jobs:
                            logger.info(f"No jobs found on page {page_num}, stopping")
                            break
                        
                        # Filter out duplicates within this scraping session
                        new_jobs = []
                        for job in page_jobs:
                            if job['job_id'] not in seen_job_ids:
                                seen_job_ids.add(job['job_id'])
                                new_jobs.append(job)
                            else:
                                logger.debug(f"Skipping duplicate job: {job['job_id']}")
                        
                        if new_jobs:
                            all_jobs.extend(new_jobs)
                            logger.info(f"Found {len(new_jobs)} new jobs on page {page_num} (total unique: {len(all_jobs)})")
                            
                            # Save new jobs to Supabase immediately
                            if scraper.supabase:
                                new_count, existing_count = scraper.save_jobs_to_supabase(new_jobs)
                                total_saved_to_supabase += new_count
                                logger.info(f"Page {page_num} results: {new_count} new jobs saved, {existing_count} already existed (total new saved: {total_saved_to_supabase})")
                        else:
                            logger.info(f"No new jobs found on page {page_num}, stopping")
                            break
                        
                        # Small delay between pages
                        await asyncio.sleep(1)
                        
                        # Try to go to next page
                        if page_num < 2:  # Only try to go to page 2
                            try:
                                next_button = await page.query_selector('[data-testid="pagination-next"]')
                                if next_button:
                                    await next_button.click()
                                    await page.wait_for_load_state('domcontentloaded', timeout=5000)
                                else:
                                    logger.info("No next page button found, stopping")
                                    break
                            except Exception as e:
                                logger.warning(f"Could not navigate to next page: {e}")
                                break
                    
                    scraper.jobs = all_jobs
                    logger.info(f"Test completed: {len(all_jobs)} total jobs scraped, {total_saved_to_supabase} new jobs saved to database")
                    
                except Exception as e:
                    logger.error(f"Error during test scraping: {e}")
                    return scraper.jobs
                finally:
                    await context.close()
                    await browser.close()
            
            return scraper.jobs
        
        # Run the test
        jobs = await test_scrape_jobs()
        
        if jobs:
            print("\n✅ Test completed successfully!")
            print(f"📊 Results:")
            print(f"   - Total jobs scraped: {len(jobs)}")
            print(f"   - Check the logs above for new vs existing job breakdown")
            print(f"   - Each page shows: 'X new jobs saved, Y already existed'")
        else:
            print("\n❌ Test failed - no jobs were scraped")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(test_duplicate_detection()) 