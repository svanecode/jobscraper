-- Create similarity search functions for semantic job search
-- Run this in your Supabase SQL editor

-- Function to find jobs similar to a given embedding vector
CREATE OR REPLACE FUNCTION match_jobs(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    id bigint,
    title text,
    company text,
    location text,
    cfo_score integer,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        j.id,
        j.title,
        j.company,
        j.location,
        j.cfo_score,
        1 - (j.embedding <=> query_embedding) as similarity
    FROM jobs j
    WHERE 
        j.embedding IS NOT NULL
        AND j.deleted_at IS NULL
        AND 1 - (j.embedding <=> query_embedding) > match_threshold
    ORDER BY j.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function to find jobs similar to a given embedding vector (returns all fields)
CREATE OR REPLACE FUNCTION match_jobs_full(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    id bigint,
    title text,
    company text,
    location text,
    description text,
    cfo_score integer,
    embedding vector(1536),
    embedding_created_at timestamptz,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        j.id,
        j.title,
        j.company,
        j.location,
        j.description,
        j.cfo_score,
        j.embedding,
        j.embedding_created_at,
        1 - (j.embedding <=> query_embedding) as similarity
    FROM jobs j
    WHERE 
        j.embedding IS NOT NULL
        AND j.deleted_at IS NULL
        AND 1 - (j.embedding <=> query_embedding) > match_threshold
    ORDER BY j.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function to find jobs similar to a specific job by ID
CREATE OR REPLACE FUNCTION find_similar_jobs(
    target_job_id bigint,
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    id bigint,
    title text,
    company text,
    location text,
    cfo_score integer,
    similarity float
)
LANGUAGE plpgsql
AS $$
DECLARE
    target_embedding vector(1536);
BEGIN
    -- Get the embedding of the target job
    SELECT embedding INTO target_embedding
    FROM jobs
    WHERE id = target_job_id AND deleted_at IS NULL;
    
    -- If no embedding found, return empty
    IF target_embedding IS NULL THEN
        RETURN;
    END IF;
    
    -- Return similar jobs
    RETURN QUERY
    SELECT 
        j.id,
        j.title,
        j.company,
        j.location,
        j.cfo_score,
        1 - (j.embedding <=> target_embedding) as similarity
    FROM jobs j
    WHERE 
        j.id != target_job_id
        AND j.embedding IS NOT NULL
        AND j.deleted_at IS NULL
        AND 1 - (j.embedding <=> target_embedding) > match_threshold
    ORDER BY j.embedding <=> target_embedding
    LIMIT match_count;
END;
$$;

-- Function to search jobs by text (for backward compatibility)
CREATE OR REPLACE FUNCTION match_jobs_text(
    search_text text,
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    id bigint,
    title text,
    company text,
    location text,
    cfo_score integer,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- This function is a placeholder for text-based search
    -- In practice, you would need to generate embeddings for the search text
    -- For now, it returns an empty result
    RETURN QUERY
    SELECT 
        j.id,
        j.title,
        j.company,
        j.location,
        j.cfo_score,
        0.0 as similarity
    FROM jobs j
    WHERE FALSE; -- Always return empty for now
END;
$$;

-- Grant permissions to authenticated users
GRANT EXECUTE ON FUNCTION match_jobs(vector(1536), float, int) TO authenticated;
GRANT EXECUTE ON FUNCTION match_jobs_full(vector(1536), float, int) TO authenticated;
GRANT EXECUTE ON FUNCTION find_similar_jobs(bigint, float, int) TO authenticated;
GRANT EXECUTE ON FUNCTION match_jobs_text(text, float, int) TO authenticated; 