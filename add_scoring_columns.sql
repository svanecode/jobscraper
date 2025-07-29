-- Add columns for job scoring to the jobs table
-- Run this script in your Supabase SQL editor

-- Add CFO score column (0-3)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cfo_score INTEGER CHECK (cfo_score >= 0 AND cfo_score <= 3);

-- Add timestamp for when the job was scored
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS scored_at TIMESTAMP WITH TIME ZONE;

-- Create index for faster queries on scored jobs
CREATE INDEX IF NOT EXISTS idx_jobs_cfo_score ON jobs(cfo_score);
CREATE INDEX IF NOT EXISTS idx_jobs_scored_at ON jobs(scored_at);

-- Create index for high-priority jobs (score 3)
CREATE INDEX IF NOT EXISTS idx_jobs_high_priority ON jobs(cfo_score) WHERE cfo_score = 3;

-- Add comment to document the scoring system
COMMENT ON COLUMN jobs.cfo_score IS 'CFO Interim Services score: 3=Akut/midlertidigt, 2=Økonomistilling, 1=Lav sandsynlighed, 0=Ikke økonomirelateret';
COMMENT ON COLUMN jobs.scored_at IS 'Timestamp when the job was scored';

-- Optional: Create a view for high-priority jobs
CREATE OR REPLACE VIEW high_priority_jobs AS
SELECT 
    job_id,
    title,
    company,
    location,
    description,
    cfo_score,
    scored_at,
    created_at
FROM jobs 
WHERE cfo_score = 3 
ORDER BY scored_at DESC;

-- Optional: Create a view for all scored jobs
CREATE OR REPLACE VIEW scored_jobs AS
SELECT 
    job_id,
    title,
    company,
    location,
    description,
    cfo_score,
    scored_at,
    created_at
FROM jobs 
WHERE cfo_score IS NOT NULL
ORDER BY cfo_score DESC, scored_at DESC; 