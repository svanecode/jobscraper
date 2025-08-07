-- Manual Database Schema Update: vector(1536) to vector(3072)
-- Run this in your Supabase SQL editor or database client

-- Step 1: Create a new column with the new vector type
ALTER TABLE jobs 
ADD COLUMN embedding_new vector(3072);

-- Step 2: Copy data from old column to new column (if any exists)
-- Note: This will fail if the old embeddings are 1536 dimensions, which is expected
-- The migration script handles this by clearing embeddings first
UPDATE jobs 
SET embedding_new = embedding::vector(3072) 
WHERE embedding IS NOT NULL;

-- Step 3: Drop the old column
ALTER TABLE jobs 
DROP COLUMN embedding;

-- Step 4: Rename the new column to the original name
ALTER TABLE jobs 
RENAME COLUMN embedding_new TO embedding;

-- Verify the change
SELECT column_name, data_type, character_maximum_length 
FROM information_schema.columns 
WHERE table_name = 'jobs' AND column_name = 'embedding'; 