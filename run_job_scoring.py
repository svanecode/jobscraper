#!/usr/bin/env python3
"""
Simple Command-Line Interface for Job Scoring

This script provides a simple way to run job scoring with customizable parameters.

Usage:
    python run_job_scoring.py                    # Score 10 jobs (default)
    python run_job_scoring.py 5                 # Score 5 jobs
    python run_job_scoring.py --help            # Show help
    python run_job_scoring.py --count 15        # Score 15 jobs
"""

import asyncio
import argparse
import sys
from score_10_jobs import JobScoringRunner

def main():
    """Main function with command-line argument parsing"""
    parser = argparse.ArgumentParser(
        description="Score jobs using AI-powered analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_job_scoring.py              # Score 10 jobs (default)
  python run_job_scoring.py 5            # Score 5 jobs
  python run_job_scoring.py --count 15   # Score 15 jobs
  python run_job_scoring.py --help       # Show this help message
        """
    )
    
    parser.add_argument(
        'count',
        nargs='?',
        type=int,
        default=10,
        help='Number of jobs to score (default: 10)'
    )
    
    parser.add_argument(
        '--count',
        type=int,
        dest='count_alt',
        help='Alternative way to specify number of jobs to score'
    )
    
    args = parser.parse_args()
    
    # Use the count from --count if provided, otherwise use positional argument
    job_count = args.count_alt if args.count_alt is not None else args.count
    
    if job_count <= 0:
        print("❌ Error: Number of jobs must be positive")
        sys.exit(1)
    
    if job_count > 100:
        print("⚠️  Warning: Scoring more than 100 jobs may take a long time and use many API calls")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled by user")
            sys.exit(0)
    
    print(f"🎯 Will score {job_count} jobs")
    
    try:
        runner = JobScoringRunner()
        asyncio.run(runner.run(job_count=job_count))
    except KeyboardInterrupt:
        print("\n⏹️  Job scoring interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 