#!/usr/bin/env python3
"""
Migration Script: text-embedding-ada-002 to text-embedding-3-large

This script migrates the database from text-embedding-ada-002 (1536 dimensions) 
to text-embedding-3-large (3072 dimensions).

Steps:
1. Update database schema from vector(1536) to vector(3072)
2. Clear existing embeddings
3. Regenerate all embeddings using text-embedding-3-large
4. Verify migration success
"""

import asyncio
import logging
import os
import sys
from typing import List, Dict, Optional
from supabase import create_client, Client
from openai import OpenAI

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, continue without it

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EmbeddingMigration:
    def __init__(self, supabase_url=None, supabase_key=None, openai_api_key=None):
        # Initialize Supabase client
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY')
        
        if self.supabase_url and self.supabase_key:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            logger.info("Supabase client initialized")
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
    
    def create_embedding_text(self, job: Dict) -> str:
        """
        Create embedding text from job data
        """
        title = job.get('title', '')
        company = job.get('company', '')
        location = job.get('location', '')
        description = job.get('description', '')
        
        # Combine all relevant text for embedding
        embedding_text = f"{title} {company} {location} {description}"
        
        # Clean up the text
        embedding_text = ' '.join(embedding_text.split())  # Remove extra whitespace
        return embedding_text.strip()
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding using text-embedding-3-large model
        """
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=text
            )
            
            embedding = response.data[0].embedding
            logger.info(f"Generated embedding with {len(embedding)} dimensions")
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None
    
    async def update_database_schema(self) -> bool:
        """
        Update database schema from vector(1536) to vector(3072)
        """
        try:
            logger.info("🔄 Updating database schema...")
            
            # First, check if we need to update the schema
            try:
                # Try to get a job with embedding to see current schema
                response = self.supabase.table('jobs').select('embedding').limit(1).execute()
                logger.info("✅ Database connection working")
            except Exception as e:
                logger.error(f"❌ Cannot connect to jobs table: {e}")
                return False
            
            # Since we can't execute DDL through Supabase client, we'll skip schema update
            # and assume the user will handle it manually or the column is already correct
            logger.info("⚠️ Schema update skipped - please ensure your database has vector(3072) column")
            logger.info("You can run the SQL commands manually in your Supabase SQL editor:")
            logger.info("See update_schema_manual.sql for the required SQL commands")
            
            # Test if the current schema accepts 3072-dimensional vectors
            try:
                test_embedding = [0.1] * 3072
                # Get first job to test with
                test_job_response = self.supabase.table('jobs').select('id').limit(1).execute()
                if test_job_response.data:
                    test_job_id = test_job_response.data[0]['id']
                    
                    # Try to update with 3072-dimensional vector
                    test_response = self.supabase.table('jobs').update({
                        'embedding': test_embedding
                    }).eq('id', test_job_id).execute()
                    
                    # Clear the test embedding
                    self.supabase.table('jobs').update({
                        'embedding': None
                    }).eq('id', test_job_id).execute()
                    
                    logger.info("✅ Database schema already supports 3072-dimensional vectors")
                    return True
                else:
                    logger.warning("No jobs found in database to test with")
                    return True  # Assume it's okay if no jobs exist
                
            except Exception as e:
                logger.error(f"❌ Database schema does not support 3072-dimensional vectors: {e}")
                logger.error("Please update your database schema manually first")
                logger.error("Run the SQL commands in update_schema_manual.sql")
                return False
            
        except Exception as e:
            logger.error(f"❌ Error checking database schema: {e}")
            return False
    
    async def clear_existing_embeddings(self) -> bool:
        """
        Clear all existing embeddings from the database
        """
        try:
            logger.info("🗑️ Clearing existing embeddings...")
            
            # Get all job IDs that have embeddings
            response = self.supabase.table('jobs').select('id').not_.is_('embedding', 'null').execute()
            jobs_with_embeddings = response.data
            
            if not jobs_with_embeddings:
                logger.info("✅ No existing embeddings to clear")
                return True
            
            logger.info(f"Found {len(jobs_with_embeddings)} jobs with embeddings to clear")
            
            # Clear embeddings in batches
            batch_size = 100
            for i in range(0, len(jobs_with_embeddings), batch_size):
                batch = jobs_with_embeddings[i:i + batch_size]
                job_ids = [job['id'] for job in batch]
                
                # Update this batch to set embedding to NULL
                update_response = self.supabase.table('jobs').update({
                    'embedding': None
                }).in_('id', job_ids).execute()
                
                logger.info(f"Cleared embeddings for batch {i//batch_size + 1}/{(len(jobs_with_embeddings) + batch_size - 1)//batch_size}")
            
            logger.info(f"✅ Cleared embeddings for {len(jobs_with_embeddings)} jobs")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error clearing embeddings: {e}")
            return False
    
    async def regenerate_all_embeddings(self, max_jobs: Optional[int] = None) -> bool:
        """
        Regenerate embeddings for all jobs using text-embedding-3-large
        """
        try:
            logger.info("🔄 Starting embedding regeneration...")
            
            # Fetch jobs that need embeddings
            query = self.supabase.table('jobs').select('*').is_('embedding', 'null')
            
            if max_jobs:
                query = query.limit(max_jobs)
                logger.info(f"Processing up to {max_jobs} jobs (limited for testing)")
            
            response = query.execute()
            jobs = response.data
            
            if not jobs:
                logger.info("No jobs found that need embeddings")
                return True
            
            logger.info(f"Found {len(jobs)} jobs to process")
            
            success_count = 0
            error_count = 0
            
            for i, job in enumerate(jobs, 1):
                try:
                    # Create embedding text
                    embedding_text = self.create_embedding_text(job)
                    
                    if not embedding_text.strip():
                        logger.warning(f"Empty embedding text for job {job.get('id')}, skipping")
                        continue
                    
                    # Generate embedding
                    embedding = await self.generate_embedding(embedding_text)
                    
                    if embedding:
                        # Update job with new embedding
                        self.supabase.table('jobs').update({
                            'embedding': embedding
                        }).eq('id', job.get('id')).execute()
                        
                        success_count += 1
                        logger.info(f"✅ Processed job {i}/{len(jobs)}: {job.get('title', 'Unknown')}")
                    else:
                        error_count += 1
                        logger.error(f"❌ Failed to generate embedding for job {job.get('id')}")
                
                except Exception as e:
                    error_count += 1
                    logger.error(f"❌ Error processing job {job.get('id')}: {e}")
                
                # Add a small delay to avoid rate limiting
                await asyncio.sleep(0.1)
            
            logger.info(f"✅ Embedding regeneration completed: {success_count} successful, {error_count} errors")
            return error_count == 0
            
        except Exception as e:
            logger.error(f"❌ Error during embedding regeneration: {e}")
            return False
    
    async def verify_migration(self) -> bool:
        """
        Verify that the migration was successful
        """
        try:
            logger.info("🔍 Verifying migration...")
            
            # Check if vector column has correct dimensions
            try:
                # Try to insert a test vector with 3072 dimensions
                test_embedding = [0.1] * 3072
                
                # Get first job to test with
                test_job_response = self.supabase.table('jobs').select('id').limit(1).execute()
                if test_job_response.data:
                    test_job_id = test_job_response.data[0]['id']
                    
                    test_response = self.supabase.table('jobs').update({
                        'embedding': test_embedding
                    }).eq('id', test_job_id).execute()
                    
                    # If successful, clear the test embedding
                    self.supabase.table('jobs').update({
                        'embedding': None
                    }).eq('id', test_job_id).execute()
                    
                    logger.info("✅ Vector column accepts 3072-dimensional vectors")
                else:
                    logger.warning("No jobs found to test vector column")
                
            except Exception as e:
                logger.error(f"❌ Vector column does not accept 3072-dimensional vectors: {e}")
                return False
            
            # Check how many jobs have embeddings
            response = self.supabase.table('jobs').select('id').not_.is_('embedding', 'null').execute()
            jobs_with_embeddings = len(response.data)
            
            # Check total jobs
            total_response = self.supabase.table('jobs').select('id').execute()
            total_jobs = len(total_response.data)
            
            logger.info(f"📊 Migration verification: {jobs_with_embeddings}/{total_jobs} jobs have embeddings")
            
            if jobs_with_embeddings > 0:
                logger.info("✅ Migration verification successful")
                return True
            else:
                logger.warning("⚠️ No jobs have embeddings - you may need to run regeneration")
                return True  # Still consider it successful if schema is correct
            
        except Exception as e:
            logger.error(f"❌ Error during migration verification: {e}")
            return False
    
    async def run_migration(self, max_jobs: Optional[int] = None) -> bool:
        """
        Run the complete migration process
        """
        logger.info("🚀 Starting migration to text-embedding-3-large")
        logger.info("=" * 60)
        
        try:
            # Step 1: Update database schema
            if not await self.update_database_schema():
                logger.error("❌ Schema update failed. Migration aborted.")
                return False
            
            # Step 2: Clear existing embeddings
            if not await self.clear_existing_embeddings():
                logger.error("❌ Failed to clear existing embeddings. Migration aborted.")
                return False
            
            # Step 3: Regenerate all embeddings
            if not await self.regenerate_all_embeddings(max_jobs):
                logger.error("❌ Embedding regeneration failed. Migration aborted.")
                return False
            
            # Step 4: Verify migration
            if not await self.verify_migration():
                logger.error("❌ Migration verification failed.")
                return False
            
            logger.info("=" * 60)
            logger.info("🎉 Migration completed successfully!")
            logger.info("Your database is now using text-embedding-3-large with 3072-dimensional vectors")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Migration failed with error: {e}")
            return False

async def main():
    """
    Main function to run the migration
    """
    try:
        print("🚀 Migration to text-embedding-3-large")
        print("=" * 50)
        print("⚠️  IMPORTANT: You may need to update your database schema manually first!")
        print("   If you haven't already, run the SQL commands in update_schema_manual.sql")
        print("   in your Supabase SQL editor before proceeding.")
        print("=" * 50)
        
        # Check if user wants to limit jobs for testing
        max_jobs = None
        if len(sys.argv) > 1:
            try:
                max_jobs = int(sys.argv[1])
                print(f"🧪 Test mode: Processing only {max_jobs} jobs")
            except ValueError:
                print("Usage: python migrate_to_embedding_v3.py [max_jobs]")
                print("Example: python migrate_to_embedding_v3.py 10  # Test with 10 jobs")
                return
        
        # Initialize migration
        migration = EmbeddingMigration()
        
        # Confirm with user
        if max_jobs:
            confirm = input(f"\nProceed with migration (test mode: {max_jobs} jobs)? (y/N): ")
        else:
            confirm = input("\nProceed with full migration? This will update ALL jobs. (y/N): ")
        
        if confirm.lower() != 'y':
            print("Migration cancelled.")
            return
        
        # Run migration
        success = await migration.run_migration(max_jobs)
        
        if success:
            print("\n✅ Migration completed successfully!")
            print("You can now use the updated semantic search with text-embedding-3-large")
        else:
            print("\n❌ Migration failed. Please check the logs above.")
            print("\nIf the schema update failed, please:")
            print("1. Run the SQL commands in update_schema_manual.sql manually")
            print("2. Then run this migration script again")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"Critical error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 