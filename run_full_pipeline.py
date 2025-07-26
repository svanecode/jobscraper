#!/usr/bin/env python3
"""
Full Pipeline Script - Scrape and Validate Jobs

This script runs both the job scraper and validator in sequence:
1. Scrape new jobs from Jobindex
2. Validate existing jobs and soft delete expired ones
"""

import asyncio
import logging
from datetime import datetime
from playwright_scraper import JobindexPlaywrightScraper
from job_validator import JobValidator

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_full_pipeline():
    """Run the complete scraping and validation pipeline"""
    print("Jobindex Full Pipeline - Scrape and Validate")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Step 1: Scrape new jobs
        print("\n🔄 Step 1: Scraping new jobs...")
        scraper = JobindexPlaywrightScraper()
        jobs = await scraper.scrape_jobs()
        
        if jobs:
            print(f"✅ Scraped {len(jobs)} new jobs")
            
            # Save results locally
            json_file = scraper.save_to_json()
            csv_file = scraper.save_to_csv()
            print(f"📁 Results saved to: {json_file}, {csv_file}")
        else:
            print("⚠️  No new jobs scraped")
        
        # Step 2: Validate existing jobs
        print("\n🔄 Step 2: Validating existing jobs...")
        validator = JobValidator()
        
        # Show initial stats
        initial_stats = validator.get_deletion_stats()
        if initial_stats:
            print(f"📊 Initial stats: {initial_stats['active_jobs']} active, {initial_stats['deleted_jobs']} deleted")
        
        # Run validation
        validation_results = await validator.validate_jobs(batch_size=5, max_jobs=None)
        
        if validation_results:
            print(f"✅ Validation complete: {validation_results['total_checked']} checked, {validation_results['total_deleted']} deleted")
            
            # Show final stats
            final_stats = validator.get_deletion_stats()
            if final_stats:
                print(f"📊 Final stats: {final_stats['active_jobs']} active, {final_stats['deleted_jobs']} deleted")
        else:
            print("⚠️  No jobs validated")
        
        print(f"\n🎉 Pipeline completed successfully!")
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        print(f"❌ Pipeline failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_full_pipeline()) 