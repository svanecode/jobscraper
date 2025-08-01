-- Restore all soft-deleted jobs by setting deleted_at to null
-- This will make all jobs active again

UPDATE jobs 
SET deleted_at = NULL 
WHERE deleted_at IS NOT NULL;

-- Optional: Show the count of jobs that were restored
SELECT 
    COUNT(*) as restored_jobs_count,
    'All soft-deleted jobs have been restored' as message
FROM jobs 
WHERE deleted_at IS NULL; 