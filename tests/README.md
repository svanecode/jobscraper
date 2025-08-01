# Tests and Utilities

This folder contains all test files, utility scripts, and temporary files for the JobindexV2 project.

## Test Files

### Core Tests
- `test_supabase_connection.py` - Tests Supabase database connection and basic operations
- `test_job_info_scraper.py` - Tests the job info scraper functionality
- `test_github_actions_scorer.py` - Tests job scoring functionality for GitHub Actions
- `test_specific_job.py` - Tests scraping a specific job ID

### Utility Scripts
- `run_job_info_scraper.py` - Utility script to run the job info scraper
- `run_job_scoring.py` - Utility script to run job scoring
- `score_10_jobs.py` - Utility to score a limited number of jobs for testing

### Backup Files
- `job_info_scraper_backup.py` - Backup version of the job info scraper

### Documentation
- `JOB_INFO_SCRAPER_README.md` - Documentation for the job info scraper
- `JOB_SCORING_README.md` - Documentation for the job scoring functionality

### Log Files
- `job_scoring_20250730_222555.log` - Log file from job scoring operations

## Running Tests

To run tests, navigate to the tests directory and execute:

```bash
# Test Supabase connection
python test_supabase_connection.py

# Test job info scraper
python test_job_info_scraper.py

# Test specific job
python test_specific_job.py

# Test GitHub Actions scorer
python test_github_actions_scorer.py
```

## Running Utilities

```bash
# Run job info scraper
python run_job_info_scraper.py

# Run job scoring
python run_job_scoring.py

# Score 10 jobs for testing
python score_10_jobs.py
```

## Notes

- All test files are designed to be run independently
- Backup files are kept for reference but should not be used in production
- Log files are automatically generated during operations
- Documentation files provide detailed information about specific components 