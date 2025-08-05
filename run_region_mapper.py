#!/usr/bin/env python3
"""
Command-line interface for the Region Mapper
Allows running the region mapping process with different options
"""

import argparse
import logging
from region_mapper import RegionMapper

def setup_logging(verbose: bool = False):
    """Setup logging based on verbosity level"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def main():
    """Main function with command-line argument parsing"""
    parser = argparse.ArgumentParser(
        description="Map job locations to regions using city_to_region table"
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without making changes'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of jobs to process in each batch (default: 100)'
    )
    
    parser.add_argument(
        '--stats-only',
        action='store_true',
        help='Only show region statistics without processing jobs'
    )
    
    parser.add_argument(
        '--include-deleted',
        action='store_true',
        help='Include soft-deleted jobs in processing'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize the region mapper
        mapper = RegionMapper()
        
        # Get current stats
        logger.info("Getting current region statistics...")
        stats = mapper.get_region_stats(include_deleted=args.include_deleted)
        
        if 'error' in stats:
            logger.error(f"Error getting stats: {stats['error']}")
            return
        
        print("\n=== CURRENT REGION STATISTICS ===")
        print(f"Total jobs: {stats['total_jobs']}")
        print(f"Jobs with region: {stats['jobs_with_region']}")
        print(f"Jobs without region: {stats['jobs_without_region']}")
        print(f"Region coverage: {stats['region_coverage_percentage']:.1f}%")
        
        if stats['region_distribution']:
            print("\nRegion distribution:")
            for region, count in sorted(stats['region_distribution'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {region}: {count}")
        
        if args.stats_only:
            return
        
        # Process jobs to add regions
        if args.dry_run:
            logger.info("Starting DRY RUN - no changes will be made...")
        else:
            logger.info("Starting region mapping process...")
        
        results = mapper.process_jobs_regions(
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            include_deleted=args.include_deleted
        )
        
        if 'error' in results:
            logger.error(f"Error during processing: {results['error']}")
            return
        
        print(f"\n=== PROCESSING RESULTS ===")
        print(f"Total processed: {results['total_processed']}")
        print(f"Updated: {results['updated']}")
        print(f"Not found: {results['not_found']}")
        print(f"Errors: {results['errors']}")
        
        if not args.dry_run:
            # Get updated stats
            logger.info("Getting updated region statistics...")
            updated_stats = mapper.get_region_stats(include_deleted=args.include_deleted)
            
            if 'error' not in updated_stats:
                print(f"\n=== UPDATED REGION STATISTICS ===")
                print(f"Total jobs: {updated_stats['total_jobs']}")
                print(f"Jobs with region: {updated_stats['jobs_with_region']}")
                print(f"Jobs without region: {updated_stats['jobs_without_region']}")
                print(f"Region coverage: {updated_stats['region_coverage_percentage']:.1f}%")
        
        logger.info("Region mapping process completed successfully!")
        
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        raise

if __name__ == "__main__":
    main() 