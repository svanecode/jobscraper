#!/usr/bin/env python3
"""
Test script for specific job r13241369
"""

import asyncio
import logging
from job_info_scraper import JobInfoScraper

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_specific_job():
    """Test scraping the specific job r13241369"""
    try:
        # Initialize the scraper
        scraper = JobInfoScraper()
        
        # Test with the specific job ID
        test_job_id = "r13241369"  # KU LCA-specialist job
        
        logger.info(f"Testing job info scraper with job ID: {test_job_id}")
        
        # Scrape job information
        job_info = await scraper.scrape_job_info(test_job_id)
        
        if job_info:
            logger.info("=== SCRAPED JOB INFORMATION ===")
            for key, value in job_info.items():
                if value:
                    # Truncate long values for display
                    display_value = value[:200] + "..." if len(str(value)) > 200 else value
                    logger.info(f"{key}: {display_value}")
                else:
                    logger.info(f"{key}: None/Empty")
        else:
            logger.error("Failed to scrape job information")
        
    except Exception as e:
        logger.error(f"Error in test: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(test_specific_job()) 