# Semantisk Søgning

Denne mappe indeholder scripts til semantisk søgning i job-databasen ved hjælp af vector embeddings.

## Scripts

### 1. `semantic_search.py`
Et script der tester semantisk søgning med foruddefinerede spørgsmål.

**Brug:**
```bash
cd Semantic
python semantic_search.py
```

Dette script vil køre gennem en række test-spørgsmål og vise resultaterne.

### 2. `interactive_search.py`
Et interaktivt script hvor du kan indtaste dine egne spørgsmål.

**Brug:**
```bash
cd Semantic
python interactive_search.py
```

Dette script giver dig en interaktiv prompt hvor du kan:
- Indtaste spørgsmål på dansk
- Se relevante job-resultater
- Bruge kommandoer som `help`, `quit`, `clear`

### 3. `test_search.py`
Et hurtigt test-script der tester semantisk søgning med et enkelt spørgsmål.

**Brug:**
```bash
cd Semantic
python test_search.py
```

Dette script er nyttigt til at verificere at alt virker korrekt før du bruger de andre scripts.

## Eksempler på spørgsmål

Du kan stille spørgsmål som:
- "Er der medicinalfirmaer der søger?"
- "Find jobs inden for IT og software udvikling"
- "Søger virksomheder efter marketing medarbejdere?"
- "Er der stillinger inden for finans og regnskab?"
- "Find jobs med høj CFO score"
- "Søger virksomheder efter ingeniører?"
- "Er der remote jobs tilgængelige?"

## Hvordan det virker

1. **Embedding Generation**: Spørgsmålet konverteres til en vector embedding ved hjælp af OpenAI's text-embedding-ada-002 model
2. **Vector Search**: Embeddingen bruges til at søge i Supabase-databasen efter jobs med lignende embeddings
3. **Similarity Scoring**: Jobs rangeres efter deres lighed med spørgsmålet (cosine similarity)
4. **Resultat Visning**: De mest relevante jobs vises med detaljer som titel, virksomhed, lokation, CFO score og relevans-score

## Krav

- Python 3.7+
- Alle dependencies fra `requirements.txt`
- Miljøvariabler:
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY` eller `SUPABASE_ANON_KEY`
  - `OPENAI_API_KEY`

## Database Setup

Før du kan bruge scriptene, skal du oprette de nødvendige database funktioner i Supabase:

### 1. Kør SQL-funktionerne

Åbn din Supabase SQL editor og kør indholdet af `create_similarity_functions.sql`:

```sql
-- Kopier og kør indholdet af Semantic/create_similarity_functions.sql
```

Dette opretter følgende funktioner:
- `match_jobs()` - Hovedfunktionen til semantisk søgning
- `match_jobs_full()` - Returnerer alle job-felter
- `find_similar_jobs()` - Finder jobs lignende et specifikt job
- `match_jobs_text()` - Placeholder for tekst-baseret søgning

### 2. Verificer pgvector extension

Sørg for at pgvector extension er aktiveret:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 3. Opret vector index (hvis ikke allerede gjort)

```sql
CREATE INDEX IF NOT EXISTS idx_jobs_embedding_vector 
ON public.jobs USING ivfflat (embedding vector_cosine_ops);
```

## Output Format

Resultaterne vises med følgende information:
- Job titel
- Virksomhed
- Lokation
- CFO Score
- Relevans-score (0-1, hvor 1 er mest relevant) 