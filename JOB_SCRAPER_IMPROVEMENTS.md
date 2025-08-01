# Job Scraper Improvements

## Issues Fixed

### 1. Title Extraction Issues
**Problem**: Job titles were being scraped with "Jobannonce: " prefix
- **Example**: `"Jobannonce: Fleksible Frivillige - Mental Talk"`
- **Expected**: `"Fleksible Frivillige - Mental Talk"`

**Root Cause**: The scraper was using the `h1.sr-only` element which contains the full title with prefix

**Solution**: 
- Primary: Use `h4 a` selector for clean job titles
- Fallback: Clean up `h1.sr-only` by removing "Jobannonce: " prefix
- Secondary: Extract from page title if needed

### 2. Description Extraction Issues
**Problem**: Job descriptions were being scraped with "Indrykket: " prefix and other metadata
- **Example**: `"Indrykket: 28. juli 2025\nAt bidrage, hvor din hjælp gør størst forskel..."`
- **Expected**: `"At bidrage, hvor din hjælp gør størst forskel..."`

**Root Cause**: The scraper was extracting from wrong elements or not properly filtering metadata

**Solution**:
- Primary: Use `.jix_robotjob-inner p` selector for clean descriptions
- Fallback: Parse `.jix_robotjob-inner` content and filter out metadata lines
- Secondary: Use text patterns to find descriptions in page content
- Enhanced filtering: Remove common unwanted patterns like "Indrykket:", "Hentet fra", etc.

### 3. Company Extraction Issues
**Problem**: Company names were not being extracted reliably

**Solution**:
- Primary: Use `.jix-toolbar-top__company` selector
- Fallback: Extract from job title if it contains company name (e.g., "Title - Company")
- Secondary: Use text patterns to find company names

### 4. Location Extraction Issues
**Problem**: Location information was not being extracted consistently

**Solution**:
- Use `.jix_robotjob--area` selector for reliable location extraction

## Technical Improvements

### 1. Better Selector Strategy
- **Before**: Used generic selectors that often picked up wrong content
- **After**: Use specific, targeted selectors based on actual page structure

### 2. Improved Fallback Logic
- **Before**: Single fallback strategy
- **After**: Multiple fallback strategies with proper priority order

### 3. Enhanced Content Filtering
- **Before**: Basic text cleaning
- **After**: Comprehensive filtering of metadata, navigation text, and unwanted content

### 4. Better Error Handling
- **Before**: Limited error handling
- **After**: Robust error handling with detailed logging

## Page Structure Analysis

Based on analysis of the Jobindex page structure:

```html
<!-- Job Title -->
<h1 class="sr-only">Jobannonce: Fleksible Frivillige - Mental Talk</h1>
<h4><a href="...">Fleksible Frivillige - Mental Talk</a></h4>

<!-- Company -->
<div class="jix-toolbar-top__company">Mental Talk</div>

<!-- Description -->
<div class="jix_robotjob-inner">
    <p>At bidrage, hvor din hjælp gør størst forskel...</p>
</div>

<!-- Location -->
<span class="jix_robotjob--area">Herning</span>

<!-- Metadata (to be filtered out) -->
<div class="jix-toolbar__pubdate">
    Indrykket: <time>15-07-2025</time>
</div>
```

## Testing Results

### Test Job: r13240911 (Mental Talk)
- **Title**: ✅ `"Fleksible Frivillige - Mental Talk"` (no prefix)
- **Company**: ✅ `"Mental Talk"`
- **Description**: ✅ `"At bidrage, hvor din hjælp gør størst forskel, alt efter hvor behovet opstår."` (no metadata)
- **Location**: ✅ `"Herning"`

### Test Job: r13248036 (DanChurchAid)
- **Title**: ✅ `"Climate Advocacy Officer, Copenhagen"`
- **Company**: ✅ `"DanChurchAid"`
- **Description**: ✅ Clean description without metadata
- **Location**: ✅ `"København V"`

## Code Changes Summary

### Key Changes in `scrape_job_info()` method:

1. **Title Extraction**:
   ```python
   # Primary: h4 a selector
   title_element = await page.query_selector('h4 a')
   
   # Fallback: Clean up sr-only h1
   if title.startswith('Jobannonce: '):
       title = title[12:]
   ```

2. **Company Extraction**:
   ```python
   # Primary: Toolbar company div
   company_element = await page.query_selector('.jix-toolbar-top__company')
   ```

3. **Description Extraction**:
   ```python
   # Primary: Job content paragraph
   desc_element = await page.query_selector('.jix_robotjob-inner p')
   
   # Enhanced filtering
   unwanted_patterns = [
       r'Indrykket:.*?(?=\n|$)',
       r'Hentet fra.*?(?=\n|$)',
       # ... more patterns
   ]
   ```

4. **Location Extraction**:
   ```python
   # Direct selector
   location_element = await page.query_selector('.jix_robotjob--area')
   ```

## Benefits

1. **Cleaner Data**: No more metadata prefixes in titles and descriptions
2. **More Reliable**: Better success rate in extracting job information
3. **Maintainable**: Clear, targeted selectors that are easier to maintain
4. **Robust**: Multiple fallback strategies ensure data extraction even if page structure changes slightly

## Newest Job Prioritization

### Feature Added
The job scraper now prioritizes the newest jobs by `created_at` timestamp when processing jobs with missing information.

### Benefits
1. **Freshest Data First**: Process the most recently added jobs first
2. **Efficient Processing**: Focus on jobs that are most likely to still be active
3. **Configurable Limits**: Can limit processing to the newest N jobs
4. **Backward Compatible**: Original behavior still available

### Usage Examples

#### Process all jobs with missing info (newest first)
```python
await scraper.process_jobs_with_missing_info(
    newest_first=True  # Default behavior
)
```

#### Process only the newest 50 jobs
```python
await scraper.process_jobs_with_missing_info(
    newest_first=True,
    limit_newest=50
)
```

#### Process newest jobs with additional limits
```python
await scraper.process_jobs_with_missing_info(
    max_jobs=10,  # Process only 10 jobs
    newest_first=True,
    limit_newest=100  # Get from newest 100
)
```

#### Original behavior (no prioritization)
```python
await scraper.process_jobs_with_missing_info(
    newest_first=False
)
```

### New Methods Added

#### `get_jobs_with_missing_info_limited(limit: int = 100)`
Returns the newest N jobs with missing information, ordered by `created_at` descending.

#### Enhanced `process_jobs_with_missing_info()`
Now accepts additional parameters:
- `newest_first=True`: Prioritize newest jobs (default)
- `limit_newest=None`: Limit to newest N jobs (default: None, processes all)

## Job Info Timestamp Tracking

### Feature Added
The job scraper now tracks which jobs have been processed by adding a `job_info` timestamp to each job record.

### Benefits
1. **Prevent Reprocessing**: Jobs with `job_info` timestamp are automatically skipped
2. **Efficient Resource Usage**: Avoid unnecessary scraping of already processed jobs
3. **Progress Tracking**: Monitor how many jobs have been processed by the scraper
4. **Resume Capability**: Can resume processing from where it left off

### Database Schema
- **Column**: `job_info` (timestamp with time zone, nullable)
- **Purpose**: Tracks when the job was last processed by the job_info scraper
- **Format**: ISO 8601 timestamp in UTC

### How It Works
1. **Query Filtering**: Only jobs without `job_info` timestamp are selected for processing
2. **Timestamp Addition**: When a job is successfully updated, a `job_info` timestamp is added
3. **Skip Logic**: Jobs with existing `job_info` timestamp are automatically skipped

### Usage Examples

#### Check processing statistics
```python
stats = scraper.get_missing_info_stats()
print(f"Jobs processed by job_info scraper: {stats['processed_by_job_info']}")
print(f"Processing percentage: {stats['processed_percentage']:.1f}%")
```

#### Process only unprocessed jobs
```python
# This will automatically skip jobs with job_info timestamp
await scraper.process_jobs_with_missing_info(
    newest_first=True,
    limit_newest=100
)
```

### Statistics Enhanced
The statistics now include:
- **Total jobs processed by job_info scraper**: Count of jobs with `job_info` timestamp
- **Processing percentage**: Percentage of total jobs that have been processed
- **Missing info jobs**: Jobs that still need processing (no `job_info` timestamp + missing fields)

### Code Changes

#### Enhanced Database Queries
```python
# Only select jobs without job_info timestamp
response = self.supabase.table('jobs').select('*').or_(
    'company.is.null,company.eq.,company_url.is.null,company_url.eq.,description.is.null,description.eq.'
).is_('deleted_at', 'null').is_('job_info', 'null').order('created_at', desc=True).execute()
```

#### Timestamp Addition in Updates
```python
# Always add the job_info timestamp to mark this job as processed
from datetime import datetime, timezone
update_data['job_info'] = datetime.now(timezone.utc).isoformat()
```

#### Enhanced Statistics
```python
# Include job_info processing statistics
return {
    "total_jobs": total_jobs,
    "missing_info": missing_info_count,
    "missing_fields": missing_fields,
    "missing_percentage": (missing_info_count / total_jobs * 100) if total_jobs > 0 else 0,
    "processed_by_job_info": processed_by_job_info_count,
    "processed_percentage": (processed_by_job_info_count / total_jobs * 100) if total_jobs > 0 else 0
}
```

## Future Considerations

1. **Monitor Page Structure**: Jobindex may change their HTML structure, requiring selector updates
2. **Expand Patterns**: Add more company and description patterns for different job types
3. **Performance**: Consider caching successful selectors for similar job types
4. **Validation**: Add data validation to ensure extracted information meets quality standards
5. **Batch Processing**: Consider processing jobs in batches for better performance
6. **Priority Queues**: Implement more sophisticated prioritization based on job type, company size, etc.
7. **Timestamp Management**: Consider adding timestamp for different types of processing (scraping, scoring, etc.)
8. **Retry Logic**: Implement retry mechanism for failed jobs with exponential backoff 