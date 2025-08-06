# Quick Setup Guide for Semantic Search

## Trin 1: Database Setup

1. **Åbn Supabase SQL Editor**
   - Gå til din Supabase dashboard
   - Klik på "SQL Editor" i menuen

2. **Kør pgvector extension**
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

3. **Kør similarity funktioner**
   - Kopier indholdet af `create_similarity_functions.sql`
   - Kør det i SQL editor

4. **Opret vector index** (hvis ikke allerede gjort)
   ```sql
   CREATE INDEX IF NOT EXISTS idx_jobs_embedding_vector 
   ON public.jobs USING ivfflat (embedding vector_cosine_ops);
   ```

## Trin 2: Verificer Setup

Kør test-scriptet for at verificere at alt virker:

```bash
cd Semantic
python test_search.py
```

Du skulle se output som:
```
🚀 Starting semantic search test...
✅ Initialized successfully
🔍 Testing search for: 'Er der medicinalfirmaer der søger?'
✅ Generated embedding (1536 dimensions)
✅ Found X results
```

## Trin 3: Generer Embeddings

Hvis du ikke har embeddings endnu, kør embedding generator:

```bash
cd ..
python job_embedding_generator.py
```

## Trin 4: Test Interaktiv Søgning

```bash
cd Semantic
python interactive_search.py
```

## Fejlfinding

### "Could not find the function public.match_jobs"
- Sørg for at du har kørt `create_similarity_functions.sql` i Supabase
- Tjek at funktionen er oprettet i SQL editor

### "No results found"
- Sørg for at jobs har embeddings (kør `job_embedding_generator.py`)
- Tjek at jobs har CFO score >= 1
- Prøv at sænke `match_threshold` fra 0.7 til 0.5

### "OpenAI API key not found"
- Sørg for at `OPENAI_API_KEY` er sat i din `.env` fil
- Eller sæt miljøvariablen: `export OPENAI_API_KEY=din_api_key` 