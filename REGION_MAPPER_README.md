# Region Mapper for Jobindex

This script maps job locations to regions using the `city_to_region` table and updates the `region` column in the `jobs` table.

## Overview

The Region Mapper consists of two main files:
- `region_mapper.py` - The core RegionMapper class with all functionality
- `run_region_mapper.py` - Command-line interface for easy usage

## Prerequisites

1. **Environment Variables**: Make sure you have the following environment variables set in your `.env` file:
   ```
   SUPABASE_URL=your_supabase_url
   SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
   ```

2. **Database Tables**: Ensure you have:
   - `jobs` table with columns: `id`, `location`, `region`, `deleted_at`
   - `city_to_region` table with columns: `city`, `region`

## Usage

### Basic Usage

Run the region mapper to process all jobs without regions:

```bash
python run_region_mapper.py
```

### Command Line Options

#### Dry Run (Recommended First Step)
Test what would be updated without making changes:

```bash
python run_region_mapper.py --dry-run
```

#### View Statistics Only
See current region coverage without processing:

```bash
python run_region_mapper.py --stats-only
```

#### Custom Batch Size
Process jobs in smaller or larger batches:

```bash
python run_region_mapper.py --batch-size 50
```

#### Verbose Logging
Get detailed logging information:

```bash
python run_region_mapper.py --verbose
```

#### Combine Options
You can combine multiple options:

```bash
python run_region_mapper.py --dry-run --verbose --batch-size 200
```

## How It Works

1. **Load Mappings**: The script loads all city-to-region mappings from the `city_to_region` table
2. **Find Jobs**: Identifies jobs that don't have a region set (null or empty)
3. **Match Locations**: For each job location, tries to find a matching city in the mappings
4. **Update Database**: Updates the `region` column for matched jobs
5. **Report Results**: Provides statistics on the processing results

## Matching Logic

The script uses the following matching strategy:
1. **Exact Match**: Direct match of the location string (case-insensitive)
2. **Partial Match**: If the location contains a city name or vice versa

Example matches:
- Location: "København" → Region: "Hovedstaden"
- Location: "Software Developer in Aarhus" → Region: "Midtjylland"
- Location: "Odense, Denmark" → Region: "Syddanmark"

## Output

The script provides detailed output including:

### Statistics
- Total jobs in database
- Jobs with/without regions
- Region coverage percentage
- Distribution of regions

### Processing Results
- Total jobs processed
- Number of jobs updated
- Number of jobs where no region was found
- Number of errors encountered

## Error Handling

The script includes comprehensive error handling:
- Database connection errors
- Missing environment variables
- Invalid data in tables
- Network timeouts

## Performance

- **Batch Processing**: Jobs are processed in configurable batches (default: 100)
- **Caching**: City-to-region mappings are cached in memory
- **Efficient Queries**: Uses optimized database queries with proper indexing

## Troubleshooting

### Common Issues

1. **"Supabase credentials not provided"**
   - Check your `.env` file has the correct environment variables
   - Ensure the file is in the same directory as the script

2. **"No city to region mappings found"**
   - Verify the `city_to_region` table exists and has data
   - Check table permissions

3. **"No jobs without regions found"**
   - All jobs already have regions assigned
   - Check if the `region` column exists in the `jobs` table

### Debug Mode

Run with verbose logging to see detailed information:

```bash
python run_region_mapper.py --verbose --dry-run
```

## Example Output

```
=== CURRENT REGION STATISTICS ===
Total jobs: 15000
Jobs with region: 8000
Jobs without region: 7000
Region coverage: 53.3%

Region distribution:
  Hovedstaden: 3500
  Midtjylland: 2500
  Syddanmark: 1200
  Nordjylland: 800

=== PROCESSING RESULTS ===
Total processed: 7000
Updated: 6500
Not found: 450
Errors: 50
```

## Integration

The RegionMapper class can be imported and used in other scripts:

```python
from region_mapper import RegionMapper

mapper = RegionMapper()
stats = mapper.get_region_stats()
results = mapper.process_jobs_regions(batch_size=50, dry_run=True)
``` 