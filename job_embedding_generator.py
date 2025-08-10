#!/usr/bin/env python3
"""
Job Embedding Generator (kvalitet først)

- Bruger OpenAI text-embedding-3-large (3072 dims)
- Genererer/regenere embeddings KUN når fingerprint af (title, company, location, description)
  har ændret sig.
- Bevarer næsten hele teksten (klipper kun hvis vi er meget tæt på modelgrænser).
- Batch-kald for performance, men ingen kvalitetstab.

Kræver env:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY (eller SUPABASE_ANON_KEY – service role anbefales til batch-opdateringer)
  OPENAI_API_KEY
  (valgfrit) EMBEDDING_MODEL (default: text-embedding-3-large)
"""

import asyncio
import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from openai import AsyncOpenAI
from supabase import Client, create_client

# Load .env hvis tilgængelig
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("job-embeddings")


# ---------- Utils ----------
def _norm(t: str) -> str:
    """Let whitespace-normalisering (bevar indhold)."""
    t = (t or "").strip()
    return re.sub(r"\s+", " ", t)


def make_fingerprint(job: Dict) -> str:
    """
    Fingerprint af felter der definerer embeddingens semantik.
    Hvis nogen ændres → regenerer.
    """
    parts = [
        _norm(job.get("title", "")),
        _norm(job.get("company", "")),
        _norm(job.get("location", "")),
        _norm(job.get("description", "")),
    ]
    s = " | ".join(parts)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---------- Generator ----------
class JobEmbeddingGenerator:
    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        embedding_model: Optional[str] = None,
        use_pgvector: bool = True,
    ):
        # Supabase
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = (
            supabase_key
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_ANON_KEY")
        )

        if not (self.supabase_url and self.supabase_key):
            raise ValueError("Supabase credentials required (URL + KEY).")

        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        logger.info(
            "Supabase client initialized with %s",
            "SERVICE_ROLE_KEY" if os.getenv("SUPABASE_SERVICE_ROLE_KEY") else "ANON_KEY",
        )

        # OpenAI
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY required.")
        self.openai_client = AsyncOpenAI(api_key=self.openai_api_key)

        # Model
        self.embedding_model = embedding_model or os.getenv(
            "EMBEDDING_MODEL", "text-embedding-3-large"
        )
        logger.info(f"Using embedding model: {self.embedding_model}")

        # Lager-type: pgvector vs. float8[] (fallback)
        self.use_pgvector = use_pgvector  # kun informativt i dette script
        if not use_pgvector:
            logger.info("Using float8[] fallback for 'embedding' column (no pgvector).")

        # Tekstlængde-konfiguration (kvalitet først)
        self.MAX_CHARS = 7500  # rigeligt under modelgrænsen

    # ---------- Udvælg kandidater ----------
    def get_candidates(self, max_jobs: Optional[int] = None) -> List[Dict]:
        """
        Hent aktive jobs (cfo_score >= 1) og beslut lokalt om de skal (re)embeddes
        ved fingerprint-sammenligning.
        """
        query = (
            self.supabase.table("jobs")
            .select(
                "id,job_id,title,company,location,description,"
                "embedding,embedding_fingerprint,cfo_score,deleted_at"
            )
            .is_("deleted_at", "null")
            .gte("cfo_score", 1)
            .order("id", desc=False)
        )
        if max_jobs:
            query = query.limit(max_jobs)

        resp = query.execute()
        rows = resp.data or []

        # Lokal beslutning: (re)embed hvis ingen embedding, intet fingerprint eller mismatch
        def should_embed(job: Dict) -> bool:
            new_fp = make_fingerprint(job)
            old_fp = job.get("embedding_fingerprint")
            has_embedding = job.get("embedding") is not None
            return (not has_embedding) or (not old_fp) or (old_fp != new_fp)

        candidates = [r for r in rows if should_embed(r)]
        logger.info(
            "Kandidater fundet: %d (ud af %d hentede).", len(candidates), len(rows)
        )
        return candidates

    # ---------- Tekst til embedding ----------
    def create_embedding_text(self, job: Dict) -> str:
        title = _norm(job.get("title", "") or "Job")
        company = _norm(job.get("company", "") or "Company")
        location = _norm(job.get("location", "") or "Location not specified")
        desc = _norm(job.get("description", "") or "")

        head = f"Company: {company}\nTitle: {title}\nLocation: {location}\n"
        body = f"Description: {company} - {title}. {desc}".strip()

        text = f"{head}{body}".strip()

        # Bevar så meget som muligt; klip kun hvis meget lang
        if len(text) > self.MAX_CHARS:
            keep_head = head
            remaining = self.MAX_CHARS - len(keep_head) - len("Description: ")
            clipped = (f"{company} - {title}. " + desc)[: max(0, remaining)] + "…"
            text = keep_head + "Description: " + clipped

        return text

    # ---------- OpenAI-kald ----------
    async def generate_embeddings_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> Optional[List[List[float]]]:
        use_model = model or self.embedding_model
        last_err = None
        for attempt in range(3):
            try:
                res = await self.openai_client.embeddings.create(
                    model=use_model, input=texts
                )
                return [item.embedding for item in res.data]
            except Exception as e:
                last_err = e
                wait = 2 ** attempt
                logger.warning(
                    "Batch embedding fejlede (forsøg %d/3): %s. Prøver igen om %ss",
                    attempt + 1,
                    e,
                    wait,
                )
                await asyncio.sleep(wait)
        logger.error("Batch embedding mislykkedes efter 3 forsøg: %s", last_err)
        return None

    # ---------- DB update ----------
    def _update_embedding_row(self, job: Dict, embedding: List[float]) -> bool:
        new_fp = make_fingerprint(job)
        payload = {
            "embedding": list(embedding),
            "embedding_fingerprint": new_fp,
            "embedding_created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            resp = (
                self.supabase.table("jobs")
                .update(payload)
                .eq("id", job["id"])  # brug id; skift til job_id hvis det er din stabile nøgle
                .execute()
            )
            return bool(resp.data)
        except Exception as e:
            logger.error("DB update fejlede for job id=%s: %s", job.get("id"), e)
            return False

    # ---------- Orkestrering ----------
    async def generate_all_embeddings(
        self, batch_size: int = 32, max_jobs: Optional[int] = None, delay: float = 0.5
    ):
        jobs = self.get_candidates(max_jobs)
        if not jobs:
            logger.info("Alle embeddings er up-to-date (fingerprints matcher).")
            return

        logger.info("Skal generere/regenerere embeddings for %d job(s).", len(jobs))

        total_ok = 0
        total_err = 0

        for i in range(0, len(jobs), batch_size):
            batch = jobs[i : i + batch_size]
            bno = i // batch_size + 1
            btot = (len(jobs) + batch_size - 1) // batch_size
            logger.info("Behandler batch %d/%d (%d jobs)", bno, btot, len(batch))

            # For kvalitets-søgning: skab tekster (dedupliker identiske tekster for at spare kald)
            texts = [self.create_embedding_text(j) for j in batch]
            text_to_indices: Dict[str, List[int]] = {}
            for idx, t in enumerate(texts):
                text_to_indices.setdefault(t, []).append(idx)
            unique_texts = list(text_to_indices.keys())

            embs_unique = await self.generate_embeddings_batch(unique_texts)
            if embs_unique is None:
                total_err += len(batch)
                continue

            # Map embeddings tilbage til hver post
            ok_in_batch = 0
            for utxt, emb in zip(unique_texts, embs_unique):
                for idx in text_to_indices[utxt]:
                    job = batch[idx]
                    if self._update_embedding_row(job, emb):
                        ok_in_batch += 1
                    else:
                        total_err += 1

            total_ok += ok_in_batch
            logger.info(
                "Batch %d/%d færdig: %d/%d opdateret.",
                bno,
                btot,
                ok_in_batch,
                len(batch),
            )

            if i + batch_size < len(jobs) and delay > 0:
                await asyncio.sleep(delay)

        logger.info("=== EMBEDDING GENERATION COMPLETE ===")
        logger.info("Jobs planlagt: %d", len(jobs))
        logger.info("Opdateret OK: %d", total_ok)
        logger.info("Fejl: %d", total_err)

    # ---------- Stats ----------
    def get_embedding_stats(self) -> Dict:
        try:
            total_resp = (
                self.supabase.table("jobs")
                .select("id", count="exact")
                .is_("deleted_at", "null")
                .gte("cfo_score", 1)
                .execute()
            )
            total_rel = total_resp.count or 0

            with_emb_resp = (
                self.supabase.table("jobs")
                .select("id", count="exact")
                .is_("deleted_at", "null")
                .gte("cfo_score", 1)
                .not_.is_("embedding", "null")
                .execute()
            )
            with_emb = with_emb_resp.count or 0

            return {
                "total_relevant_jobs": total_rel,
                "jobs_with_embeddings": with_emb,
                "jobs_needing_embeddings": max(0, total_rel - with_emb),
                "embedding_coverage": (with_emb / total_rel * 100) if total_rel else 0,
            }
        except Exception as e:
            logger.error("Fejl ved stats: %s", e)
            return {
                "total_relevant_jobs": 0,
                "jobs_with_embeddings": 0,
                "jobs_needing_embeddings": 0,
                "embedding_coverage": 0,
            }


# ---------- Main ----------
async def main():
    gen = JobEmbeddingGenerator(
        use_pgvector=True  # sæt False hvis du kører fallback (float8[])
    )

    stats = gen.get_embedding_stats()
    logger.info("=== INITIAL STATISTICS ===")
    logger.info("Total relevant jobs (cfo_score >= 1): %s", stats["total_relevant_jobs"])
    logger.info("Jobs with embeddings: %s", stats["jobs_with_embeddings"])
    logger.info("Jobs needing embeddings: %s", stats["jobs_needing_embeddings"])
    logger.info("Embedding coverage: %.1f%%", stats["embedding_coverage"])

    await gen.generate_all_embeddings(
        batch_size=32,   # større batch er fint – få daglige opgaver
        max_jobs=None,   # processér alle kandidater
        delay=0.5
    )

    final = gen.get_embedding_stats()
    logger.info("=== FINAL STATISTICS ===")
    logger.info("Total relevant jobs (cfo_score >= 1): %s", final["total_relevant_jobs"])
    logger.info("Jobs with embeddings: %s", final["jobs_with_embeddings"])
    logger.info("Jobs needing embeddings: %s", final["jobs_needing_embeddings"])
    logger.info("Embedding coverage: %.1f%%", final["embedding_coverage"])


if __name__ == "__main__":
    asyncio.run(main())