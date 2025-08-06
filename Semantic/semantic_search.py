#!/usr/bin/env python3
"""
Semantic Search Script

This script performs semantic search on job records in the database.
It takes a question, generates an embedding for it, and finds the most
relevant jobs using vector similarity search in Supabase.
"""

import asyncio
import logging
import os
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

class SemanticSearch:
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
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for given text using OpenAI's text-embedding-ada-002 model
        
        Args:
            text: Text to embed
        
        Returns:
            List of embedding values or None if failed
        """
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            
            embedding = response.data[0].embedding
            logger.info(f"Generated embedding with {len(embedding)} dimensions")
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None
    
    async def search_jobs(self, question: str, limit: int = 10) -> List[Dict]:
        """
        Perform semantic search for jobs based on a question
        
        Args:
            question: The search question
            limit: Maximum number of results to return
        
        Returns:
            List of job dictionaries with similarity scores
        """
        try:
            # Generate embedding for the question
            logger.info(f"Generating embedding for question: '{question}'")
            question_embedding = await self.generate_embedding(question)
            
            if not question_embedding:
                logger.error("Failed to generate embedding for question")
                return []
            
            # Perform vector similarity search in Supabase
            logger.info("Performing vector similarity search...")
            
            # Use pgvector's cosine similarity function
            response = self.supabase.rpc(
                'match_jobs',
                {
                    'query_embedding': question_embedding,
                    'match_threshold': 0.7,  # Minimum similarity threshold
                    'match_count': limit
                }
            ).execute()
            
            if response.data:
                logger.info(f"Found {len(response.data)} relevant jobs")
                return response.data
            else:
                logger.info("No relevant jobs found")
                return []
                
        except Exception as e:
            logger.error(f"Error performing semantic search: {e}")
            return []
    
    def format_job_results(self, jobs: List[Dict]) -> str:
        """
        Format job search results for display
        
        Args:
            jobs: List of job dictionaries with similarity scores
        
        Returns:
            Formatted string with job information
        """
        if not jobs:
            return "Ingen relevante jobs fundet."
        
        result = f"Fundet {len(jobs)} relevante jobs:\n\n"
        
        for i, job in enumerate(jobs, 1):
            similarity = job.get('similarity', 0)
            title = job.get('title', 'Ukendt titel')
            company = job.get('company', 'Ukendt virksomhed')
            location = job.get('location', 'Ukendt lokation')
            cfo_score = job.get('cfo_score', 0)
            
            result += f"{i}. {title}\n"
            result += f"   Virksomhed: {company}\n"
            result += f"   Lokation: {location}\n"
            result += f"   CFO Score: {cfo_score}\n"
            result += f"   Relevans: {similarity:.3f}\n"
            result += "\n"
        
        return result

async def main():
    """
    Main function to run semantic search
    """
    try:
        # Initialize semantic search
        search = SemanticSearch()
        
        # Example questions to test
        test_questions = [
            "Er der medicinalfirmaer der søger?",
            "Find jobs inden for IT og software udvikling",
            "Søger virksomheder efter marketing medarbejdere?",
            "Er der stillinger inden for finans og regnskab?",
            "Find jobs med høj CFO score"
        ]
        
        print("=== Semantisk Søgning Test ===\n")
        
        for question in test_questions:
            print(f"Spørgsmål: {question}")
            print("-" * 50)
            
            # Perform search
            results = await search.search_jobs(question, limit=10)
            
            # Format and display results
            formatted_results = search.format_job_results(results)
            print(formatted_results)
            print("=" * 80 + "\n")
            
            # Add a small delay between searches
            await asyncio.sleep(1)
    
    except Exception as e:
        logger.error(f"Error in main function: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 