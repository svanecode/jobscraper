# Job Embedding System

This directory contains scripts for generating and using vector embeddings for job records in your database. The system uses OpenAI's text-embedding-3-large model to create 3072-dimensional embeddings that enable semantic similarity search.

## Files Overview

- `job_embedding_generator.py` - Main script to generate embeddings for job records
- `job_similarity_search.py` - Script to demonstrate similarity search functionality
- `create_similarity_function.sql` - PostgreSQL functions for vector similarity search

## Prerequisites

1. **Database Setup**: Your Supabase database must have the `pgvector` extension enabled
2. **Environment Variables**: Set up your `.env` file with:
   ```
   SUPABASE_URL=your_supabase_url
   SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
   OPENAI_API_KEY=your_openai_api_key
   ```

## Setup Instructions

### 1. Enable pgvector Extension

First, ensure the pgvector extension is enabled in your Supabase database:

```sql
-- Enable the pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
```

### 2. Create Similarity Search Functions

Run the SQL functions in `create_similarity_function.sql` in your Supabase SQL editor:

```bash
# Copy the contents of create_similarity_function.sql and run it in Supabase SQL editor
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Generating Embeddings

To generate embeddings for relevant jobs (CFO score >= 1) that don't have them yet:

```bash
python job_embedding_generator.py
```

The script will:
- Find all jobs without embeddings that have CFO score >= 1
- Generate embeddings using OpenAI's API
- Store the embeddings in the database
- Update the `embedding_created_at` timestamp

**Configuration Options:**
- `batch_size`: Number of jobs to process in parallel (default: 5)
- `max_jobs`: Maximum jobs to process per run (default: 1000)
- `delay`: Delay between batches in seconds (default: 2.0)

**Note:** Only jobs with CFO score >= 1 will have embeddings generated, as these are the relevant jobs for your CFO services.

### Running Similarity Search

To test the similarity search functionality:

```bash
python job_similarity_search.py
```

This will demonstrate:
- Searching by text query
- Finding jobs similar to a specific job
- Displaying results with similarity scores

## Database Schema

The jobs table should have these vector-related columns:

```sql
CREATE TABLE public.jobs (
  -- ... existing columns ...
  embedding public.vector(1536) null,
  embedding_created_at timestamp with time zone null,
  -- ... other columns ...
);

-- Create vector index for similarity search
CREATE INDEX IF NOT EXISTS idx_jobs_embedding_vector 
ON public.jobs USING ivfflat (embedding vector_cosine_ops);
```

## API Functions

The system provides several PostgreSQL functions for similarity search:

### `match_jobs(query_embedding, match_threshold, match_count)`
Find jobs similar to a given embedding vector.

**Parameters:**
- `query_embedding`: Vector embedding (1536 dimensions)
- `match_threshold`: Minimum similarity score (0-1, default: 0.7)
- `match_count`: Maximum results to return (default: 10)

**Returns:** Jobs with similarity scores

### `find_similar_jobs(target_job_id, match_threshold, match_count)`
Find jobs similar to a specific job by its ID.

### `match_jobs_full(query_embedding, match_threshold, match_count)`
Same as `match_jobs` but returns all job fields.

## Example Usage in Code

```python
from job_embedding_generator import JobEmbeddingGenerator
from job_similarity_search import JobSimilaritySearch

# Generate embeddings
generator = JobEmbeddingGenerator()
await generator.generate_all_embeddings(max_jobs=50)

# Search for similar jobs
searcher = JobSimilaritySearch()
similar_jobs = await searcher.search_by_query("regnskabschef barselsvikariat", limit=5)

# Find jobs similar to a specific job
similar_jobs = searcher.search_by_job_id("job_123", limit=5)
```

## Cost Considerations

- **OpenAI API Costs**: Each embedding generation costs approximately $0.0001 per job
- **Rate Limits**: The script includes delays to respect OpenAI's rate limits
- **Batch Processing**: Process jobs in batches to optimize API usage

## Monitoring

The scripts provide detailed logging:
- Progress updates during processing
- Statistics on embedding coverage
- Error reporting for failed operations

## Troubleshooting

### Common Issues

1. **"pgvector extension not enabled"**
   - Enable the vector extension in your Supabase database

2. **"No embedding found for job"**
   - Run the embedding generator first
   - Check if the job has content to embed

3. **API rate limit errors**
   - Increase the delay between batches
   - Reduce the batch size

4. **Vector dimension mismatch**
   - Ensure you're using text-embedding-3-large (3072 dimensions)
   - Check that the vector column is defined as `vector(1536)`

### Performance Tips

- Use the `ivfflat` index for better search performance
- Process embeddings in batches to avoid overwhelming the API
- Monitor embedding coverage to ensure all jobs have embeddings

## Security Notes

- Use the service role key for embedding operations
- The embedding generator bypasses RLS for efficiency
- Embeddings contain semantic information but not sensitive data 