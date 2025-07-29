# Job Scoring System for CFO Interim Services

This system automatically scores job listings based on their likelihood of needing temporary CFO/economic assistance services.

## Scoring System

Jobs are scored on a scale of 0-3:

- **3** = Akut/midlertidigt og økonomirelateret → KPMG bør tage kontakt straks
- **2** = Økonomistilling hvor behovet kunne være der  
- **1** = Lav sandsynlighed, men økonomirelateret
- **0** = Ikke økonomirelateret

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file with the following variables:

```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_ANON_KEY=your_supabase_anon_key
OPENAI_API_KEY=your_openai_api_key
```

### 3. Database Setup

Run the SQL script in your Supabase SQL editor to add the necessary columns:

```bash
# Copy the contents of add_scoring_columns.sql and run it in Supabase
```

## Usage

### Test the System

First, test with a small number of jobs:

```bash
python test_job_scorer.py
```

### Score All Jobs

Run the full scoring system:

```bash
python job_scorer.py
```

### Configuration Options

You can modify the scoring parameters in `job_scorer.py`:

- `batch_size`: Number of jobs to process in parallel (default: 5)
- `delay`: Delay between batches in seconds (default: 2.0)
- `max_jobs`: Maximum number of jobs to score (for testing)

## Database Schema

The scoring system adds two new columns to the `jobs` table:

- `cfo_score` (INTEGER): Score from 0-3
- `scored_at` (TIMESTAMP): When the job was scored

### Views

The system creates two useful views:

- `high_priority_jobs`: Jobs with score 3 (highest priority)
- `scored_jobs`: All jobs that have been scored

## API Usage

The scoring system uses OpenAI's GPT-4o-mini model with the following prompt:

```
Du arbejder i en virksomhed, der tilbyder CFO Interim Services.

Du får her et jobopslag og skal vurdere, hvor sandsynligt det er, at virksomheden har brug for midlertidig assistance til økonomifunktionen.

Vurder ud fra stillingsbetegnelse, virksomhedsnavn, lokation og jobbeskrivelse.

Giv kun én score:
- 3 = Akut/midlertidigt og økonomirelateret → KPMG bør tage kontakt straks
- 2 = Økonomistilling hvor behovet kunne være der
- 1 = Lav sandsynlighed, men økonomirelateret
- 0 = Ikke økonomirelateret

Svar KUN med et tal (0, 1, 2 eller 3).
```

## Cost Considerations

- Uses OpenAI GPT-4o-mini model (cost-effective with good performance)
- Can be changed to GPT-3.5-turbo for even faster/cheaper processing
- Rate limiting is built-in to respect API limits
- Batch processing reduces API calls

## Monitoring

The system provides detailed logging including:

- Progress updates during scoring
- Score distribution statistics
- Error handling and reporting
- Final summary with statistics

## Integration

The scoring system can be integrated into the existing pipeline by:

1. Adding it to `run_full_pipeline.py`
2. Setting up automated scoring via GitHub Actions
3. Creating scheduled jobs for regular scoring updates

## Troubleshooting

### Common Issues

1. **OpenAI API Key Missing**: Ensure `OPENAI_API_KEY` is set in environment
2. **Supabase Connection**: Verify Supabase credentials are correct
3. **Rate Limiting**: Increase delay between batches if hitting API limits
4. **Database Schema**: Ensure scoring columns exist in the database

### Debug Mode

Enable debug logging by modifying the logging level in the script:

```python
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
``` 