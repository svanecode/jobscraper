
#!/usr/bin/env python3
"""
Interactive Semantic Search Script

This script provides an interactive interface for semantic job search.
Users can input questions and get real-time results from the database.
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
    pass  # dotenv not installed, continue without it

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InteractiveSemanticSearch:
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
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for given text using OpenAI's text-embedding-ada-002 model
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
    
    def preprocess_query(self, question: str) -> str:
        """
        Preprocess the query to improve search results
        """
        # Convert to lowercase for better matching
        question = question.lower().strip()
        
        # Add common synonyms and variations
        synonyms = {
            'aarhus': 'aarhus location',
            'københavn': 'københavn location',
            'pharma': 'pharma company pharmaceutical',
            'fragt': 'fragt transport logistik',
            'marketing': 'marketing reklame',
            'it': 'it software teknologi',
            'finance': 'finance økonomi regnskab',
            'controller': 'controller økonomi regnskab',
            'bogholder': 'bogholder regnskab økonomi',
            'remote': 'remote hjemmearbejde hybrid',
            'student': 'student studentermedhjælper',
            'erfaren': 'erfaren senior',
            'ny': 'ny nyoprettet',
            'deltid': 'deltid part time',
            'fuldtid': 'fuldtid full time'
        }
        
        # Add synonyms to the query
        enhanced_query = question
        for term, synonyms_list in synonyms.items():
            if term in question:
                enhanced_query += f" {synonyms_list}"
        
        return enhanced_query

    def get_optimal_threshold(self, question: str) -> float:
        """
        Determine optimal similarity threshold based on query type
        """
        question_lower = question.lower()
        
        # Location queries need lower threshold for better matching
        location_terms = ['aarhus', 'københavn', 'odense', 'aalborg', 'esbjerg', 'roskilde', 'horsens', 'vejle', 'randers', 'herning']
        if any(term in question_lower for term in location_terms):
            return 0.4  # Lower threshold for location searches
        
        # Company name queries
        company_terms = ['pharma', 'novo', 'erhvervsstyrelsen', 'region', 'kommune', 'universitet']
        if any(term in question_lower for term in company_terms):
            return 0.45  # Medium-low threshold for company searches
        
        # Specific job function queries
        function_terms = ['controller', 'bogholder', 'økonomi', 'finance', 'regnskab']
        if any(term in question_lower for term in function_terms):
            return 0.5  # Medium threshold for function searches
        
        # General queries
        return 0.5  # Default threshold

    async def search_jobs(self, question: str, limit: int = 10) -> List[Dict]:
        """
        Perform semantic search for jobs based on a question
        """
        try:
            # Preprocess the query
            enhanced_question = self.preprocess_query(question)
            
            # Generate embedding for the enhanced question
            print(f"Genererer embedding for spørgsmålet...")
            question_embedding = await self.generate_embedding(enhanced_question)
            
            if not question_embedding:
                print("Fejl: Kunne ikke generere embedding for spørgsmålet")
                return []
            
            # Perform vector similarity search in Supabase
            print("Søger efter relevante jobs...")
            
            # Determine optimal threshold based on query type
            threshold = self.get_optimal_threshold(question)
            
            # Use pgvector's cosine similarity function
            response = self.supabase.rpc(
                'match_jobs',
                {
                    'query_embedding': question_embedding,
                    'match_threshold': threshold,
                    'match_count': limit
                }
            ).execute()
            
            if response.data:
                print(f"Fundet {len(response.data)} relevante jobs")
                return response.data
            else:
                print("Ingen relevante jobs fundet")
                return []
                
        except Exception as e:
            logger.error(f"Error performing semantic search: {e}")
            print(f"Fejl under søgning: {e}")
            return []
    
    def format_job_results(self, jobs: List[Dict]) -> str:
        """
        Format job search results for display
        """
        if not jobs:
            return "Ingen relevante jobs fundet."
        
        result = f"\n=== Søgeresultater ({len(jobs)} jobs) ===\n\n"
        
        for i, job in enumerate(jobs, 1):
            similarity = job.get('similarity', 0)
            title = job.get('title', 'Ukendt titel')
            company = job.get('company', 'Ukendt virksomhed')
            location = job.get('location', 'Ukendt lokation')
            cfo_score = job.get('cfo_score', 0)
            
            result += f"{i}. {title}\n"
            result += f"   🏢 {company}\n"
            result += f"   📍 {location}\n"
            result += f"   ⭐ CFO Score: {cfo_score}\n"
            result += f"   🎯 Relevans: {similarity:.3f}\n"
            result += "\n"
        
        return result
    
    async def get_ai_analysis(self, question: str, jobs: List[Dict]) -> str:
        """
        Get AI analysis of the search results
        """
        if not jobs:
            return "❌ Ingen jobs fundet at analysere."
        
        try:
            # Prepare job details for AI analysis
            job_details = []
            for i, job in enumerate(jobs, 1):
                title = job.get('title', 'Ukendt titel')
                company = job.get('company', 'Ukendt virksomhed')
                location = job.get('location', 'Ukendt lokation')
                description = job.get('description', 'Ingen beskrivelse')
                cfo_score = job.get('cfo_score', 0)
                similarity = job.get('similarity', 0)
                
                job_detail = f"""
Job {i}:
- Titel: {title}
- Virksomhed: {company}
- Lokation: {location}
- CFO Score: {cfo_score}
- Relevans: {similarity:.3f}
- Beskrivelse: {description}
"""
                job_details.append(job_detail)
            
            # Create prompt for AI analysis
            prompt = f"""
Du er en ekspert jobrådgiver. Analyser følgende jobs baseret på spørgsmålet: "{question}"

VIGTIGT: Alle jobs i databasen er økonomi/regnskab stillinger (controller, bogholder, økonomimedarbejder, etc.). Fokuser derfor på:
- Virksomhedstype (f.eks. pharma, transport, IT, etc.)
- Lokation
- Projekttyper eller særlige omstændigheder
- IKKE jobfunktionen selv

Her er {len(jobs)} jobs fra databasen:

{''.join(job_details)}

Giv et kort og direkte svar på spørgsmålet. Hvis ingen jobs er relevante, svar "Nej" + kort forklaring. Hvis der er relevante jobs, nævn op til 5 af de mest relevante job numre + kort forklaring.

Eksempler:
- "Nej, der er ikke nogen fragtfirmaer der søger økonomimedarbejdere"
- "Ja, Job 1, 2. Pharma Nord søger økonomimedarbejdere"
- "Ja, Job 3. Erhvervsstyrelsen søger controller i København"

Svar kun på dansk og hold det kort og direkte.
"""
            
            # Get AI response
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Du er en ekspert jobrådgiver der analyserer job stillinger. Giv korte og præcise svar på dansk."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.3
            )
            
            ai_response = response.choices[0].message.content.strip()
            return f"🤖 AI Analyse: {ai_response}"
            
        except Exception as e:
            logger.error(f"Error getting AI analysis: {e}")
            return "❌ Fejl ved AI analyse."

    def show_help(self):
        """
        Display help information
        """
        help_text = """
=== Semantisk Job Søgning - Hjælp ===

Du kan stille spørgsmål på dansk om jobs, og systemet vil finde de mest relevante stillinger.

Eksempler på spørgsmål:
- "Er der medicinalfirmaer der søger?"
- "Find jobs inden for IT og software udvikling"
- "Søger virksomheder efter marketing medarbejdere?"
- "Er der stillinger inden for finans og regnskab?"
- "Find jobs med høj CFO score"
- "Søger virksomheder efter ingeniører?"
- "Er der remote jobs tilgængelige?"

🤖 AI Analyse:
Systemet vil automatisk analysere resultaterne og give dig:
- En vurdering af relevante jobs (0-5 jobs)
- Kort forklaring på spørgsmålet
- Fokus på de mest relevante stillinger

Kommandoer:
- 'help' eller 'h' - Vis denne hjælp
- 'quit' eller 'q' - Afslut programmet
- 'clear' eller 'c' - Ryd skærmen

        """
        print(help_text)

async def main():
    """
    Main interactive function
    """
    try:
        print("🚀 Initialiserer semantisk søgning...")
        search = InteractiveSemanticSearch()
        
        print("\n" + "="*60)
        print("🎯 SEMANTISK JOB SØGNING")
        print("="*60)
        print("Skriv 'help' for hjælp eller 'quit' for at afslutte\n")
        
        while True:
            try:
                # Get user input
                question = input("❓ Indtast dit spørgsmål: ").strip()
                
                # Handle commands
                if question.lower() in ['quit', 'q', 'exit']:
                    print("👋 Farvel!")
                    break
                elif question.lower() in ['help', 'h']:
                    search.show_help()
                    continue
                elif question.lower() in ['clear', 'c']:
                    os.system('clear' if os.name == 'posix' else 'cls')
                    continue
                elif not question:
                    print("⚠️  Indtast venligst et spørgsmål")
                    continue
                
                # Perform search
                results = await search.search_jobs(question, limit=10)
                
                # Display results
                formatted_results = search.format_job_results(results)
                print(formatted_results)
                
                # Get AI analysis
                print("🤖 Får AI analyse...")
                ai_analysis = await search.get_ai_analysis(question, results)
                print(ai_analysis)
                
                print("-" * 60)
                
            except KeyboardInterrupt:
                print("\n\n👋 Farvel!")
                break
            except Exception as e:
                print(f"❌ Fejl: {e}")
                print("Prøv igen eller skriv 'help' for hjælp")
    
    except Exception as e:
        logger.error(f"Error in main function: {e}")
        print(f"❌ Kritisk fejl: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 