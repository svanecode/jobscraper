# Migration Guide: From Job Validator to Job Cleanup

## Overview

This guide helps you migrate from the old job validator system to the new, more efficient job cleanup approach.

## What Changed

### Old System (Job Validator)
- **`job_validator_github_actions_v2.py`**: Visited every job URL individually to check if jobs were expired
- **`.github/workflows/job-validator.yml`**: GitHub Actions workflow that ran the validator
- **Inefficient**: Required visiting hundreds/thousands of URLs, causing timeouts and high resource usage

### New System (Job Cleanup)
- **`job_cleanup.py`**: Uses `last_seen` timestamps to identify old jobs
- **`.github/workflows/job-cleanup.yml`**: New GitHub Actions workflow
- **Efficient**: No URL visits needed, just database queries

## Migration Steps

### 1. Add the `last_seen` Column

Run the SQL script to add the new column:

```sql
-- Run this in your Supabase SQL editor
\i add_last_seen_column.sql
```

Or manually:

```sql
ALTER TABLE jobs ADD COLUMN last_seen TIMESTAMP WITH TIME ZONE;
CREATE INDEX idx_jobs_last_seen ON jobs(last_seen);

-- Set initial last_seen values for existing jobs
UPDATE jobs 
SET last_seen = created_at 
WHERE deleted_at IS NULL AND last_seen IS NULL;
```

### 2. Update Your Scrapers

The scrapers have been updated to automatically set `last_seen` when they successfully access jobs:

- **`playwright_scraper.py`**: Now updates `last_seen` for existing jobs found during scraping
- **`job_info_scraper.py`**: Now updates `last_seen` when enriching job information

### 3. Replace the GitHub Actions Workflow

**Remove the old workflow:**
```bash
rm .github/workflows/job-validator.yml
```

**The new workflow is already created:**
- `.github/workflows/job-cleanup.yml` (runs every 6 hours)

### 4. Test the New System

```bash
# Test the cleanup utility
python job_cleanup.py

# Check statistics
python -c "
from job_cleanup import JobCleanup
cleanup = JobCleanup()
stats = cleanup.get_cleanup_stats()
print(f'Database stats: {stats}')
"
```

## Benefits of the New System

### Performance
- **Before**: Had to visit every job URL (slow, resource-intensive)
- **After**: Simple database queries (fast, efficient)

### Reliability
- **Before**: Prone to timeouts and network issues
- **After**: Database operations are reliable and fast

### Maintenance
- **Before**: Complex browser automation with fallback strategies
- **After**: Simple timestamp-based logic

### Scalability
- **Before**: Performance degraded with more jobs
- **After**: Performance remains consistent regardless of job count

## Configuration

### Cleanup Threshold

The default cleanup threshold is 48 hours. You can customize this:

```python
from job_cleanup import JobCleanup

# Clean up jobs not seen in 24 hours
cleanup = JobCleanup(cleanup_hours=24)

# Clean up jobs not seen in 72 hours
cleanup = JobCleanup(cleanup_hours=72)
```

### GitHub Actions Schedule

The cleanup workflow runs every 6 hours by default. You can modify the schedule in `.github/workflows/job-cleanup.yml`:

```yaml
schedule:
  # Run every 4 hours
  - cron: '0 */4 * * *'
  
  # Run twice daily
  - cron: '0 6,18 * * *'
  
  # Run daily at 2 AM
  - cron: '0 2 * * *'
```

## Monitoring

### Check Cleanup Statistics

```python
from job_cleanup import JobCleanup

cleanup = JobCleanup()
stats = cleanup.get_cleanup_stats()

print(f"Total jobs: {stats['total_jobs']}")
print(f"Active jobs: {stats['active_jobs']}")
print(f"Deleted jobs: {stats['deleted_jobs']}")
print(f"Jobs that will be cleaned up next run: {stats['old_jobs_count']}")
```

### Monitor GitHub Actions

The new workflow provides detailed logging:
- Number of jobs processed
- Number of jobs deleted
- Any errors encountered
- Database statistics

## Rollback Plan

If you need to rollback to the old system:

1. **Keep the old files**: Don't delete `job_validator_github_actions_v2.py` immediately
2. **Restore the old workflow**: Copy back `.github/workflows/job-validator.yml`
3. **Disable the new workflow**: Comment out the new workflow file

## Troubleshooting

### Jobs Not Being Cleaned Up

1. **Check `last_seen` values**: Ensure jobs have recent `last_seen` timestamps
2. **Verify cleanup threshold**: Check if the 48-hour threshold is appropriate
3. **Check for errors**: Review the cleanup logs for any issues

### Performance Issues

1. **Database indexes**: Ensure `idx_jobs_last_seen` index exists
2. **Query optimization**: The cleanup uses efficient database queries
3. **Batch size**: The cleanup processes all jobs in a single operation

### Missing `last_seen` Values

If some jobs don't have `last_seen` values:

```sql
-- Set last_seen to created_at for jobs without it
UPDATE jobs 
SET last_seen = created_at 
WHERE deleted_at IS NULL AND last_seen IS NULL;
```

## Support

If you encounter issues during migration:

1. Check the logs in GitHub Actions
2. Review the database statistics
3. Test the cleanup utility locally
4. Check that all scrapers are updating `last_seen` correctly 