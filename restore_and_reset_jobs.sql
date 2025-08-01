-- Restore all soft-deleted jobs and reset last_seen to created_at
-- This will make all jobs active again and reset their "last seen" to when they were first created

-- Step 1: Restore all soft-deleted jobs by setting deleted_at to null
UPDATE jobs 
SET deleted_at = NULL 
WHERE deleted_at IS NOT NULL;

-- Step 2: Reset last_seen to match created_at for all jobs
UPDATE jobs 
SET last_seen = created_at 
WHERE created_at IS NOT NULL;

-- Optional: Show the count of jobs that were restored and reset
SELECT 
    COUNT(*) as total_jobs_count,
    'All jobs restored and last_seen reset to created_at' as message
FROM jobs 
WHERE deleted_at IS NULL; 