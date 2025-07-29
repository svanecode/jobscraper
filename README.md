# Jobindex Scraper with Supabase Integration

A Python scraper that extracts job listings from [Jobindex.dk](https://www.jobindex.dk/jobsoegning/kontor) and saves them directly to Supabase database, with automatic validation and soft deletion of expired jobs.

## Features

- **Playwright-based scraping** - Handles JavaScript-rendered content
- **Supabase integration** - Direct database saving with duplicate detection
- **Job validation** - Automatic detection and soft deletion of expired jobs
- **AI-powered job scoring** - CFO Interim Services scoring using OpenAI
- **Multiple output formats** - JSON, CSV, and database
- **Clean data structure** - Essential job information only
- **Rate limiting** - Respectful scraping with delays
- **Error handling** - Robust error handling and logging

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Set Up Supabase (Optional)

If you want to save data to Supabase:

1. **Create a Supabase project** at [supabase.com](https://supabase.com)
2. **Get your credentials** from Project Settings → API
3. **Set environment variables**:

```bash
export SUPABASE_URL="https://your-project-id.supabase.co"
export SUPABASE_ANON_KEY="your-anon-key-here"
```

### 3. Create Database Table

Run this SQL in your Supabase SQL editor:

```sql
CREATE TABLE jobs (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT UNIQUE NOT NULL,
    title TEXT,
    job_url TEXT,
    company TEXT,
    company_url TEXT,
    location TEXT,
    publication_date DATE,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for better performance
CREATE INDEX idx_jobs_job_id ON jobs(job_id);
CREATE INDEX idx_jobs_company ON jobs(company);
CREATE INDEX idx_jobs_publication_date ON jobs(publication_date);
CREATE INDEX idx_jobs_deleted_at ON jobs(deleted_at);
```

**Note:** If you already have a table without the `deleted_at` column, run the `add_deleted_at_column.sql` script to add it.

### 4. Run the Scraper

```bash
# Run the full scraper
python playwright_scraper.py

# Test duplicate detection with limited pages
python test_scraper_duplicates.py
```

### 5. Validate and Clean Expired Jobs (Optional)

```bash
# Test with a small batch first
python test_job_validator.py

# Run full validation (handles all jobs, not just first 1000)
python job_validator.py

# Restore incorrectly deleted jobs
python restore_jobs.py

# Check specific job validity
python restore_jobs.py h1583150
```

### 6. Score Jobs for CFO Interim Services (Optional)

```bash
# First, add scoring columns to database
# Run the SQL in add_scoring_columns.sql in your Supabase SQL editor

# Test scoring with a small sample
python test_job_scorer.py

# Score all active unscored jobs
python job_scorer.py
```

**Scoring System:**
- **3** = Akut/midlertidigt og økonomirelateret → KPMG bør tage kontakt straks
- **2** = Økonomistilling hvor behovet kunne være der
- **1** = Lav sandsynlighed, men økonomirelateret
- **0** = Ikke økonomirelateret

## Usage

### With Supabase Credentials

```bash
# Set environment variables
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_ANON_KEY="your-anon-key"

# Run scraper
python playwright_scraper.py
```

### Without Supabase (Local Only)

```bash
# Run without setting environment variables
python playwright_scraper.py
```

### Job Validation

```bash
# Test validation with small batch
python test_job_validator.py

# Run full validation (checks all jobs and soft deletes expired ones)
python job_validator.py

# Restore incorrectly deleted jobs
python restore_jobs.py

# Check specific job validity
python restore_jobs.py h1583150

# Programmatic usage
from job_validator import JobValidator

validator = JobValidator()
results = await validator.validate_jobs(batch_size=10, max_jobs=50)

# Restore specific jobs
validator.restore_jobs_by_ids(['h1583150', 'h1583151'])
```

### Programmatic Usage

```python
from playwright_scraper import JobindexPlaywrightScraper

# Initialize with Supabase credentials
scraper = JobindexPlaywrightScraper(
    supabase_url="https://your-project.supabase.co",
    supabase_key="your-anon-key"
)

# Scrape jobs
jobs = await scraper.scrape_jobs(max_pages=3)

# Save to Supabase
scraper.save_to_supabase(table_name='jobs')
```

## Data Structure

Each job listing includes:

- `job_id` - Unique job identifier
- `title` - Job title
- `job_url` - Direct application link
- `company` - Company name
- `company_url` - Company profile link
- `location` - Job location
- `publication_date` - When the job was posted
- `description` - Job description
- `created_at` - Database timestamp (auto-generated)
- `deleted_at` - Soft deletion timestamp (NULL = active job)

## Output Files

The scraper creates:

1. **JSON file** - `jobindex_playwright_jobs_YYYYMMDD_HHMMSS.json`
2. **CSV file** - `jobindex_playwright_jobs_YYYYMMDD_HHMMSS.csv`
3. **Supabase table** - `jobs` (if credentials provided)

## Testing

### Test Supabase Connection

Test your Supabase setup:

```bash
python test_supabase.py
```

### Test Job Validator

Test the job validation functionality:

```bash
python test_job_validator.py
```

## Configuration

### Environment Variables

- `SUPABASE_URL` - Your Supabase project URL
- `SUPABASE_ANON_KEY` - Your Supabase anon/public key
- `SUPABASE_TABLE_NAME` - Custom table name (default: 'jobs')
- `OPENAI_API_KEY` - Your OpenAI API key (required for job scoring)

### Scraper Options

- `max_pages` - Number of pages to scrape (default: 3)
- `table_name` - Supabase table name (default: 'jobs')

## Example Output

### Console Output
```
Jobindex Playwright Scraper with Supabase Integration
============================================================
Target URL: https://www.jobindex.dk/jobsoegning/kontor
✅ Jobs successfully saved to Supabase!

=== Jobindex Playwright Scraping Summary ===
Total jobs: 20

Top companies:
  Radiometer Medical ApS: 2 jobs
  Professionshøjskolen Absalon: 1 jobs
  ...

Results saved to:
  Supabase: jobs table
  JSON: jobindex_playwright_jobs_20250726_175302.json
  CSV: jobindex_playwright_jobs_20250726_175302.csv
```

### Sample Job Data
```json
{
  "job_id": "h1577351",
  "title": "Projektleder til uddannelsesreform samt udvikling af undervisning og studiemiljø",
  "job_url": "https://candidate.hr-manager.net/ApplicationInit.aspx?cid=5001&ProjectId=189722&DepartmentId=9395&MediaId=5",
  "company": "Professionshøjskolen Absalon",
  "company_url": "https://www.jobindex.dk/virksomhed/27049/professionshoejskolen-absalon#om-virksomhed",
  "location": "Roskilde eller Slagelse",
  "publication_date": "2025-07-26",
  "description": "Her er der mulighed for at spille en central rolle..."
}
```

## Troubleshooting

### Common Issues

1. **Supabase connection failed**
   - Check your credentials
   - Verify the table exists
   - Run `python test_supabase.py`

2. **No jobs found**
   - Website structure may have changed
   - Check network connectivity
   - Verify the URL is accessible

3. **Playwright errors**
   - Run `playwright install chromium`
   - Check browser installation

4. **Job scoring errors**
   - Ensure `OPENAI_API_KEY` is set in environment
   - Check if scoring columns exist in database
   - Run `python test_job_scorer.py` to test

### Debug Mode

The scraper includes comprehensive logging. Check console output for:
- Connection status
- Number of jobs found
- Database save confirmations
- Error messages

## Ethical Considerations

- **Rate limiting** - 1-second delays between requests
- **Respectful scraping** - Proper headers and user agents
- **Terms of service** - Always check website terms
- **Data usage** - Use responsibly and legally

## License

This project is for educational purposes. Use responsibly and in accordance with applicable laws and website terms of service. 