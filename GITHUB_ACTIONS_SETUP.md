# GitHub Actions Setup - Daily Job Scraper and Validator

## 🚀 **Automated Daily Pipeline**

The system is now configured to run automatically every day at **5:00 AM Danish time** (CET/CEST) using GitHub Actions.

## 📅 **Schedule Configuration**

- **Time**: 5:00 AM Danish time (CET/CEST)
- **UTC Time**: 3:00 AM UTC (configured to work year-round)
- **Frequency**: Daily
- **Cron Expression**: `0 3 * * *`

## 🔧 **What the Pipeline Does**

### 1. **Job Scraping** (`playwright_scraper.py`)
- Scrapes new job listings from Jobindex.dk
- Saves jobs to Supabase database
- Handles duplicates automatically
- Creates local backup files (JSON/CSV)

### 2. **Job Validation** (`job_validator_auto.py`)
- **Dry Run First**: Checks all jobs without deleting
- **Actual Validation**: Soft deletes expired jobs
- Identifies jobs with "Annoncen er udløbet!" text
- Provides detailed progress reporting

## 📁 **Files Created/Modified**

### New Files:
- `job_validator_auto.py` - Automated validator for GitHub Actions
- `test_expired_job.py` - Test script for expired jobs
- `test_multiple_expired.py` - Test multiple expired jobs
- `check_expired_jobs.py` - Interactive expired job finder

### Modified Files:
- `.github/workflows/daily-scraper.yml` - Updated workflow
- `job_validator.py` - Improved interactive validator

## 🔑 **Required GitHub Secrets**

Make sure these secrets are set in your GitHub repository:

1. **SUPABASE_URL**: Your Supabase project URL
2. **SUPABASE_ANON_KEY**: Your Supabase anon key

### How to Set Secrets:
1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add both secrets with your Supabase credentials

## 🏃‍♂️ **Manual Triggering**

You can manually trigger the workflow anytime:

1. Go to your GitHub repository
2. Click **Actions** tab
3. Select **Daily Job Scraper and Validator**
4. Click **Run workflow** button

## 📊 **Expected Performance**

- **Processing Rate**: ~1.8 jobs/second
- **Total Jobs**: ~2866 jobs
- **Estimated Time**: ~26 minutes for full validation
- **Memory Usage**: Efficient with proper cleanup

## 🔍 **Validation Logic**

The validator specifically looks for:
- **Danish Text**: "Annoncen er udløbet!" (The ad has expired!)
- **Safety First**: Any error = keep the job
- **Soft Deletion**: Sets `deleted_at` timestamp
- **Restore Capability**: Can restore deleted jobs

## 📈 **Monitoring and Logs**

### GitHub Actions Logs:
- View in **Actions** tab of your repository
- Shows detailed progress for each step
- Includes timing and error information

### Database Monitoring:
- Check `deleted_at` column for soft-deleted jobs
- Monitor job counts before/after validation
- Track deletion rates over time

## 🛠️ **Troubleshooting**

### Common Issues:

1. **Supabase Connection Failed**
   - Check secrets are set correctly
   - Verify Supabase project is active
   - Test connection manually first

2. **Playwright Installation Issues**
   - GitHub Actions automatically installs Playwright
   - Uses Ubuntu latest runner
   - Installs Chromium browser

3. **Timeout Issues**
   - Jobs with network issues are kept (safe approach)
   - Timeouts are set to 8 seconds per job
   - Progress is reported every 5 batches

## 📝 **Local Testing**

Before deploying to GitHub Actions, test locally:

```bash
# Test the automated validator
python job_validator_auto.py --dry-run

# Test with known expired jobs
python test_multiple_expired.py

# Test Supabase connection
python test_supabase_connection.py
```

## 🎯 **Success Criteria**

The pipeline is successful when:
- ✅ New jobs are scraped and saved
- ✅ Expired jobs are identified and soft-deleted
- ✅ No false positives (valid jobs kept)
- ✅ No false negatives (expired jobs detected)
- ✅ Progress reporting works
- ✅ Error handling is robust

## 🔄 **Recovery and Restore**

If jobs are incorrectly deleted:
- Use `restore_job()` function to restore specific jobs
- Check logs to identify any issues
- Adjust validation logic if needed

## 📞 **Support**

If you encounter issues:
1. Check GitHub Actions logs
2. Verify Supabase credentials
3. Test locally first
4. Review error messages in logs

The automated pipeline is now ready to run daily at 5 AM Danish time! 🎉 