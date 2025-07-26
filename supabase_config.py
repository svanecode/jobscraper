"""
Supabase Configuration for Jobindex Scraper

To use Supabase integration, you need to:

1. Create a Supabase project at https://supabase.com
2. Get your project URL and anon key from the project settings
3. Set up environment variables or pass credentials directly

Environment Variables:
- SUPABASE_URL: Your Supabase project URL
- SUPABASE_ANON_KEY: Your Supabase anon/public key

Example usage:
```python
from playwright_scraper import JobindexPlaywrightScraper

# Option 1: Use environment variables
scraper = JobindexPlaywrightScraper()

# Option 2: Pass credentials directly
scraper = JobindexPlaywrightScraper(
    supabase_url="https://your-project.supabase.co",
    supabase_key="your-anon-key"
)
```

Database Table Structure:
The scraper expects a table named 'jobs' with the following columns:
- job_id (text, primary key)
- title (text)
- job_url (text)
- company (text)
- company_url (text)
- location (text)
- publication_date (date)
- description (text)
- created_at (timestamp with time zone, auto-generated)

SQL to create the table:
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index for faster queries
CREATE INDEX idx_jobs_job_id ON jobs(job_id);
CREATE INDEX idx_jobs_company ON jobs(company);
CREATE INDEX idx_jobs_publication_date ON jobs(publication_date);
```
""" 