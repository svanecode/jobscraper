#!/usr/bin/env python3
"""
Job Embedding Generator

This script generates vector embeddings for job records in the database.
It uses OpenAI's text-embedding-ada-002 model to create embeddings from
job titles, descriptions, and company information.
"""

import asyncio
import logging
import os
import time
from typing import List, Dict, Optional
from supabase import create_client, Client
from openai import OpenAI
import numpy as np

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, continue without it

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class JobEmbeddingGenerator:
    def __init__(self, supabase_url=None, supabase_key=None, openai_api_key=None):
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
        
        # Initialize OpenAI client
        self.openai_api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        if self.openai_api_key:
            self.openai_client = OpenAI(api_key=self.openai_api_key)
            logger.info("OpenAI client initialized")
        else:
            self.openai_client = None
            logger.error("OpenAI API key not provided. Cannot proceed.")
            raise ValueError("OpenAI API key required")
    
    def get_jobs_without_embeddings(self, max_jobs=None) -> List[Dict]:
        """
        Get jobs that don't have embeddings yet and have CFO score >= 1
        
        Args:
            max_jobs: Maximum number of jobs to fetch (for testing)
        
        Returns:
            List of job dictionaries
        """
        try:
            # Get jobs that don't have embeddings, are not deleted, and have CFO score >= 1
            query = self.supabase.table('jobs').select('*').is_('deleted_at', 'null').is_('embedding', 'null').gte('cfo_score', 1)
            
            if max_jobs:
                query = query.limit(max_jobs)
            
            response = query.execute()
            
            if response.data:
                logger.info(f"Retrieved {len(response.data)} jobs without embeddings and with CFO score >= 1")
                return response.data
            else:
                logger.info("No jobs found without embeddings and with CFO score >= 1")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching jobs from database: {e}")
            return []
    
    def create_embedding_text(self, job: Dict) -> str:
        """
        Create optimal text for embedding with balanced weighting
        
        Args:
            job: Job dictionary
        
        Returns:
            Formatted text string for embedding
        """
        # Extract job data
        title = job.get('title', '') or ''
        company = job.get('company', '') or ''
        location = job.get('location', '') or ''
        description = job.get('description', '') or ''
        
        # Strip whitespace
        title = title.strip()
        company = company.strip()
        location = location.strip()
        description = description.strip()

        # Create optimal embedding text with balanced weighting
        # Strategy: Emphasize company and title while keeping full description
        # Format: Company - Title. Location. Full description with company/title repeated
        
        # Clean and prepare text components
        if not title:
            title = "Job"
        if not company:
            company = "Company"
        if not location:
            location = "Location not specified"
        
        # Create weighted description that repeats company and title for emphasis
        weighted_description = f"{company} - {title}. {description}"
        
        # Create final embedding text with enhanced searchability
        # Give maximum weight to location, company, and title by repeating them multiple times
        # This makes the embeddings more sensitive to location and company searches
        embedding_text = f"""Location: {location}
Company: {company}
Title: {title}
Location: {location}
Company: {company}
{company} - {title}
Location: {location}
Description: {weighted_description}"""
        
        # Clean up the text
        embedding_text = embedding_text.strip()
        
        # If text is too long, truncate it (OpenAI has a limit of 8191 tokens)
        if len(embedding_text) > 8000:
            # Keep the most important parts (location, company, title) and truncate description
            important_parts = f"""Location: {location}
Company: {company}
Title: {title}
Location: {location}
Company: {company}
{company} - {title}
Location: {location}
Description: {company} - {title}. """
            remaining_length = 8000 - len(important_parts)
            if remaining_length > 0:
                truncated_description = description[:remaining_length] + "..."
                embedding_text = important_parts + truncated_description
            else:
                embedding_text = important_parts + description[:100] + "..."

        return embedding_text
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for text using OpenAI API
        
        Args:
            text: Text to embed
        
        Returns:
            List of floats representing the embedding vector
        """
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            
            # Extract the embedding vector
            embedding = response.data[0].embedding
            
            logger.debug(f"Generated embedding with {len(embedding)} dimensions")
            return embedding
                
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None
    
    def update_job_embedding(self, job_id: int, embedding: List[float]) -> bool:
        """
        Update the job embedding in the database
        
        Args:
            job_id: Job ID (bigint primary key)
            embedding: Embedding vector as list of floats
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert embedding to proper format for Supabase
            embedding_array = list(embedding)  # Ensure it's a list
            
            response = self.supabase.table('jobs').update({
                'embedding': embedding_array,
                'embedding_created_at': 'now()'
            }).eq('id', job_id).execute()
            
            if response.data:
                logger.debug(f"Updated embedding for job ID {job_id}")
                return True
            else:
                logger.error(f"Failed to update embedding for job ID {job_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating embedding for job ID {job_id}: {e}")
            return False
    
    async def process_job_embedding(self, job: Dict) -> bool:
        """
        Process a single job to generate and store its embedding
        
        Args:
            job: Job dictionary
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create text for embedding
            embedding_text = self.create_embedding_text(job)
            
            if not embedding_text.strip():
                logger.warning(f"No text content for job ID {job.get('id')}, skipping")
                return False
            
            # Generate embedding
            embedding = await self.generate_embedding(embedding_text)
            
            if embedding is None:
                logger.error(f"Failed to generate embedding for job ID {job.get('id')}")
                return False
            
            # Update database
            success = self.update_job_embedding(job['id'], embedding)
            
            if success:
                logger.debug(f"Successfully processed embedding for job '{job.get('title')}' (ID: {job.get('id')})")
            
            return success
                
        except Exception as e:
            logger.error(f"Error processing job ID {job.get('id')}: {e}")
            return False
    
    async def generate_all_embeddings(self, batch_size=10, max_jobs=None, delay=1.0):
        """
        Generate embeddings for all jobs that don't have them
        
        Args:
            batch_size: Number of jobs to process in parallel
            max_jobs: Maximum number of jobs to process (for testing)
            delay: Delay between batches in seconds (to respect API rate limits)
        """
        # Get jobs without embeddings and with CFO score >= 1
        jobs = self.get_jobs_without_embeddings(max_jobs)
        
        if not jobs:
            logger.info("No jobs found without embeddings and with CFO score >= 1")
            return
        
        logger.info(f"Starting to generate embeddings for {len(jobs)} jobs with CFO score >= 1")
        
        # Process jobs in batches
        total_processed = 0
        total_errors = 0
        
        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            batch_num = i//batch_size + 1
            total_batches = (len(jobs) + batch_size - 1)//batch_size
            
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} jobs)")
            
            # Process jobs in parallel
            tasks = [self.process_job_embedding(job) for job in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for job, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.error(f"Error processing job ID {job.get('id')}: {result}")
                    total_errors += 1
                    continue
                
                if result:
                    total_processed += 1
                else:
                    total_errors += 1
            
            # Progress update
            progress = (total_processed + total_errors) / len(jobs) * 100
            logger.info(f"Progress: {progress:.1f}% ({total_processed + total_errors}/{len(jobs)})")
            
            # Add delay between batches to respect API rate limits
            if i + batch_size < len(jobs):
                await asyncio.sleep(delay)
        
        # Final summary
        logger.info("=== EMBEDDING GENERATION COMPLETE ===")
        logger.info(f"Total jobs processed (CFO score >= 1): {len(jobs)}")
        logger.info(f"Successfully processed: {total_processed}")
        logger.info(f"Errors: {total_errors}")
    
    def get_embedding_stats(self) -> Dict:
        """
        Get statistics about job embeddings (only for jobs with CFO score >= 1)
        
        Returns:
            Dictionary with embedding statistics
        """
        try:
            # Get total jobs with CFO score >= 1
            total_response = self.supabase.table('jobs').select('id', count='exact').is_('deleted_at', 'null').gte('cfo_score', 1).execute()
            total_relevant_jobs = total_response.count if total_response.count is not None else 0
            
            # Get jobs with embeddings and CFO score >= 1
            embedded_response = self.supabase.table('jobs').select('id', count='exact').is_('deleted_at', 'null').gte('cfo_score', 1).not_.is_('embedding', 'null').execute()
            embedded_relevant_jobs = embedded_response.count if embedded_response.count is not None else 0
            
            # Get jobs without embeddings but with CFO score >= 1
            jobs_needing_embeddings = total_relevant_jobs - embedded_relevant_jobs
            
            return {
                "total_relevant_jobs": total_relevant_jobs,
                "jobs_with_embeddings": embedded_relevant_jobs,
                "jobs_needing_embeddings": jobs_needing_embeddings,
                "embedding_coverage": (embedded_relevant_jobs / total_relevant_jobs * 100) if total_relevant_jobs > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting embedding stats: {e}")
            return {
                "total_relevant_jobs": 0,
                "jobs_with_embeddings": 0,
                "jobs_needing_embeddings": 0,
                "embedding_coverage": 0
            }

async def main():
    """Main function to run the embedding generator"""
    try:
        # Initialize the embedding generator
        generator = JobEmbeddingGenerator()
        
        # Print initial statistics
        stats = generator.get_embedding_stats()
        logger.info("=== INITIAL STATISTICS ===")
        logger.info(f"Total relevant jobs (CFO score >= 1): {stats['total_relevant_jobs']}")
        logger.info(f"Jobs with embeddings: {stats['jobs_with_embeddings']}")
        logger.info(f"Jobs needing embeddings: {stats['jobs_needing_embeddings']}")
        logger.info(f"Embedding coverage: {stats['embedding_coverage']:.1f}%")
        
        # Generate embeddings (limited to 1000 jobs per run)
        await generator.generate_all_embeddings(
            batch_size=5,  # Conservative batch size for API rate limits
            max_jobs=1000,  # Limited to 1000 jobs per run
            delay=2.0  # 2 second delay between batches
        )
        
        # Print final statistics
        final_stats = generator.get_embedding_stats()
        logger.info("=== FINAL STATISTICS ===")
        logger.info(f"Total relevant jobs (CFO score >= 1): {final_stats['total_relevant_jobs']}")
        logger.info(f"Jobs with embeddings: {final_stats['jobs_with_embeddings']}")
        logger.info(f"Jobs needing embeddings: {final_stats['jobs_needing_embeddings']}")
        logger.info(f"Embedding coverage: {final_stats['embedding_coverage']:.1f}%")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 