#!/usr/bin/env python3
"""
Test Job Scorer - Test the job scoring functionality with a small sample

This script tests the job scoring functionality with a limited number of jobs
to verify everything works correctly before running on the full dataset.
"""

import asyncio
import logging
from job_scorer import JobScorer

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_scoring():
    """Test the job scoring functionality"""
    try:
        # Initialize the job scorer
        scorer = JobScorer()
        
        # Test with a small number of active unscored jobs
        logger.info("Starting test scoring with 5 active unscored jobs...")
        
        await scorer.score_all_jobs(
            batch_size=2,  # Small batch size for testing
            max_jobs=5,    # Only test with 5 jobs
            delay=1.0,     # 1 second delay between batches
            only_unscored=True  # Only score jobs that haven't been scored yet
        )
        
        # Get and display statistics
        stats = scorer.get_scoring_stats()
        logger.info("=== TEST RESULTS ===")
        logger.info(f"Total jobs scored: {stats['total_scored']}")
        logger.info(f"Average score: {stats['average_score']:.2f}")
        logger.info("Score distribution:")
        for score, count in stats['distribution'].items():
            percentage = (count / stats['total_scored']) * 100 if stats['total_scored'] > 0 else 0
            logger.info(f"  Score {score}: {count} jobs ({percentage:.1f}%)")
        
        logger.info("Test completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(test_scoring()) 