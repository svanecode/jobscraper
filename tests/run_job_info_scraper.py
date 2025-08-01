#!/usr/bin/env python3
"""
Runner script for JobInfoScraper
Allows running the scraper with configurable parameters
"""

import asyncio
import argparse
import logging
from job_info_scraper import JobInfoScraper

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_scraper(max_jobs=None, delay=2.0, test_mode=False):
    """
    Run the job info scraper
    
    Args:
        max_jobs: Maximum number of jobs to process (None for all)
        delay: Delay between requests in seconds
        test_mode: If True, only show statistics without processing
    """
    try:
        # Initialize the scraper
        scraper = JobInfoScraper()
        
        # Print initial statistics
        stats = scraper.get_missing_info_stats()
        logger.info("=== INITIAL STATISTICS ===")
        logger.info(f"Total active jobs: {stats['total_jobs']}")
        logger.info(f"Jobs with missing info: {stats['missing_info']} ({stats['missing_percentage']:.1f}%)")
        logger.info("Missing fields breakdown:")
        for field, count in stats['missing_fields'].items():
            percentage = (count / stats['total_jobs'] * 100) if stats['total_jobs'] > 0 else 0
            logger.info(f"  {field}: {count} jobs ({percentage:.1f}%)")
        
        if test_mode:
            logger.info("Test mode: Only showing statistics, not processing jobs")
            return
        
        if stats['missing_info'] == 0:
            logger.info("No jobs with missing information found. Nothing to do.")
            return
        
        # Process jobs with missing information
        logger.info(f"Starting to process jobs with missing information...")
        await scraper.process_jobs_with_missing_info(
            max_jobs=max_jobs,
            delay=delay
        )
        
        # Print final statistics
        final_stats = scraper.get_missing_info_stats()
        logger.info("=== FINAL STATISTICS ===")
        logger.info(f"Total active jobs: {final_stats['total_jobs']}")
        logger.info(f"Jobs with missing info: {final_stats['missing_info']} ({final_stats['missing_percentage']:.1f}%)")
        logger.info("Missing fields breakdown:")
        for field, count in final_stats['missing_fields'].items():
            percentage = (count / final_stats['total_jobs'] * 100) if final_stats['total_jobs'] > 0 else 0
            logger.info(f"  {field}: {count} jobs ({percentage:.1f}%)")
        
        # Show improvement
        improvement = stats['missing_info'] - final_stats['missing_info']
        if improvement > 0:
            logger.info(f"Successfully filled missing information for {improvement} jobs!")
        
    except Exception as e:
        logger.error(f"Error running scraper: {e}")
        raise

def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(description='JobInfoScraper - Fill missing job information')
    parser.add_argument(
        '--max-jobs', 
        type=int, 
        default=None,
        help='Maximum number of jobs to process (default: all jobs with missing info)'
    )
    parser.add_argument(
        '--delay', 
        type=float, 
        default=2.0,
        help='Delay between requests in seconds (default: 2.0)'
    )
    parser.add_argument(
        '--test', 
        action='store_true',
        help='Test mode: only show statistics, do not process jobs'
    )
    parser.add_argument(
        '--verbose', 
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Print configuration
    logger.info("=== JOB INFO SCRAPER CONFIGURATION ===")
    logger.info(f"Max jobs: {args.max_jobs if args.max_jobs else 'All jobs with missing info'}")
    logger.info(f"Delay: {args.delay} seconds")
    logger.info(f"Test mode: {args.test}")
    logger.info(f"Verbose logging: {args.verbose}")
    logger.info("=" * 40)
    
    # Run the scraper
    asyncio.run(run_scraper(
        max_jobs=args.max_jobs,
        delay=args.delay,
        test_mode=args.test
    ))

if __name__ == "__main__":
    main() 