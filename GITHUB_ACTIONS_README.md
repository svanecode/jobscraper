# GitHub Actions Setup for Jobindex Scraper

This repository includes a GitHub Actions workflow that automatically runs your Jobindex scraper every day and **pushes the results back to the repository**.

## 📋 Single Workflow

### Daily Scraper (`daily-scraper.yml`)
- Runs **once every day** at 5:00 AM Danish time
- **Automatically commits and pushes results** to the repository
- Manual trigger available
- Includes all necessary features:
  - ChromaDB connection testing
  - Error handling
  - Log management
  - Artifact storage
  - Git operations

## 🚀 Setup Instructions

### Step 1: Add Repository Secrets

Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions** and add these secrets:

```
OPENAI_API_KEY=your_openai_api_key_here
CHROMA_HOST=your_chroma_host_here
CHROMA_TENANT=your_chroma_tenant_id_here
CHROMA_DATABASE=your_chroma_database_name_here
CHROMA_API_KEY=your_chroma_api_token_here
```

**Note:** `GITHUB_TOKEN` is automatically provided by GitHub Actions.

### Step 2: Customize Schedule (Optional)

Edit the cron expression in the workflow file:

```yaml
schedule:
  # Current: Every day at 5:00 AM Danish time
  - cron: '0 4 * * *'
  
  # Other options:
  # - cron: '0 6 * * *'    # 6:00 AM UTC (7:00 AM Danish winter, 8:00 AM summer)
  # - cron: '0 */6 * * *'  # Every 6 hours
  # - cron: '0 4 * * 1-5' # Weekdays only at 4:00 AM UTC
```

## 🎯 Manual Trigger

You can manually run the scraper anytime:

1. Go to **Actions** tab in your repository
2. Click on your workflow (Daily Jobindex Scraper)
3. Click **Run workflow**
4. Set parameters:
   - **Max pages**: Number of pages to scrape (default: 50)
   - **Start page**: Page to start from (default: 1)

## 📊 Workflow Features

- ✅ **One run per day** (automated)
- ✅ Manual trigger capability
- ✅ **Automatic commit and push** of results
- ✅ ChromaDB connection testing
- ✅ Log artifact upload (30 days retention)
- ✅ Output artifact storage (30 days retention)
- ✅ Comprehensive summary in workflow
- ✅ Timeout protection (2 hours max)
- ✅ System dependency installation

## 🔄 **Auto-Commit & Push Feature**

The workflow automatically:

1. **Run the scraper** once per day
2. **Commit any changes** (logs, output files, etc.)
3. **Push results** back to your repository
4. **Include timestamps** in commit messages

### What Gets Committed:
- Scraper logs (`jobindex_scraper.log`)
- Any output files (JSON, CSV)
- Configuration changes
- Other generated files

### Commit Message Format:
```
🤖 Daily job scraping update - 2025-01-27 05:00:00 UTC
```

## 🔧 Customization Options

### Change Python Version
```yaml
- name: Set up Python
  uses: actions/setup-python@v4
  with:
    python-version: '3.12'  # Change this
```

### Adjust Timeout
```yaml
jobs:
  scrape-jobs:
    timeout-minutes: 180  # 3 hours instead of 2
```

### Customize Commit Message
```yaml
- name: Commit and push results
  run: |
    git commit -m "Your custom message - $(date '+%Y-%m-%d %H:%M:%S UTC')"
```

## 📈 Monitoring

### View Workflow Runs
1. Go to **Actions** tab
2. Click on your workflow
3. See all recent runs with status

### Check Commits
1. Go to **Commits** tab
2. Look for commits with 🤖 emoji
3. See what was updated daily

### Download Logs & Output
1. Click on a specific run
2. Scroll down to **Artifacts**
3. Download `scraper-logs` or `scraper-output`

### Check Logs Online
1. Click on a run
2. Click on **Run scraper** step
3. View real-time logs

## 🚨 Troubleshooting

### Common Issues

**Workflow fails to start:**
- Check if cron syntax is correct
- Verify repository has Actions enabled

**Scraper fails:**
- Check ChromaDB connection
- Verify all secrets are set
- Check logs in artifacts

**Git push fails:**
- Ensure `GITHUB_TOKEN` has write permissions
- Check if branch protection rules allow pushes
- Verify the workflow has proper permissions

### Debug Mode

Add debug logging to your scraper:

```python
# In jobindex_scraper.py
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('jobindex_scraper.log'),
        logging.StreamHandler()
    ]
)
```

## 🔒 Security Notes

- Never commit `.env` files to your repository
- Use repository secrets for all sensitive data
- `GITHUB_TOKEN` is automatically provided and secure
- Consider using GitHub's Dependabot for security updates
- Regularly rotate API keys

## 📅 Timezone Information

The workflow runs at **4:00 AM UTC**, which corresponds to:
- **Winter (CET)**: 5:00 AM Danish time
- **Summer (CEST)**: 6:00 AM Danish time

To adjust for your preferred time, modify the cron expression in the workflow file.

## 🎉 Next Steps

1. **Test the workflow** by manually triggering it
2. **Monitor the first few runs** to ensure everything works
3. **Check your repository commits** to see daily updates
4. **Customize** the schedule and parameters as needed
5. **Review logs regularly** to monitor performance

## 🔍 **Important Notes**

- **Only one run per day** - The cron schedule ensures this
- **Results are automatically committed** - No manual intervention needed
- **GitHub token is secure** - Automatically provided by GitHub
- **Branch protection** - Make sure your main branch allows workflow pushes

Your Jobindex scraper will now run automatically every day and push all results back to your repository! 🚀 