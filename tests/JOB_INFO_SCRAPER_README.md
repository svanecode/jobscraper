# Job Info Scraper

A Python script that scrapes missing company information from individual Jobindex job URLs for jobs that have empty `company`, `company_url`, or `description` fields in the database.

## Overview

The JobInfoScraper identifies jobs in your Supabase database that have missing information and visits each job's individual page to extract the missing data. This is useful when the main scraper doesn't capture all the information from the job listing pages.

## Features

- **Identifies missing data**: Finds jobs with empty company, company_url, or description fields
- **Individual job scraping**: Visits each job's specific URL to extract missing information
- **Multiple selectors**: Uses various CSS selectors to find company and description information
- **Database updates**: Automatically updates the database with scraped information
- **Progress tracking**: Shows progress and statistics during processing
- **Rate limiting**: Respectful scraping with configurable delays
- **Error handling**: Robust error handling and logging

## Requirements

- Python 3.7+
- Playwright
- Supabase client
- Environment variables for Supabase credentials

## Installation

1. **Install dependencies**:
   ```bash
   pip install playwright supabase python-dotenv
   playwright install chromium
   ```

2. **Set up environment variables**:
   ```bash
   export SUPABASE_URL="https://your-project-id.supabase.co"
   export SUPABASE_ANON_KEY="your-anon-key-here"
   ```

   Or create a `.env` file:
   ```
   SUPABASE_URL=https://your-project-id.supabase.co
   SUPABASE_ANON_KEY=your-anon-key-here
   ```

## Usage

### Basic Usage

Run the scraper to process all jobs with missing information:

```bash
python run_job_info_scraper.py
```

### Command Line Options

```bash
# Process only first 10 jobs (for testing)
python run_job_info_scraper.py --max-jobs 10

# Use faster delay (1 second between requests)
python run_job_info_scraper.py --delay 1.0

# Test mode: only show statistics, don't process jobs
python run_job_info_scraper.py --test

# Enable verbose logging
python run_job_info_scraper.py --verbose

# Combine options
python run_job_info_scraper.py --max-jobs 5 --delay 1.5 --verbose
```

### Programmatic Usage

```python
from job_info_scraper import JobInfoScraper
import asyncio

async def main():
    scraper = JobInfoScraper()
    
    # Get statistics
    stats = scraper.get_missing_info_stats()
    print(f"Jobs with missing info: {stats['missing_info']}")
    
    # Process jobs
    await scraper.process_jobs_with_missing_info(
        max_jobs=10,  # Process only 10 jobs
        delay=2.0     # 2 second delay between requests
    )

asyncio.run(main())
```

## Testing

### Test Single Job

Test scraping a specific job:

```bash
python test_job_info_scraper.py
```

This will:
1. Test the database query for jobs with missing info
2. Test scraping a single job (r13248036 - Climate Advocacy Officer)

### Test Database Connection

```bash
python test_supabase_connection.py
```

## How It Works

1. **Database Query**: The scraper queries the database for jobs where `company`, `company_url`, or `description` fields are empty or null
2. **Job URL Construction**: For each job, it constructs the URL: `https://www.jobindex.dk/vis-job/{job_id}`
3. **Page Scraping**: Uses Playwright to visit each job page and extract missing information
4. **Data Extraction**: Uses multiple CSS selectors to find company name, company URL, and job description
5. **Database Update**: Updates the database with the scraped information

## CSS Selectors Used

### Company Information
- `h1 + div a` - Company link near the title
- `.company-name a` - Company name link
- `a[href*="/virksomhed/"]` - Any link containing /virksomhed/
- `.jix-toolbar-top__company a` - Company in toolbar

### Job Description
- `.job-description` - Main job description
- `.PaidJob-inner` - Job content area
- `[data-testid="job-description"]` - Test ID for description
- `.job-content` - Job content
- `article` - Article content

### Additional Information
- Job title: `h1`, `.job-title`, `[data-testid="job-title"]`
- Location: `.job-location`, `.location`, `[data-testid="job-location"]`, `.jix_robotjob--area`

## Output

The script provides detailed logging including:

- Initial statistics showing how many jobs have missing information
- Progress updates during processing
- Success/error counts for each job
- Final statistics showing improvement

Example output:
```
2024-01-15 10:30:00 - INFO - === INITIAL STATISTICS ===
2024-01-15 10:30:00 - INFO - Total active jobs: 1250
2024-01-15 10:30:00 - INFO - Jobs with missing info: 45 (3.6%)
2024-01-15 10:30:00 - INFO - Missing fields breakdown:
2024-01-15 10:30:00 - INFO -   company: 12 jobs (1.0%)
2024-01-15 10:30:00 - INFO -   company_url: 23 jobs (1.8%)
2024-01-15 10:30:00 - INFO -   description: 35 jobs (2.8%)
2024-01-15 10:30:01 - INFO - Processing job 1/45: r13248036
2024-01-15 10:30:01 - INFO - Missing fields for job r13248036: ['company', 'description']
2024-01-15 10:30:03 - INFO - Successfully scraped info for job r13248036
2024-01-15 10:30:03 - INFO - Updated job r13248036 with: ['company', 'description']
2024-01-15 10:30:03 - INFO - Successfully updated job r13248036
...
2024-01-15 10:35:00 - INFO - === PROCESSING COMPLETE ===
2024-01-15 10:35:00 - INFO - Total jobs processed: 45
2024-01-15 10:35:00 - INFO - Successfully updated: 42
2024-01-15 10:35:00 - INFO - Errors: 3
```

## Error Handling

The script handles various error scenarios:

- **Network errors**: Retries and continues with next job
- **Missing selectors**: Tries multiple CSS selectors for each field
- **Database errors**: Logs errors and continues processing
- **Invalid job IDs**: Skips jobs without valid job_id

## Rate Limiting

The script includes configurable delays between requests to be respectful to Jobindex's servers:

- Default delay: 2 seconds between requests
- Configurable via `--delay` parameter
- Recommended minimum: 1 second

## Database Schema

The script expects a `jobs` table with the following fields:
- `job_id` (text, primary key)
- `company` (text)
- `company_url` (text)
- `description` (text)
- `title` (text, optional)
- `location` (text, optional)
- `deleted_at` (timestamp, for soft deletion)

## Troubleshooting

### Common Issues

1. **Supabase connection errors**:
   - Verify your environment variables
   - Check your Supabase project URL and API key

2. **Playwright installation issues**:
   ```bash
   playwright install chromium
   ```

3. **No jobs found with missing info**:
   - Check if your database has jobs with empty fields
   - Verify the database schema matches expectations

4. **Scraping failures**:
   - Jobindex may have changed their HTML structure
   - Check the CSS selectors in the code
   - Try running with `--verbose` for more details

### Debug Mode

Enable verbose logging to see detailed information:

```bash
python run_job_info_scraper.py --verbose --max-jobs 1
```

## Contributing

To improve the scraper:

1. **Add new selectors**: If Jobindex changes their HTML structure, add new CSS selectors to the `scrape_job_info` method
2. **Improve error handling**: Add specific error handling for new scenarios
3. **Optimize performance**: Adjust delays or add parallel processing

## License

This script is part of the JobindexV2 project and follows the same licensing terms. 