#!/usr/bin/env python3
"""
Region Mapper for Job Scraper
Maps job locations to regions using the city_to_region table and updates the region column in jobs table
"""

import logging
import os
from typing import Dict, List, Optional
from supabase import create_client, Client

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, continue without it

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RegionMapper:
    def __init__(self, supabase_url=None, supabase_key=None):
        # Initialize Supabase client
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY')
        
        if self.supabase_url and self.supabase_key:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            # Log which key type is being used
            if os.getenv('SUPABASE_SERVICE_ROLE_KEY'):
                logger.info("Supabase client initialized with SERVICE_ROLE_KEY (RLS bypass)")
            else:
                logger.info("Supabase client initialized with ANON_KEY")
        else:
            self.supabase = None
            logger.error("Supabase credentials not provided. Cannot proceed.")
            raise ValueError("Supabase credentials required")
        
        # Cache for city to region mappings
        self.city_to_region_cache: Dict[str, str] = {}
    
    def load_city_to_region_mappings(self) -> Dict[str, str]:
        """
        Load all city to region mappings from the city_to_region table
        
        Returns:
            Dictionary mapping city names to region names
        """
        try:
            response = self.supabase.table('city_to_region').select('city, region').execute()
            
            if response.data:
                mappings = {item['city'].lower().strip(): item['region'] for item in response.data}
                logger.info(f"Loaded {len(mappings)} city to region mappings")
                self.city_to_region_cache = mappings
                return mappings
            else:
                logger.warning("No city to region mappings found in database")
                return {}
                
        except Exception as e:
            logger.error(f"Error loading city to region mappings: {e}")
            return {}
    
    def get_region_for_location(self, location: str) -> Optional[str]:
        """
        Get the region for a given location by looking it up in the city_to_region mappings
        
        Args:
            location: The location string to look up
            
        Returns:
            The region name if found, None otherwise
        """
        if not location:
            return None
        
        # Clean and normalize the location
        clean_location = location.lower().strip()
        
        # Direct match
        if clean_location in self.city_to_region_cache:
            return self.city_to_region_cache[clean_location]
        
        # Try partial matches (in case location contains additional text)
        for city, region in self.city_to_region_cache.items():
            if city in clean_location or clean_location in city:
                return region
        
        return None
    
    def get_jobs_without_regions(self, limit: Optional[int] = None, last_id: Optional[int] = None, include_deleted: bool = False) -> List[Dict]:
        """
        Get jobs that don't have a region set using cursor-based pagination
        
        Args:
            limit: Optional limit on number of jobs to return
            last_id: ID of the last processed job (for cursor-based pagination)
            include_deleted: Whether to include soft-deleted jobs
            
        Returns:
            List of job dictionaries without regions
        """
        try:
            # Get jobs where region is null or empty array
            query = self.supabase.table('jobs').select('id, location, region').or_(
                'region.is.null,region.eq.{}'
            ).order('id')
            
            # Only filter by deleted_at if not including deleted jobs
            if not include_deleted:
                query = query.is_('deleted_at', 'null')
            
            # Use cursor-based pagination
            if last_id is not None:
                query = query.gt('id', last_id)
            
            if limit:
                query = query.limit(limit)
            
            response = query.execute()
            
            if response.data:
                logger.info(f"Found {len(response.data)} jobs without regions (last_id: {last_id}, include_deleted: {include_deleted})")
                return response.data
            else:
                logger.info("No jobs without regions found")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching jobs without regions: {e}")
            return []
    
    def update_job_region(self, job_id: str, region: str) -> bool:
        """
        Update the region for a specific job
        
        Args:
            job_id: The job ID to update
            region: The region to set (will be stored as array)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Store region as an array since the column is text[]
            response = self.supabase.table('jobs').update({'region': [region]}).eq('id', job_id).execute()
            
            if response.data:
                logger.debug(f"Updated region for job {job_id} to '{region}'")
                return True
            else:
                logger.warning(f"No job found with ID {job_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating region for job {job_id}: {e}")
            return False
    
    def process_jobs_regions(self, batch_size: int = 100, dry_run: bool = False, include_deleted: bool = False) -> Dict:
        """
        Process all jobs without regions and update them with the appropriate region
        
        Args:
            batch_size: Number of jobs to process in each batch
            dry_run: If True, only show what would be updated without making changes
            include_deleted: Whether to include soft-deleted jobs
            
        Returns:
            Dictionary with processing statistics
        """
        # Load city to region mappings
        mappings = self.load_city_to_region_mappings()
        if not mappings:
            logger.error("No city to region mappings available. Cannot proceed.")
            return {"error": "No mappings available"}
        
        stats = {
            "total_processed": 0,
            "updated": 0,
            "not_found": 0,
            "errors": 0,
            "dry_run": dry_run
        }
        
        last_id = None
        while True:
            # Get batch of jobs without regions
            jobs = self.get_jobs_without_regions(limit=batch_size, last_id=last_id, include_deleted=include_deleted)
            if not jobs:
                break
            
            logger.info(f"Processing batch of {len(jobs)} jobs (last_id: {last_id})")
            
            for job in jobs:
                job_id = job['id']
                location = job.get('location', '')
                
                stats["total_processed"] += 1
                
                # Find region for this location
                region = self.get_region_for_location(location)
                
                if region:
                    if not dry_run:
                        success = self.update_job_region(job_id, region)
                        if success:
                            stats["updated"] += 1
                        else:
                            stats["errors"] += 1
                    else:
                        stats["updated"] += 1
                        logger.info(f"Would update job {job_id} (location: '{location}') -> region: '{region}'")
                else:
                    stats["not_found"] += 1
                    logger.debug(f"No region found for job {job_id} with location: '{location}'")
                
                # Update last_id for cursor-based pagination
                last_id = job_id
            
            # If we got fewer jobs than the batch size, we've processed all jobs
            if len(jobs) < batch_size:
                break
        
        logger.info(f"Processing complete. Stats: {stats}")
        return stats
    
    def get_region_stats(self, include_deleted: bool = False) -> Dict:
        """
        Get statistics about region distribution in jobs table
        
        Args:
            include_deleted: Whether to include soft-deleted jobs
            
        Returns:
            Dictionary with region statistics
        """
        try:
            # Get total jobs count
            if include_deleted:
                total_response = self.supabase.table('jobs').select('id', count='exact').execute()
            else:
                total_response = self.supabase.table('jobs').select('id', count='exact').is_('deleted_at', 'null').execute()
            total_jobs = total_response.count if total_response.count is not None else 0
            
            # Get jobs with regions (not null and not empty array)
            if include_deleted:
                with_region_response = self.supabase.table('jobs').select('id', count='exact').not_.is_('region', 'null').not_.eq('region', '{}').execute()
            else:
                with_region_response = self.supabase.table('jobs').select('id', count='exact').not_.is_('region', 'null').not_.eq('region', '{}').is_('deleted_at', 'null').execute()
            jobs_with_region = with_region_response.count if with_region_response.count is not None else 0
            
            # Get jobs without regions (null or empty array)
            if include_deleted:
                without_region_response = self.supabase.table('jobs').select('id', count='exact').or_('region.is.null,region.eq.{}').execute()
            else:
                without_region_response = self.supabase.table('jobs').select('id', count='exact').or_('region.is.null,region.eq.{}').is_('deleted_at', 'null').execute()
            jobs_without_region = without_region_response.count if without_region_response.count is not None else 0
            
            # Get region distribution
            if include_deleted:
                region_distribution_response = self.supabase.table('jobs').select('region').not_.is_('region', 'null').not_.eq('region', '{}').execute()
            else:
                region_distribution_response = self.supabase.table('jobs').select('region').not_.is_('region', 'null').not_.eq('region', '{}').is_('deleted_at', 'null').execute()
            
            region_counts = {}
            if region_distribution_response.data:
                for job in region_distribution_response.data:
                    regions = job.get('region')
                    if regions and isinstance(regions, list):
                        for region in regions:
                            if region:
                                region_counts[region] = region_counts.get(region, 0) + 1
            
            stats = {
                "total_jobs": total_jobs,
                "jobs_with_region": jobs_with_region,
                "jobs_without_region": jobs_without_region,
                "region_coverage_percentage": (jobs_with_region / total_jobs * 100) if total_jobs > 0 else 0,
                "region_distribution": region_counts
            }
            
            logger.info(f"Region stats: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error getting region stats: {e}")
            return {"error": str(e)}

def main():
    """Main function to run the region mapping process"""
    try:
        # Initialize the region mapper
        mapper = RegionMapper()
        
        # Get current stats
        logger.info("Getting current region statistics...")
        stats = mapper.get_region_stats()
        logger.info(f"Current stats: {stats}")
        
        # Process jobs to add regions
        logger.info("Starting region mapping process...")
        results = mapper.process_jobs_regions(batch_size=100, dry_run=False)
        
        # Get updated stats
        logger.info("Getting updated region statistics...")
        updated_stats = mapper.get_region_stats()
        logger.info(f"Updated stats: {updated_stats}")
        
        logger.info("Region mapping process completed successfully!")
        
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        raise

if __name__ == "__main__":
    main() 