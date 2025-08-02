#!/usr/bin/env python3
"""
Du er en dansk sprogmodel og ekspert i interim CFO-services. Din opgave er at gennemlæse danske jobopslag og vurdere sandsynligheden for, at virksomheden har brug for midlertidig CFO- eller økonomiassistance.

🔹 Du analyserer:
- Jobtitel
- Jobbeskrivelse
- Virksomhedsnavn og branche
- Eventuel angivelse af vikariat, barsel, sygdom, opsigelse, akut behov mv.

🔹 Du skal vurdere både relevans og **tidsmæssig karakter** (midlertidigt/akut vs. fast stilling).

🔹 Du må **aldrig tildele point til jobopslag fra konsulenthuse** (fx Deloitte, EY, PwC, BDO, Capgemini osv.) – de scorer altid **0**, da vi ikke konkurrerer med dem.

🔹 Økonomirelaterede stillinger dækker: CFO, regnskabschef, controller, bogholder, business partner, økonomichef, rapportering, budgettering, finansiel analyse, SAP/ERP relaterede økonomiroller.

🔹 Du skal returnere **kun én score**:  
- `3` = Akut/midlertidigt og økonomirelateret → KPMG bør tage kontakt straks  
- `2` = Økonomistilling hvor behovet kunne være der  
- `1` = Lav sandsynlighed, men økonomirelateret  
- `0` = Ikke økonomirelateret eller konsulenthus  

**Returnér kun et tal (0, 1, 2 eller 3). Ingen anden tekst.**

---

🔸 Eksempler:
- “Interim regnskabschef i barselsvikariat” → 3  
- “Finance Business Partner” → 2  
- “Studiejob i økonomiafdelingen” → 1  
- “HR-assistent med personaleansvar” → 0  
- “Managementkonsulent hos Deloitte” → 0

---

Læs og vurder følgende jobopslag:

"""

import asyncio
import logging
import os
import time
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

class JobScorer:
    def __init__(self, supabase_url=None, supabase_key=None, openai_api_key=None):
        # Initialize Supabase client
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_ANON_KEY')
        
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
    
    def get_all_jobs(self, max_jobs=None, only_unscored=False) -> List[Dict]:
        """
        Get all jobs from the database
        
        Args:
            max_jobs: Maximum number of jobs to fetch (for testing)
            only_unscored: If True, only fetch jobs that haven't been scored yet
        
        Returns:
            List of job dictionaries
        """
        try:
            # Start with base query - only get active (non-deleted) jobs
            query = self.supabase.table('jobs').select('*').is_('deleted_at', 'null')
            
            if only_unscored:
                query = query.is_('cfo_score', 'null')
                logger.info("Filtering for active unscored jobs only")
            else:
                logger.info("Filtering for active jobs only")
            
            if max_jobs:
                query = query.limit(max_jobs)
            
            response = query.execute()
            
            if response.data:
                logger.info(f"Retrieved {len(response.data)} active jobs from database")
                return response.data
            else:
                logger.warning("No active jobs found in database")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching jobs from database: {e}")
            return []
    
    def create_scoring_prompt(self, job: Dict) -> str:
        """
        Create the scoring prompt for a specific job
        
        Args:
            job: Job dictionary containing title, company, location, description
        
        Returns:
            Formatted prompt string
        """
        prompt = f"""Du er en dansk sprogmodel og ekspert i interim CFO-services. Din opgave er at gennemlæse danske jobopslag og vurdere sandsynligheden for, at virksomheden har brug for midlertidig CFO- eller økonomiassistance.

🔹 Du analyserer:
- Jobtitel
- Jobbeskrivelse
- Virksomhedsnavn og branche
- Eventuel angivelse af vikariat, barsel, sygdom, opsigelse, akut behov mv.

🔹 Du skal vurdere både relevans og **tidsmæssig karakter** (midlertidigt/akut vs. fast stilling).

🔹 Du må **aldrig tildele point til jobopslag fra konsulenthuse** (fx Deloitte, EY, PwC, BDO, Capgemini osv.) – de scorer altid **0**, da vi ikke konkurrerer med dem.

🔹 Økonomirelaterede stillinger dækker fx: CFO, regnskabschef, controller, bogholder, business partner, økonomichef, rapportering, budgettering, finansiel analyse, **lønbehandling**, lønbogholder, lønassistent og SAP/ERP relaterede økonomiroller.

🔹 Du skal returnere **kun én score**:  
- `3` = Akut/midlertidigt og økonomirelateret → KPMG bør tage kontakt straks  
- `2` = Økonomistilling hvor behovet kunne være der  
- `1` = Lav sandsynlighed, men økonomirelateret  
- `0` = Ikke økonomirelateret eller konsulenthus  

**Returnér kun et tal (0, 1, 2 eller 3). Ingen anden tekst.**

---

🔸 Eksempler:
- "Interim regnskabschef i barselsvikariat" → 3  
- "Finance Business Partner" → 2  
- "Studiejob i økonomiafdelingen" → 1  
- "HR-assistent med personaleansvar" → 0  
- "Managementkonsulent hos Deloitte" → 0
- “HR- og lønassistent – barselsvikariat” → 3  
- “Lønbogholder til regnskabsafdeling” → 2  
- “Studentermedhjælper med opgaver i løn og administration” → 1  
- “HR-konsulent med fokus på personaleudvikling” → 0  

---

🔹 Sådan skelner du mellem score 1 og 2:

- Vælg **score 2**, hvis jobtitlen eller beskrivelsen indeholder klare økonomiroller som: “regnskabsmedarbejder”, “controller”, “bogholder”, “økonomichef”, “finance business partner” osv.

- Vælg **score 1**, hvis det kun nævnes perifert, fx “assistent i økonomiafdelingen”, “hjælper med budgetter” eller “økonomiforståelse ønskes”.

→ Det er vigtigt, at du ikke er for forsigtig: **Hvis jobtitlen i sig selv er en økonomistilling, så giv mindst score 2**.

---

- **Score 3**, hvis der er tale om et **midlertidigt lønjob**, fx barselsvikariat, sygefravær eller “hurtig tiltrædelse” i en lønfunktion
- **Score 2**, hvis det er en **permanent lønrelateret rolle** i økonomiafdelingen
- **Score 1**, hvis det kun nævnes perifert (“hjælper med løn”, “forståelse for løn ønskes”)

---

Læs og vurder følgende jobopslag:

Titel: {job.get('title', 'N/A')}
Firma: {job.get('company', 'N/A')}
Lokation: {job.get('location', 'N/A')}
Beskrivelse: {job.get('description', 'N/A')}"""
        
        return prompt
    
    async def score_job(self, job: Dict) -> Optional[int]:
        """
        Score a single job using OpenAI API
        
        Args:
            job: Job dictionary
        
        Returns:
            Score (0-3) or None if error
        """
        try:
            # Create system message with rules and examples
            system_message = """Du er en dansk sprogmodel og ekspert i interim CFO-services. Din opgave er at gennemlæse danske jobopslag og vurdere sandsynligheden for, at virksomheden har brug for midlertidig CFO- eller økonomiassistance.

🔹 Du analyserer:
- Jobtitel
- Jobbeskrivelse
- Virksomhedsnavn og branche
- Eventuel angivelse af vikariat, barsel, sygdom, opsigelse, akut behov mv.

🔹 Du skal vurdere både relevans og **tidsmæssig karakter** (midlertidigt/akut vs. fast stilling).

🔹 Du må **aldrig tildele point til jobopslag fra konsulenthuse** (fx Deloitte, EY, PwC, BDO, Capgemini osv.) – de scorer altid **0**, da vi ikke konkurrerer med dem.

🔹 Økonomirelaterede stillinger dækker: CFO, regnskabschef, controller, bogholder, business partner, økonomichef, rapportering, budgettering, finansiel analyse, SAP/ERP relaterede økonomiroller.

🔹 Du skal returnere **kun én score**:  
- `3` = Akut/midlertidigt og økonomirelateret → KPMG bør tage kontakt straks  
- `2` = Økonomistilling hvor behovet kunne være der  
- `1` = Lav sandsynlighed, men økonomirelateret  
- `0` = Ikke økonomirelateret eller konsulenthus  

🔹 Sådan skelner du mellem score 1 og 2:

- Vælg **score 2**, hvis jobtitlen eller beskrivelsen indeholder klare økonomiroller som: "regnskabsmedarbejder", "controller", "bogholder", "økonomichef", "finance business partner" osv.

- Vælg **score 1**, hvis det kun nævnes perifert, fx "assistent i økonomiafdelingen", "hjælper med budgetter" eller "økonomiforståelse ønskes".

→ Det er vigtigt, at du ikke er for forsigtig: **Hvis jobtitlen i sig selv er en økonomistilling, så giv mindst score 2**.

🔸 Eksempler:
- "Interim regnskabschef i barselsvikariat" → 3  
- "Finance Business Partner" → 2  
- "Studiejob i økonomiafdelingen" → 1  
- "HR-assistent med personaleansvar" → 0  
- "Managementkonsulent hos Deloitte" → 0

**Returnér kun et tal (0, 1, 2 eller 3). Ingen anden tekst.**"""

            # Create user message with the specific job
            user_message = f"""Læs og vurder følgende jobopslag:

Titel: {job.get('title', 'N/A')}
Firma: {job.get('company', 'N/A')}
Lokation: {job.get('location', 'N/A')}
Beskrivelse: {job.get('description', 'N/A')}"""
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",  # Using GPT-4o for better accuracy
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=5,  # Reduced since we only need a single digit
                temperature=0  # Set to 0 for maximum consistency
            )
            
            # Extract the score from the response
            score_text = response.choices[0].message.content.strip()
            
            # Try to extract just the number
            try:
                score = int(score_text)
                if 0 <= score <= 3:
                    return score
                else:
                    logger.warning(f"Invalid score {score} for job {job.get('job_id')}, defaulting to 0")
                    return 0
            except ValueError:
                logger.warning(f"Could not parse score '{score_text}' for job {job.get('job_id')}, defaulting to 0")
                return 0
                
        except Exception as e:
            logger.error(f"Error scoring job {job.get('job_id')}: {e}")
            return None
    
    def update_job_score(self, job_id: str, score: int) -> bool:
        """
        Update the job score in the database
        
        Args:
            job_id: Job ID
            score: Score (0-3)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.supabase.table('jobs').update({
                'cfo_score': score,
                'scored_at': 'now()'
            }).eq('job_id', job_id).execute()
            
            if response.data:
                logger.debug(f"Updated score for job {job_id}: {score}")
                return True
            else:
                logger.error(f"Failed to update score for job {job_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating score for job {job_id}: {e}")
            return False
    
    async def score_all_jobs(self, batch_size=10, max_jobs=None, delay=1.0, only_unscored=False):
        """
        Score all jobs in the database
        
        Args:
            batch_size: Number of jobs to process in parallel
            max_jobs: Maximum number of jobs to score (for testing)
            delay: Delay between batches in seconds (to respect API rate limits)
            only_unscored: If True, only score jobs that haven't been scored yet
        """
        # Get all jobs
        jobs = self.get_all_jobs(max_jobs, only_unscored)
        
        if not jobs:
            if only_unscored:
                logger.info("No active unscored jobs found to score")
            else:
                logger.info("No active jobs found to score")
            return
        
        if only_unscored:
            logger.info(f"Starting to score {len(jobs)} active unscored jobs")
        else:
            logger.info(f"Starting to score {len(jobs)} active jobs")
        
        # Process jobs in batches
        total_scored = 0
        total_errors = 0
        scores_distribution = {0: 0, 1: 0, 2: 0, 3: 0}
        
        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            batch_num = i//batch_size + 1
            total_batches = (len(jobs) + batch_size - 1)//batch_size
            
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} jobs)")
            
            # Score jobs in parallel
            tasks = [self.score_job(job) for job in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for job, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.error(f"Error scoring job {job.get('job_id')}: {result}")
                    total_errors += 1
                    continue
                
                if result is not None:
                    score = result
                    scores_distribution[score] += 1
                    
                    # Update database
                    if self.update_job_score(job['job_id'], score):
                        total_scored += 1
                        logger.debug(f"Scored job '{job.get('title')}' ({job.get('job_id')}): {score}")
                    else:
                        total_errors += 1
                else:
                    total_errors += 1
            
            # Progress update
            progress = (total_scored + total_errors) / len(jobs) * 100
            logger.info(f"Progress: {progress:.1f}% ({total_scored + total_errors}/{len(jobs)})")
            
            # Add delay between batches to respect API rate limits
            if i + batch_size < len(jobs):
                await asyncio.sleep(delay)
        
        # Final summary
        logger.info("=== SCORING COMPLETE ===")
        logger.info(f"Total active jobs processed: {len(jobs)}")
        logger.info(f"Successfully scored: {total_scored}")
        logger.info(f"Errors: {total_errors}")
        logger.info("Score distribution:")
        for score, count in scores_distribution.items():
            percentage = (count / len(jobs)) * 100 if len(jobs) > 0 else 0
            logger.info(f"  Score {score}: {count} jobs ({percentage:.1f}%)")
    
    def get_scoring_stats(self) -> Dict:
        """
        Get statistics about job scoring
        
        Returns:
            Dictionary with scoring statistics
        """
        try:
            # Get jobs with scores
            response = self.supabase.table('jobs').select('cfo_score').not_.is_('cfo_score', 'null').execute()
            
            if not response.data:
                return {
                    "total_scored": 0, 
                    "distribution": {},
                    "average_score": 0
                }
            
            scores = [job['cfo_score'] for job in response.data]
            distribution = {0: 0, 1: 0, 2: 0, 3: 0}
            
            for score in scores:
                if score in distribution:
                    distribution[score] += 1
            
            return {
                "total_scored": len(scores),
                "distribution": distribution,
                "average_score": sum(scores) / len(scores) if scores else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting scoring stats: {e}")
            return {
                "total_scored": 0, 
                "distribution": {},
                "average_score": 0
            }

async def main():
    """Main function to run the job scorer"""
    try:
        # Initialize the job scorer
        scorer = JobScorer()
        
        # Score jobs (limited to 100 unscored jobs per run)
        await scorer.score_all_jobs(
            batch_size=5,  # Conservative batch size for API rate limits
            max_jobs=100,  # Limited to 100 jobs per run
            delay=2.0,  # 2 second delay between batches
            only_unscored=True  # Only score jobs that haven't been scored yet
        )
        
        # Print final statistics
        stats = scorer.get_scoring_stats()
        logger.info("=== FINAL STATISTICS ===")
        logger.info(f"Total jobs scored: {stats['total_scored']}")
        logger.info(f"Average score: {stats['average_score']:.2f}")
        logger.info("Score distribution:")
        for score, count in stats['distribution'].items():
            percentage = (count / stats['total_scored']) * 100 if stats['total_scored'] > 0 else 0
            logger.info(f"  Score {score}: {count} jobs ({percentage:.1f}%)")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 