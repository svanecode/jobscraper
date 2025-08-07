
#!/usr/bin/env python3
"""
Interactive Semantic Search Script

This script provides an interactive interface for semantic job search.
Users can input questions and get real-time results from the database.
Enhanced with AI query structuring and conversation context.
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
        
        # Initialize conversation context
        self.conversation_history = []
        self.max_history_length = 10  # Keep last 10 exchanges
    
    async def structure_query_with_ai(self, user_question: str, conversation_context: List[Dict] = None) -> str:
        """
        Use AI to structure and enhance the user query for better search results
        """
        try:
            # Prepare conversation context for AI
            context_text = ""
            if conversation_context:
                context_text = "\n".join([
                    f"Tidligere spørgsmål: {exchange.get('question', '')}"
                    for exchange in conversation_context[-3:]  # Last 3 exchanges
                ])
            
            # Create prompt for query structuring
            prompt = f"""
Du er en ekspert i at strukturere job-søgninger. Din opgave er at forbedre brugerens spørgsmål for bedre søgeresultater.

KONTEKST:
Alle jobs i databasen er økonomi/regnskab stillinger (controller, bogholder, økonomimedarbejder, etc.).
Fokuser derfor på: virksomhedstype, lokation, projekttyper, ikke jobfunktionen selv.

{context_text if context_text else "Ingen tidligere kontekst"}

BRUGER SPØRGSMÅL: "{user_question}"

VIGTIGE REGLER:
1. Identificer virksomhedsnavne og lokationer i spørgsmålet
2. Hvis brugeren spørger om en SPECIFIK VIRKSOMHED, gentag virksomhedsnavnet 2-3 gange
3. Hvis brugeren spørger om en SPECIFIK LOKATION, gentag lokationen 2-3 gange
4. IKKE gentag ord som "søger", "jobs", "stillinger", "nogeni", "er", "der", "hvor", etc.
5. Kombiner virksomhed/lokation med relevante job-termer

OPGAVE:
1. Forstå brugerens intention
2. Identificer specifikke virksomheder eller lokationer
3. Gentag disse specifikke termer 2-3 gange
4. Tilføj relevante job-termer
5. Bevar den oprindelige mening

RETUR:
Kun det forbedrede spørgsmål, intet andet. Hold det under 100 ord.

Eksempler:
- "søger novo nordisk?" → "Novo Nordisk Novo Nordisk økonomi regnskab controller stillinger"
- "pharma jobs" → "pharma pharmaceutical medicinal company økonomi regnskab controller"
- "remote stillinger" → "remote hjemmearbejde hybrid work økonomi regnskab"
- "controller stillinger" → "controller økonomi regnskab stillinger"
- "finance jobs" → "finance økonomi regnskab stillinger"
"""
            
            # Get AI response
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Du er en ekspert i at strukturere job-søgninger. Giv kun det forbedrede spørgsmål som svar."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.3
            )
            
            structured_query = response.choices[0].message.content.strip()
            logger.info(f"Original query: '{user_question}' → Structured: '{structured_query}'")
            print(f"🔍 AI strukturerede: '{user_question}' → '{structured_query}'")
            return structured_query
            
        except Exception as e:
            logger.error(f"Error structuring query with AI: {e}")
            # Fallback to original query
            return user_question
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for given text using OpenAI's text-embedding-3-large model
        """
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-large",
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
        
        # If AI has already structured the query with repetitions, don't add more synonyms
        # Check if there are repeated terms (indicating AI has already enhanced it)
        words = question.split()
        word_counts = {}
        for word in words:
            word_counts[word] = word_counts.get(word, 0) + 1
        
        # If any word appears more than 2 times, AI has already enhanced it
        has_ai_enhancement = any(count > 2 for count in word_counts.values())
        
        if has_ai_enhancement:
            # AI has already enhanced the query, just return it
            return question
        
        # Add common synonyms and variations only if AI hasn't enhanced it
        synonyms = {
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
        
        # Specific company queries need very low threshold for exact matching
        # Check for company name patterns
        if any(word in question_lower for word in ['virksomhed', 'firma', 'selskab', 'as', 'aps']):
            return 0.35  # Very low threshold for specific company searches
        
        # Location queries need lower threshold for better matching
        # Check for common location patterns
        if any(word in question_lower for word in ['by', 'sted', 'område', 'region', 'kommune']):
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
            # Preprocess the original query directly (no AI structuring first)
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
    
    async def get_ai_analysis(self, question: str, jobs: List[Dict], conversation_context: List[Dict] = None) -> str:
        """
        Get AI analysis of the search results with conversation context
        """
        if not jobs:
            return "❌ Ingen jobs fundet at analysere."
        
        try:
            # Prepare conversation context
            context_text = ""
            if conversation_context:
                recent_exchanges = conversation_context[-3:]  # Last 3 exchanges
                context_text = "\n".join([
                    f"Tidligere spørgsmål: {exchange.get('question', '')}"
                    for exchange in recent_exchanges
                ])
            
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

KONTEKST:
Alle jobs i databasen er økonomi/regnskab stillinger (controller, bogholder, økonomimedarbejder, etc.). Fokuser derfor på:
- Virksomhedstype (f.eks. pharma, transport, IT, etc.)
- Lokation
- Projekttyper eller særlige omstændigheder
- IKKE jobfunktionen selv

{context_text if context_text else "Ingen tidligere kontekst"}

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
    
    def add_to_conversation_history(self, question: str, results: List[Dict]):
        """
        Add current exchange to conversation history
        """
        self.conversation_history.append({
            'question': question,
            'results_count': len(results),
            'timestamp': asyncio.get_event_loop().time()
        })
        
        # Keep only the last N exchanges
        if len(self.conversation_history) > self.max_history_length:
            self.conversation_history = self.conversation_history[-self.max_history_length:]
    
    def clear_conversation_history(self):
        """
        Clear conversation history
        """
        self.conversation_history = []
        print("🗑️  Samtalehistorik ryddet")

    def show_help(self):
        """
        Display help information
        """
        help_text = """
=== Semantisk Job Søgning - Hjælp ===

Du kan stille spørgsmål på dansk om jobs, og systemet vil finde de mest relevante stillinger.

🤖 AI-FORBEDRINGER:
- AI analyserer søgeresultaterne og giver dig indsigt
- Systemet husker tidligere spørgsmål i samtalen
- Opfølgende spørgsmål forstås i kontekst

Eksempler på spørgsmål:
- "Er der medicinalfirmaer der søger?"
- "Find jobs inden for IT og software udvikling"
- "Søger virksomheder efter marketing medarbejdere?"
- "Er der stillinger inden for finans og regnskab?"
- "Find jobs med høj CFO score"
- "Søger virksomheder efter ingeniører?"
- "Er der remote jobs tilgængelige?"

Opfølgende spørgsmål:
- "Hvad med i København?" (efter et spørgsmål om jobs)
- "Er der flere?" (efter at have set resultater)
- "Hvad med remote muligheder?" (efter et spørgsmål om specifik virksomhed)

🤖 AI Analyse:
Systemet vil automatisk analysere resultaterne og give dig:
- En vurdering af relevante jobs (0-5 jobs)
- Kort forklaring på spørgsmålet
- Fokus på de mest relevante stillinger

Kommandoer:
- 'help' eller 'h' - Vis denne hjælp
- 'quit' eller 'q' - Afslut programmet
- 'clear' eller 'c' - Ryd skærmen
- 'history' eller 'hist' - Vis samtalehistorik
- 'clear_history' eller 'ch' - Ryd samtalehistorik

        """
        print(help_text)
    
    def show_conversation_history(self):
        """
        Display conversation history
        """
        if not self.conversation_history:
            print("📝 Ingen samtalehistorik")
            return
        
        print("\n=== SAMTALEHISTORIK ===")
        for i, exchange in enumerate(self.conversation_history, 1):
            question = exchange.get('question', 'Ukendt spørgsmål')
            results_count = exchange.get('results_count', 0)
            print(f"{i}. {question} ({results_count} resultater)")
        print("=" * 30)

async def main():
    """
    Main interactive function
    """
    try:
        print("🚀 Initialiserer semantisk søgning...")
        search = InteractiveSemanticSearch()
        
        print("\n" + "="*60)
        print("🎯 SEMANTISK JOB SØGNING (AI-Forbedret)")
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
                elif question.lower() in ['history', 'hist']:
                    search.show_conversation_history()
                    continue
                elif question.lower() in ['clear_history', 'ch']:
                    search.clear_conversation_history()
                    continue
                elif not question:
                    print("⚠️  Indtast venligst et spørgsmål")
                    continue
                
                # Perform search first (no AI query structuring)
                results = await search.search_jobs(question, limit=10)
                
                # Add to conversation history
                search.add_to_conversation_history(question, results)
                
                # Display results
                formatted_results = search.format_job_results(results)
                print(formatted_results)
                
                # Then send results to AI for analysis
                print("🤖 Får AI analyse af søgeresultaterne...")
                ai_analysis = await search.get_ai_analysis(question, results, search.conversation_history)
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