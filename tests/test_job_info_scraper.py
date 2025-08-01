#!/usr/bin/env python3
"""
Test script for JobInfoScraper
Tests scraping a single job to verify functionality
"""

import asyncio
import logging
from job_info_scraper import JobInfoScraper

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_single_job():
    """Test scraping a single job"""
    try:
        # Initialize the scraper
        scraper = JobInfoScraper()
        
        # Test with the job ID from the web search results
        test_job_id = "r13248036"  # Climate Advocacy Officer job
        
        logger.info(f"Testing job info scraper with job ID: {test_job_id}")
        
        # Scrape job information
        job_info = await scraper.scrape_job_info(test_job_id)
        
        if job_info:
            logger.info("=== SCRAPED JOB INFORMATION ===")
            for key, value in job_info.items():
                if value:
                    # Truncate long values for display
                    display_value = value[:100] + "..." if len(str(value)) > 100 else value
                    logger.info(f"{key}: {display_value}")
                else:
                    logger.info(f"{key}: None/Empty")
        else:
            logger.error("Failed to scrape job information")
        
    except Exception as e:
        logger.error(f"Error in test: {e}")
        raise

async def test_database_query():
    """Test the database query for jobs with missing info"""
    try:
        # Initialize the scraper
        scraper = JobInfoScraper()
        
        logger.info("Testing database query for jobs with missing info")
        
        # Get jobs with missing information
        jobs = scraper.get_jobs_with_missing_info()
        
        logger.info(f"Found {len(jobs)} jobs with missing information")
        
        if jobs:
            # Show first few jobs as examples
            for i, job in enumerate(jobs[:3]):
                logger.info(f"Job {i+1}: {job.get('job_id')} - {job.get('title', 'No title')}")
                logger.info(f"  Company: '{job.get('company', 'None')}'")
                logger.info(f"  Company URL: '{job.get('company_url', 'None')}'")
                logger.info(f"  Description: '{job.get('description', 'None')[:50]}...' if job.get('description') else 'None'")
                logger.info("---")
        
        # Get statistics
        stats = scraper.get_missing_info_stats()
        logger.info("=== MISSING INFO STATISTICS ===")
        logger.info(f"Total active jobs: {stats['total_jobs']}")
        logger.info(f"Jobs with missing info: {stats['missing_info']} ({stats['missing_percentage']:.1f}%)")
        logger.info("Missing fields breakdown:")
        for field, count in stats['missing_fields'].items():
            percentage = (count / stats['total_jobs'] * 100) if stats['total_jobs'] > 0 else 0
            logger.info(f"  {field}: {count} jobs ({percentage:.1f}%)")
        
    except Exception as e:
        logger.error(f"Error in database test: {e}")
        raise

async def main():
    """Main test function"""
    logger.info("Starting JobInfoScraper tests")
    
    # Test database query first
    await test_database_query()
    
    # Test single job scraping
    await test_single_job()
    
    logger.info("Tests completed")

if __name__ == "__main__":
    asyncio.run(main()) 