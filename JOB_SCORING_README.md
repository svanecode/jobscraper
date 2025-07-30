# Job Scoring Scripts

This directory contains scripts for scoring jobs using AI-powered analysis to identify potential CFO interim service opportunities.

## 📋 Overview

The job scoring system analyzes job postings to determine their relevance for KPMG's interim CFO services. Jobs are scored on a scale of 0-3:

- **Score 3** 🟢: High relevance (urgent/temporary finance need) - Contact immediately!
- **Score 2** 🟠: Medium relevance (finance position with potential need)
- **Score 1** 🟡: Low relevance (finance-related but unlikely need)
- **Score 0** ❌: Not relevant (not finance-related or consulting firm)

## 🚀 Quick Start

### Prerequisites

1. **Environment Variables**: Set up your environment variables:
   ```bash
   export SUPABASE_URL="your_supabase_url"
   export SUPABASE_ANON_KEY="your_supabase_anon_key"
   export OPENAI_API_KEY="your_openai_api_key"
   ```

   Or create a `.env` file:
   ```bash
   SUPABASE_URL=your_supabase_url
   SUPABASE_ANON_KEY=your_supabase_anon_key
   OPENAI_API_KEY=your_openai_api_key
   ```

2. **Dependencies**: Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Scripts

#### Option 1: Score exactly 10 jobs
```bash
python score_10_jobs.py
```

#### Option 2: Score custom number of jobs
```bash
python run_job_scoring.py 5        # Score 5 jobs
python run_job_scoring.py 15       # Score 15 jobs
python run_job_scoring.py          # Score 10 jobs (default)
```

#### Option 3: Use command-line arguments
```bash
python run_job_scoring.py --count 20
python run_job_scoring.py --help
```

## 📁 Script Files

### `score_10_jobs.py`
- **Purpose**: Score exactly 10 jobs with detailed output
- **Features**:
  - Detailed job information display
  - Real-time progress updates
  - Comprehensive summary statistics
  - Error handling and logging
  - Automatic log file creation

### `run_job_scoring.py`
- **Purpose**: Command-line interface for flexible job scoring
- **Features**:
  - Customizable number of jobs to score
  - Command-line argument parsing
  - Safety warnings for large batches
  - User confirmation for high-volume scoring

### `job_scorer.py`
- **Purpose**: Core scoring engine and database integration
- **Features**:
  - OpenAI API integration
  - Supabase database operations
  - Batch processing capabilities
  - Scoring statistics

## 📊 Output Examples

### Job Details Display
```
================================================================================
📋 JOB DETAILS
================================================================================
🆔 Job ID: abc123
📝 Title: Interim Regnskabschef
🏢 Company: TechCorp A/S
📍 Location: København
⭐ Score: 3 - 🟢 High relevance (urgent/temporary finance need)
📄 Description: Vi søger en erfaren regnskabschef til et barselsvikariat...
================================================================================
```

### Summary Statistics
```
📊 SCORING SUMMARY
================================================================================
⏰ Completed at: 2024-01-15 14:30:25
📋 Total jobs processed: 10
✅ Successfully scored: 10
❌ Errors: 0
📈 Success rate: 100.0%

📊 Score Distribution:
  Score 0 (Not relevant): 3 jobs (30.0%)
  Score 1 (Low relevance): 2 jobs (20.0%)
  Score 2 (Medium relevance): 3 jobs (30.0%)
  Score 3 (High relevance): 2 jobs (20.0%)

📊 Average Score: 1.40

🎯 High-priority jobs (score 3): 2
   These jobs should be contacted immediately!
```

## 🔧 Configuration

### Environment Variables
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_ANON_KEY`: Your Supabase anonymous key
- `OPENAI_API_KEY`: Your OpenAI API key

### Scoring Parameters
- **Model**: GPT-4o (optimized for accuracy)
- **Temperature**: 0.1 (low for consistent scoring)
- **Max Tokens**: 10 (sufficient for score output)
- **Rate Limiting**: 2-second delay between API calls

### Database Schema
The scripts expect a `jobs` table with the following columns:
- `job_id`: Unique job identifier
- `title`: Job title
- `company`: Company name
- `location`: Job location
- `description`: Job description
- `cfo_score`: Scoring result (0-3)
- `scored_at`: Timestamp when scored
- `deleted_at`: Soft delete timestamp

## 📝 Logging

Both scripts create detailed logs:
- **Console Output**: Real-time progress and results
- **Log Files**: Timestamped log files (e.g., `job_scoring_20240115_143025.log`)
- **Log Level**: INFO (configurable)

## ⚠️ Important Notes

1. **API Costs**: Each job scoring uses 1 OpenAI API call
2. **Rate Limits**: Scripts include delays to respect API rate limits
3. **Data Priority**: Unscored jobs are prioritized over already-scored jobs
4. **Error Handling**: Failed scorings are logged but don't stop the process
5. **Database Updates**: Scores are automatically saved to the database

## 🛠️ Troubleshooting

### Common Issues

1. **Missing Environment Variables**
   ```
   ❌ Failed to initialize JobScorer: Supabase credentials required
   ```
   **Solution**: Set up environment variables or .env file

2. **Database Connection Issues**
   ```
   ❌ Error fetching jobs from database: connection error
   ```
   **Solution**: Check Supabase credentials and network connection

3. **OpenAI API Errors**
   ```
   ❌ Error scoring job: API rate limit exceeded
   ```
   **Solution**: Wait and retry, or reduce batch size

4. **No Jobs Found**
   ```
   ❌ No jobs found to score!
   ```
   **Solution**: Check if jobs exist in database and are not deleted

### Debug Mode
To enable debug logging, modify the logging level in the scripts:
```python
logging.basicConfig(level=logging.DEBUG, ...)
```

## 📈 Performance

- **Typical Speed**: ~2-3 seconds per job (including API delay)
- **Batch Size**: Recommended 10-20 jobs per run
- **API Usage**: 1 call per job scored
- **Database**: Minimal impact (one update per scored job)

## 🔄 Automation

For automated scoring, consider:
1. **Cron Jobs**: Schedule regular scoring runs
2. **GitHub Actions**: Automated scoring on schedule
3. **Webhooks**: Trigger scoring on new job additions

Example cron job (daily at 9 AM):
```bash
0 9 * * * cd /path/to/JobindexV2 && python run_job_scoring.py 20
``` 