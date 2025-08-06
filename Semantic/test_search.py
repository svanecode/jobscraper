#!/usr/bin/env python3
"""
Quick Test Script for Semantic Search

This script quickly tests the semantic search functionality with a single question.
Useful for verifying that everything is working correctly.
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

class QuickSearchTest:
    def __init__(self):
        # Initialize Supabase client
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY')
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Supabase credentials not found in environment variables")
        
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        
        # Initialize OpenAI client
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not found in environment variables")
        
        self.openai_client = OpenAI(api_key=self.openai_api_key)
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for given text"""
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None
    
    async def test_search(self, question: str, limit: int = 5) -> List[Dict]:
        """Test semantic search with a single question"""
        try:
            print(f"🔍 Testing search for: '{question}'")
            
            # Generate embedding
            embedding = await self.generate_embedding(question)
            if not embedding:
                print("❌ Failed to generate embedding")
                return []
            
            print(f"✅ Generated embedding ({len(embedding)} dimensions)")
            
            # Perform search
            response = self.supabase.rpc(
                'match_jobs',
                {
                    'query_embedding': embedding,
                    'match_threshold': 0.7,
                    'match_count': limit
                }
            ).execute()
            
            if response.data:
                print(f"✅ Found {len(response.data)} results")
                return response.data
            else:
                print("⚠️  No results found")
                return []
                
        except Exception as e:
            logger.error(f"Error in test search: {e}")
            print(f"❌ Error: {e}")
            return []
    
    def display_results(self, jobs: List[Dict]):
        """Display search results in a simple format"""
        if not jobs:
            print("Ingen resultater fundet.")
            return
        
        print(f"\n📋 Top {len(jobs)} resultater:")
        print("-" * 50)
        
        for i, job in enumerate(jobs, 1):
            similarity = job.get('similarity', 0)
            title = job.get('title', 'Ukendt titel')
            company = job.get('company', 'Ukendt virksomhed')
            
            print(f"{i}. {title}")
            print(f"   🏢 {company}")
            print(f"   🎯 Relevans: {similarity:.3f}")
            print()

async def main():
    """Main test function"""
    try:
        print("🚀 Starting semantic search test...")
        
        # Initialize test
        test = QuickSearchTest()
        print("✅ Initialized successfully")
        
        # Test question
        test_question = "Er der medicinalfirmaer der søger?"
        
        # Perform test search
        results = await test.test_search(test_question, limit=5)
        
        # Display results
        test.display_results(results)
        
        print("✅ Test completed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        logger.error(f"Test error: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 