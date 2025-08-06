#!/usr/bin/env python3
"""
Regenerate embeddings for Aarhus jobs with improved location weighting
"""

import asyncio
import logging
import os
from typing import List, Dict, Optional
from supabase import create_client, Client
from openai import OpenAI

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AarhusEmbeddingRegenerator:
    def __init__(self):
        # Initialize Supabase client
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        
        # Initialize OpenAI client
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set")
        
        self.openai_client = OpenAI(api_key=openai_api_key)
        
        logger.info("AarhusEmbeddingRegenerator initialized")

    def create_embedding_text(self, job: Dict) -> str:
        """
        Create optimal text for embedding with location emphasis
        """
        title = job.get('title', '') or ''
        company = job.get('company', '') or ''
        location = job.get('location', '') or ''
        description = job.get('description', '') or ''
        
        # Strip whitespace
        title = title.strip()
        company = company.strip()
        location = location.strip()
        description = description.strip()
        
        if not title:
            title = "Job"
        if not company:
            company = "Company"
        if not location:
            location = "Location not specified"
        
        # Create weighted description that repeats company and title for emphasis
        weighted_description = f"{company} - {title}. {description}"
        
        # Create final embedding text with location emphasis
        # Give more weight to location by repeating it and putting it first
        embedding_text = f"Location: {location}\n{company} - {title}\nLocation: {location}\nDescription: {weighted_description}"
        
        embedding_text = embedding_text.strip()
        
        # If text is too long, truncate it
        if len(embedding_text) > 8000:
            important_parts = f"Location: {location}\n{company} - {title}\nLocation: {location}\nDescription: {company} - {title}. "
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
        """
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            embedding = response.data[0].embedding
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None

    def update_job_embedding(self, job_id: int, embedding: List[float]) -> bool:
        """
        Update the job embedding in the database
        """
        try:
            embedding_array = list(embedding)
            
            response = self.supabase.table('jobs').update({
                'embedding': embedding_array,
                'embedding_created_at': 'now()'
            }).eq('id', job_id).execute()
            
            if response.data:
                logger.info(f"✅ Successfully updated embedding for job ID {job_id}")
                return True
            else:
                logger.error(f"❌ Failed to update embedding for job ID {job_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating embedding for job ID {job_id}: {e}")
            return False

    def get_aarhus_jobs(self) -> List[Dict]:
        """
        Get all Aarhus jobs with CFO score >= 1
        """
        try:
            response = self.supabase.table('jobs').select('*').ilike('location', '%aarhus%').gte('cfo_score', 1).execute()
            jobs = response.data
            logger.info(f"Found {len(jobs)} Aarhus jobs with CFO score >= 1")
            return jobs
        except Exception as e:
            logger.error(f"Error fetching Aarhus jobs: {e}")
            return []

    async def process_job_embedding(self, job: Dict) -> bool:
        """
        Process a single job to generate and store its embedding
        """
        try:
            job_id = job.get('id')
            title = job.get('title', 'Unknown')
            
            logger.info(f"Processing: {title} (ID: {job_id})")
            
            # Create text for embedding
            embedding_text = self.create_embedding_text(job)
            
            if not embedding_text.strip():
                logger.warning(f"No text content for job ID {job_id}, skipping")
                return False
            
            # Generate embedding
            embedding = await self.generate_embedding(embedding_text)
            
            if embedding is None:
                logger.error(f"Failed to generate embedding for job ID {job_id}")
                return False
            
            # Update database
            success = self.update_job_embedding(job_id, embedding)
            return success
                
        except Exception as e:
            logger.error(f"Error processing job ID {job.get('id')}: {e}")
            return False

    async def regenerate_aarhus_embeddings(self):
        """
        Regenerate embeddings for all Aarhus jobs
        """
        try:
            logger.info("🚀 Starting Aarhus embedding regeneration...")
            
            # Get Aarhus jobs
            jobs = self.get_aarhus_jobs()
            
            if not jobs:
                logger.warning("No Aarhus jobs found")
                return
            
            logger.info(f"📊 Processing {len(jobs)} Aarhus jobs...")
            
            # Process jobs sequentially to avoid rate limits
            successful = 0
            failed = 0
            
            for i, job in enumerate(jobs, 1):
                logger.info(f"Progress: {i}/{len(jobs)} ({i/len(jobs)*100:.1f}%)")
                
                success = await self.process_job_embedding(job)
                
                if success:
                    successful += 1
                else:
                    failed += 1
                
                # Small delay to respect API rate limits
                await asyncio.sleep(0.5)
            
            logger.info("=== AARHUS EMBEDDING REGENERATION COMPLETE ===")
            logger.info(f"Total jobs processed: {len(jobs)}")
            logger.info(f"Successfully processed: {successful}")
            logger.info(f"Failed: {failed}")
            
        except Exception as e:
            logger.error(f"Error in regenerate_aarhus_embeddings: {e}")

async def main():
    """
    Main function
    """
    try:
        regenerator = AarhusEmbeddingRegenerator()
        await regenerator.regenerate_aarhus_embeddings()
        
    except Exception as e:
        logger.error(f"Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 