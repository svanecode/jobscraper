# JobindexV2 Project Structure

## Overview
This project has been cleaned up and organized for better maintainability. All temporary files, test files, and utilities have been moved to a dedicated `tests/` folder.

## Main Directory Structure

```
JobindexV2/
├── README.md                           # Main project documentation
├── PROJECT_STRUCTURE.md               # This file - project organization
├── requirements.txt                   # Python dependencies
├── .gitignore                        # Git ignore rules
├── .github/                          # GitHub Actions configuration
├── tests/                            # All test files and utilities
└── Core Application Files:
    ├── playwright_scraper.py         # Main job scraping functionality
    ├── job_info_scraper.py           # Detailed job information scraper
    ├── job_scorer.py                 # AI-powered job scoring system
    ├── job_validator_github_actions_v2.py  # Job validation and cleanup
    ├── supabase_config.py            # Supabase configuration
    └── add_scoring_columns.sql       # Database schema updates
```

## Core Application Files

### Main Scrapers
- **`playwright_scraper.py`** - Primary job listing scraper using Playwright
- **`job_info_scraper.py`** - Scrapes detailed information for individual jobs

### Job Processing
- **`job_scorer.py`** - AI-powered scoring system for CFO interim services
- **`job_validator_github_actions_v2.py`** - Validates jobs and handles expired listings

### Configuration
- **`supabase_config.py`** - Supabase client configuration
- **`add_scoring_columns.sql`** - SQL script to add scoring columns to database

## Tests Directory (`tests/`)

### Test Files
- `test_supabase_connection.py` - Database connection tests
- `test_job_info_scraper.py` - Job scraper functionality tests
- `test_github_actions_scorer.py` - Scoring system tests
- `test_specific_job.py` - Individual job testing

### Utility Scripts
- `run_job_info_scraper.py` - Utility to run job info scraper
- `run_job_scoring.py` - Utility to run job scoring
- `score_10_jobs.py` - Limited job scoring for testing

### Documentation
- `JOB_INFO_SCRAPER_README.md` - Detailed scraper documentation
- `JOB_SCORING_README.md` - Scoring system documentation
- `README.md` - Tests directory documentation

### Backup and Log Files
- `job_info_scraper_backup.py` - Backup version of scraper
- `job_scoring_20250730_222555.log` - Scoring operation logs

## Files Removed/Cleaned

### Removed Files
- `__pycache__/` - Python cache directory
- All `.pyc` and `.pyo` files - Compiled Python files

### Moved Files
- All `test_*.py` files → `tests/`
- All `run_*.py` files → `tests/`
- All `JOB_*_README.md` files → `tests/`
- Backup files → `tests/`
- Log files → `tests/`

## Benefits of This Organization

1. **Cleaner Root Directory** - Only essential application files remain
2. **Better Testing Structure** - All tests and utilities in one place
3. **Easier Maintenance** - Clear separation between production and test code
4. **Improved Documentation** - Dedicated documentation for each component
5. **Better Version Control** - Temporary files properly organized

## Usage

### Running Core Application
```bash
# Main scraping
python playwright_scraper.py

# Job info scraping
python job_info_scraper.py

# Job scoring
python job_scorer.py

# Job validation
python job_validator_github_actions_v2.py
```

### Running Tests and Utilities
```bash
# Navigate to tests directory
cd tests/

# Run specific tests
python test_supabase_connection.py
python test_job_info_scraper.py

# Run utilities
python run_job_info_scraper.py
python score_10_jobs.py
```

## Maintenance Notes

- All temporary files should be placed in the `tests/` directory
- New test files should follow the `test_*.py` naming convention
- Utility scripts should be placed in `tests/` with descriptive names
- Log files are automatically moved to `tests/` during cleanup operations 