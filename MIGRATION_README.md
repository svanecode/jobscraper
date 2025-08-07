# Migration Guide: text-embedding-ada-002 to text-embedding-3-large

This guide will help you migrate your database from `text-embedding-ada-002` (1536 dimensions) to `text-embedding-3-large` (3072 dimensions).

## ⚠️ Important Notes

- **Backup your database** before running this migration
- The migration will **clear all existing embeddings** and regenerate them
- This process may take some time depending on the number of jobs in your database
- Make sure you have sufficient OpenAI API credits for regenerating all embeddings

## Prerequisites

1. **Environment Variables**: Ensure your `.env` file contains:
   ```
   SUPABASE_URL=your_supabase_url
   SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
   OPENAI_API_KEY=your_openai_api_key
   ```

2. **Dependencies**: Make sure you have the required packages:
   ```bash
   pip install supabase openai python-dotenv
   ```

## Migration Options

### Option 1: Automated Migration (Recommended)

Use the automated migration script:

```bash
# Test with a small number of jobs first
python migrate_to_embedding_v3.py 10

# Run full migration (all jobs)
python migrate_to_embedding_v3.py
```

The script will:
1. ✅ Update database schema from `vector(1536)` to `vector(3072)`
2. ✅ Clear all existing embeddings
3. ✅ Regenerate all embeddings using `text-embedding-3-large`
4. ✅ Verify the migration was successful

### Option 2: Manual Migration

If you prefer to do it manually:

1. **Update Database Schema**:
   - Open your Supabase SQL editor
   - Run the SQL commands from `update_schema_manual.sql`
   - Or execute them step by step in your database client

2. **Clear Existing Embeddings**:
   ```sql
   UPDATE jobs SET embedding = NULL;
   ```

3. **Regenerate Embeddings**:
   ```bash
   python job_embedding_generator.py
   ```

## What the Migration Does

### Database Schema Changes
- Changes the `embedding` column from `vector(1536)` to `vector(3072)`
- This is necessary because `text-embedding-3-large` produces 3072-dimensional vectors

### Embedding Regeneration
- Clears all existing embeddings (they're incompatible with the new dimensions)
- Regenerates embeddings using `text-embedding-3-large` for all jobs
- Uses the same text combination: `title + company + location + description`

### Verification
- Tests that the new vector column accepts 3072-dimensional vectors
- Counts how many jobs have embeddings after migration
- Provides detailed logging throughout the process

## Benefits of text-embedding-3-large

- **Better semantic understanding**: More accurate representation of text meaning
- **Improved search results**: Better matching between queries and job descriptions
- **Higher quality embeddings**: 3072 dimensions vs 1536 dimensions
- **Better performance**: More recent model with improved training

## Troubleshooting

### Common Issues

1. **"Vector column does not accept 3072-dimensional vectors"**
   - The schema update failed. Check your database permissions
   - Try running the manual SQL commands

2. **"OpenAI API key not provided"**
   - Check your `.env` file has the correct `OPENAI_API_KEY`

3. **"Supabase credentials required"**
   - Check your `.env` file has the correct `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`

4. **Rate limiting errors**
   - The script includes delays to avoid rate limiting
   - If you still get errors, increase the delay in the script

### Rollback Plan

If something goes wrong, you can rollback:

1. **Restore from backup** (recommended)
2. **Or manually revert schema**:
   ```sql
   ALTER TABLE jobs DROP COLUMN embedding;
   ALTER TABLE jobs ADD COLUMN embedding vector(1536);
   ```

## Post-Migration

After successful migration:

1. **Test the semantic search**:
   ```bash
   python Semantic/interactive_search.py
   ```

2. **Verify search results** are working correctly

3. **Monitor performance** - the new embeddings should provide better search results

## Cost Estimation

- **text-embedding-3-large** costs approximately $0.00013 per 1K tokens
- For 1000 jobs with average 500 tokens each: ~$0.065
- For 10,000 jobs: ~$0.65

## Support

If you encounter issues:
1. Check the logs for detailed error messages
2. Verify your environment variables are correct
3. Test with a small number of jobs first
4. Ensure you have sufficient OpenAI API credits 