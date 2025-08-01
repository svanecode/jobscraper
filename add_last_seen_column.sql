-- Add last_seen column to jobs table
-- This column tracks when a job was last successfully accessed/scraped

ALTER TABLE jobs ADD COLUMN last_seen TIMESTAMP WITH TIME ZONE;

-- Create index for efficient queries on last_seen
CREATE INDEX idx_jobs_last_seen ON jobs(last_seen);

-- Update existing jobs to set last_seen to created_at for jobs that haven't been deleted
UPDATE jobs 
SET last_seen = created_at 
WHERE deleted_at IS NULL AND last_seen IS NULL;

-- Add comment to document the column
COMMENT ON COLUMN jobs.last_seen IS 'Timestamp when job was last successfully accessed/scraped. Used for automatic cleanup of old jobs.'; 