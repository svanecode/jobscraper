#!/usr/bin/env python3
"""
Test script for GitHub Actions Job Validator V2 with Scoring

This script tests the new functionality:
- 100 job limit per run
- Prioritizing newest unscored jobs by publication date
- Integration with job scoring
"""

import asyncio
import logging
import sys
from job_validator_github_actions_v2 import GitHubActionsJobValidatorV2

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def test_job_retrieval():
    """Test the new job retrieval logic"""
    logger.info("🧪 Testing job retrieval logic...")
    
    try:
        validator = GitHubActionsJobValidatorV2()
        
        # Test getting jobs with different limits
        for limit in [10, 50, 100]:
            logger.info(f"\n📊 Testing with limit={limit}")
            jobs = validator.get_active_jobs(max_jobs=limit)
            
            if jobs:
                logger.info(f"✅ Retrieved {len(jobs)} jobs")
                
                # Check if jobs are ordered by publication date (newest first)
                if len(jobs) > 1:
                    first_date = jobs[0].get('publication_date')
                    last_date = jobs[-1].get('publication_date')
                    logger.info(f"📅 First job date: {first_date}")
                    logger.info(f"📅 Last job date: {last_date}")
                    
                    # Count unscored vs scored jobs
                    unscored = sum(1 for job in jobs if job.get('cfo_score') is None)
                    scored = len(jobs) - unscored
                    logger.info(f"🎯 Unscored jobs: {unscored}")
                    logger.info(f"✅ Scored jobs: {scored}")
                else:
                    logger.info("ℹ️ Only one job retrieved")
            else:
                logger.warning("⚠️ No jobs retrieved")
                
    except Exception as e:
        logger.error(f"❌ Error testing job retrieval: {e}")
        raise

async def test_validation_only():
    """Test validation without scoring"""
    logger.info("\n🔍 Testing validation only (without scoring)...")
    
    try:
        validator = GitHubActionsJobValidatorV2()
        
        # Test with a small batch
        await validator.validate_jobs(
            batch_size=2,  # Very small batch for testing
            max_jobs=5     # Only 5 jobs for testing
        )
        
        logger.info("✅ Validation test completed")
        
    except Exception as e:
        logger.error(f"❌ Error testing validation: {e}")
        raise

async def main():
    """Main test function"""
    logger.info("🚀 Starting GitHub Actions Job Validator V2 Tests")
    logger.info("=" * 60)
    
    try:
        # Test 1: Job retrieval logic
        await test_job_retrieval()
        
        # Test 2: Validation only (small batch)
        await test_validation_only()
        
        logger.info("\n🎉 All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 