#!/usr/bin/env python3
"""
Job Scoring Script - Score 10 Jobs Manually

This script scores exactly 10 jobs from the database using the JobScorer class.
It provides detailed, descriptive output about each job being scored and the results.

Features:
- Scores exactly 10 jobs (or fewer if not enough available)
- Detailed output for each job including title, company, and score
- Summary statistics at the end
- Can be run manually from command line
- Handles errors gracefully with informative messages

Usage:
    python score_10_jobs.py

Requirements:
    - Environment variables: SUPABASE_URL, SUPABASE_ANON_KEY, OPENAI_API_KEY
    - Or .env file with the same variables
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional
from job_scorer import JobScorer

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, continue without it

# Set up logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'job_scoring_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

class JobScoringRunner:
    def __init__(self):
        """Initialize the job scoring runner"""
        try:
            self.scorer = JobScorer()
            logger.info("✅ JobScorer initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize JobScorer: {e}")
            raise
    
    def get_jobs_to_score(self, count: int = 10) -> List[Dict]:
        """
        Get jobs to score, prioritizing unscored jobs
        
        Args:
            count: Number of jobs to fetch (default: 10)
        
        Returns:
            List of job dictionaries
        """
        logger.info(f"🔍 Fetching {count} jobs to score...")
        
        # First try to get unscored jobs
        unscored_jobs = self.scorer.get_all_jobs(max_jobs=count, only_unscored=True)
        
        if len(unscored_jobs) >= count:
            logger.info(f"✅ Found {len(unscored_jobs)} unscored jobs")
            return unscored_jobs[:count]
        
        # If not enough unscored jobs, get any active jobs
        logger.info(f"⚠️  Only found {len(unscored_jobs)} unscored jobs, fetching more active jobs...")
        all_jobs = self.scorer.get_all_jobs(max_jobs=count)
        
        if len(all_jobs) < count:
            logger.warning(f"⚠️  Only {len(all_jobs)} total jobs available (requested {count})")
        
        return all_jobs[:count]
    
    def print_job_details(self, job: Dict, score: Optional[int] = None) -> None:
        """
        Print detailed information about a job
        
        Args:
            job: Job dictionary
            score: Optional score to display
        """
        print("\n" + "="*80)
        print(f"📋 JOB DETAILS")
        print("="*80)
        print(f"🆔 Job ID: {job.get('job_id', 'N/A')}")
        print(f"📝 Title: {job.get('title', 'N/A')}")
        print(f"🏢 Company: {job.get('company', 'N/A')}")
        print(f"📍 Location: {job.get('location', 'N/A')}")
        
        if score is not None:
            score_description = {
                0: "❌ Not relevant (not finance-related or consulting firm)",
                1: "🟡 Low relevance (finance-related but unlikely need)",
                2: "🟠 Medium relevance (finance position with potential need)",
                3: "🟢 High relevance (urgent/temporary finance need)"
            }
            print(f"⭐ Score: {score} - {score_description.get(score, 'Unknown')}")
        
        # Show truncated description
        description = job.get('description', 'N/A')
        if len(description) > 300:
            description = description[:300] + "..."
        print(f"📄 Description: {description}")
        print("="*80)
    
    async def score_jobs_sequentially(self, jobs: List[Dict]) -> Dict:
        """
        Score jobs one by one with detailed output
        
        Args:
            jobs: List of jobs to score
        
        Returns:
            Dictionary with scoring results
        """
        results = {
            'total_jobs': len(jobs),
            'successful_scores': 0,
            'errors': 0,
            'scores': [],
            'job_details': []
        }
        
        print(f"\n🚀 Starting to score {len(jobs)} jobs...")
        print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        for i, job in enumerate(jobs, 1):
            print(f"\n📊 Processing job {i}/{len(jobs)}")
            self.print_job_details(job)
            
            try:
                print("🤖 Calling OpenAI API for scoring...")
                score = await self.scorer.score_job(job)
                
                if score is not None:
                    print(f"✅ Successfully scored: {score}")
                    results['successful_scores'] += 1
                    results['scores'].append(score)
                    
                    # Update database
                    if self.scorer.update_job_score(job['job_id'], score):
                        print("💾 Score saved to database")
                    else:
                        print("⚠️  Warning: Failed to save score to database")
                    
                    # Store job details with score
                    results['job_details'].append({
                        'job_id': job.get('job_id'),
                        'title': job.get('title'),
                        'company': job.get('company'),
                        'score': score
                    })
                    
                else:
                    print("❌ Failed to get score from API")
                    results['errors'] += 1
                    
            except Exception as e:
                print(f"❌ Error scoring job: {e}")
                results['errors'] += 1
            
            # Add delay between API calls to respect rate limits
            if i < len(jobs):
                print("⏳ Waiting 2 seconds before next job...")
                await asyncio.sleep(2)
        
        return results
    
    def print_summary(self, results: Dict) -> None:
        """
        Print detailed summary of scoring results
        
        Args:
            results: Results dictionary from score_jobs_sequentially
        """
        print("\n" + "="*80)
        print("📊 SCORING SUMMARY")
        print("="*80)
        print(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📋 Total jobs processed: {results['total_jobs']}")
        print(f"✅ Successfully scored: {results['successful_scores']}")
        print(f"❌ Errors: {results['errors']}")
        print(f"📈 Success rate: {(results['successful_scores']/results['total_jobs']*100):.1f}%")
        
        if results['scores']:
            # Score distribution
            distribution = {0: 0, 1: 0, 2: 0, 3: 0}
            for score in results['scores']:
                distribution[score] += 1
            
            print(f"\n📊 Score Distribution:")
            for score, count in distribution.items():
                percentage = (count / len(results['scores'])) * 100
                score_desc = {
                    0: "Not relevant",
                    1: "Low relevance", 
                    2: "Medium relevance",
                    3: "High relevance"
                }
                print(f"  Score {score} ({score_desc[score]}): {count} jobs ({percentage:.1f}%)")
            
            # Average score
            avg_score = sum(results['scores']) / len(results['scores'])
            print(f"\n📊 Average Score: {avg_score:.2f}")
            
            # High-priority jobs (score 3)
            high_priority = distribution[3]
            if high_priority > 0:
                print(f"🎯 High-priority jobs (score 3): {high_priority}")
                print("   These jobs should be contacted immediately!")
            
            # Show individual job results
            print(f"\n📋 Individual Job Results:")
            for job_detail in results['job_details']:
                score_emoji = "🟢" if job_detail['score'] == 3 else "🟠" if job_detail['score'] == 2 else "🟡" if job_detail['score'] == 1 else "❌"
                print(f"  {score_emoji} {job_detail['title']} at {job_detail['company']} → Score: {job_detail['score']}")
        
        print("="*80)
    
    async def run(self, job_count: int = 10) -> None:
        """
        Main method to run the job scoring process
        
        Args:
            job_count: Number of jobs to score (default: 10)
        """
        print("🎯 JOB SCORING SCRIPT")
        print("="*50)
        print(f"Target: Score {job_count} jobs")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # Get jobs to score
            jobs = self.get_jobs_to_score(job_count)
            
            if not jobs:
                print("❌ No jobs found to score!")
                return
            
            # Score jobs
            results = await self.score_jobs_sequentially(jobs)
            
            # Print summary
            self.print_summary(results)
            
            print("\n🎉 Job scoring completed successfully!")
            
        except Exception as e:
            logger.error(f"❌ Error in job scoring process: {e}")
            print(f"❌ Error: {e}")
            raise

async def main():
    """Main function to run the job scoring script"""
    try:
        runner = JobScoringRunner()
        await runner.run(job_count=10)
    except KeyboardInterrupt:
        print("\n⏹️  Job scoring interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("🚀 Starting Job Scoring Script...")
    asyncio.run(main()) 