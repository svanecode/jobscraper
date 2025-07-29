#!/usr/bin/env python3
"""
Test Validator Batch - Test the validator with small batch size

This script tests the validator with a small batch size to see if it processes
the specific job that wasn't being deleted.
"""

import asyncio
import logging
from job_validator_auto import AutomatedJobValidator

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_validator_batch():
    """Test the validator with a small batch size"""
    try:
        print("🧪 Testing validator with small batch size...")
        print("=" * 50)
        
        # Initialize validator
        validator = AutomatedJobValidator()
        
        # Run validation with very small batch size
        print("Running validator with batch_size=1 and max_jobs=5...")
        await validator.validate_jobs(
            batch_size=1,  # Process one job at a time
            max_jobs=5     # Only process 5 jobs
        )
        
        print()
        print("=" * 50)
        print("✅ Test completed!")
        print("Check the logs above to see if job h1570748 was processed")
        
    except Exception as e:
        logger.error(f"Error in test: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(test_validator_batch()) 