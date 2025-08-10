#!/usr/bin/env python3
"""
Location ➜ Region backfiller for public.jobs

What it does
------------
1) Reads jobs in keyset-paginated batches (no 1000-row limit issues).
2) For each job missing region, extracts a canonical "city token" from `location`
   (handles DK district suffixes like "København Ø/S/V/N/NV/SV/K", "Aarhus C/N",
   "Odense SØ/SV/M", "Aalborg Øst", "Randers SV", "Viby J", "Kgs./Kongens Lyngby", etc.)
3) Resolves that city to one of these regions:
      - Hovedstaden
      - Sjælland
      - Fyn
      - Syd- og Sønderjylland
      - Midtjylland
      - Nordjylland
      - Udlandet
      - Ukendt
4) Caches new city→region pairs into public.city_to_region for future runs.
5) Updates jobs.region (works whether region is TEXT or TEXT[]).
6) Uses OpenAI only as a last resort; you can set MODEL_NAME to "gpt-5-thinking"
   if available in your org, otherwise default is "gpt-4o-mini".

IMPORTANT: Based on the current database schema (region text[]), you MUST set:
   export JOBS_REGION_IS_ARRAY=true

Env vars
--------
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY (preferred) or SUPABASE_ANON_KEY
OPENAI_API_KEY
MODEL_NAME (optional, default: "gpt-4o-mini"; you may set "gpt-5-thinking")
JOBS_REGION_IS_ARRAY = "true" if jobs.region is TEXT[]; anything else => TEXT

Tables assumed
--------------
public.jobs:
  job_id TEXT PRIMARY KEY (or unique)
  location TEXT
  description TEXT (optional)
  region TEXT or TEXT[] (this script supports both)
  deleted_at TIMESTAMP NULL (treated as soft-deleted if not null)

public.city_to_region:
  city TEXT PRIMARY KEY
  region TEXT NOT NULL
  -- allowed values include: the 6 DK regions + 'Udlandet' + 'Ukendt'
"""

import asyncio
import os
import re
import json
import unicodedata
from typing import Optional, Dict, List

from supabase import create_client, Client
from openai import AsyncOpenAI

# -------- ENV --------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-5")
FALLBACK_MODEL_NAME = os.getenv("FALLBACK_MODEL_NAME", "gpt-5-thinking")
STRICT_GPT5 = os.getenv("STRICT_GPT5", "false").lower() == "true"

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE key env.")

if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY env.")

# If jobs.region is an array (text[]), set env JOBS_REGION_IS_ARRAY=true
JOBS_REGION_IS_ARRAY = os.getenv("JOBS_REGION_IS_ARRAY", "false").lower() == "true"

# Warn users if they haven't set the environment variable correctly
if not JOBS_REGION_IS_ARRAY:
    print("WARNING: JOBS_REGION_IS_ARRAY is not set to 'true'")
    print("Based on the database schema (region text[]), you should set:")
    print("export JOBS_REGION_IS_ARRAY=true")
    print("Continuing with text mode, but this may cause errors...")

VALID_REGIONS = {
    "Hovedstaden",
    "Sjælland",
    "Fyn",
    "Syd- og Sønderjylland",
    "Midtjylland",
    "Nordjylland",
    "Udlandet",
    "Ukendt",
}

# Region keywords disabled – rely on GPT-5 classification only
REGION_KEYWORDS: Dict[str, str] = {}

# Canonical aliases disabled – rely on GPT-5 classification only
DEFAULT_ALIASES: Dict[str, str] = {}

# Seed guardrails disabled – rely on GPT-5 classification only
SEED_KNOWN_CITY_REGION: Dict[str, str] = {}

NON_CITY_PATTERNS = [
    r"\b(company|firma|virksomhed|holding|group|department|afdeling|team)\b",
    r"\b(consulting|consultant|advisory|advisers?|services?|solutions?|tech|digital)\b",
    r"\b(manager|director|chief|head|senior|junior|assistant|partner)\b",
    r"\b(accountant|controller|cfo|finance|økonomi|accounting|bookkeeping|bogholderi)\b",
    r"\b(interim|vikariat|temporary|permanent|full[- ]?time|part[- ]?time)\b",
    r"\b(remote|hybrid|onsite|flex|hjemmearbejde)\b",
    r"\b(denmark|danmark|danish|scandinavia|europe|international|udland(et)?)\b",
    r"\b(office|kontor|location|area|region|zone)\b",
    r"\b(center|centre|park|plaza|street|road|avenue|vej|gade)\b",
    r"^\d{4}\b",
]

def _is_valid_city(c: str) -> bool:
    if not c or len(c) < 2 or len(c) > 50:
        return False
    cl = c.lower()
    for pat in NON_CITY_PATTERNS:
        if re.search(pat, cl):
            return False
    # avoid long sentences
    if len(cl.split()) >= 5:
        return False
    return True

def _clean_city_token(token: str) -> str:
    t = (token or "").strip()
    t = re.sub(r"\s+og\s+mulighed\s+for\s+hjemmearbejde.*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+(remote|hybrid|onsite).*?$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*\(.*?\)\s*", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" ,-/")
    return t

def _best_token_from_location(location: str) -> str:
    loc = (location or "").strip()
    if not loc:
        return ""

    loc_l = loc.lower()
    # Region keyword shortcut disabled – always parse tokens

    raw_tokens = re.split(r",|/|\s-\s| - |\sog\s|\sand\s|\|", loc, flags=re.IGNORECASE)
    tokens = [_clean_city_token(t) for t in raw_tokens if _clean_city_token(t)]

    normalized: List[str] = []
    for t in tokens:
        tl = t.lower()
        if tl in DEFAULT_ALIASES:
            normalized.append(DEFAULT_ALIASES[tl])
            continue

        # pattern like "<base> <district>"
        m = re.match(r"^([a-zæøå]+)\s+[a-zæøå]{1,3}$", tl)
        if m:
            normalized.append(m.group(1))
            continue

        normalized.append(tl)

    for cand in normalized:
        if _is_valid_city(cand):
            return cand

    return ""

def _norm_city(city: str) -> str:
    return _normalize_city_input(city)

def _normalize_city_input(city: str) -> str:
    """Normalize user/HTML-sourced city strings.
    - Trim and lowercase
    - Unicode normalize (NFC)
    - Repair common UTF-8/Latin1 mojibake for Danish letters
    """
    c = (city or "").strip()
    if not c:
        return ""
    # Try latin1->utf8 roundtrip fix (e.g. 'skÃ¦rbÃ¦k' -> 'skærbæk')
    try:
        recoded = c.encode("latin-1").decode("utf-8")
        if recoded:
            c = recoded
    except Exception:
        pass

    # Normalize to NFC and lowercase for matching
    c = unicodedata.normalize("NFC", c).lower()
    # Repair common mojibake sequences
    replacements = {
        "\u00c3\u00a6": "æ",  # Ã¦
        "\u00c3\u00a5": "å",  # Ã¥
        "\u00c3\u00b8": "ø",  # Ã¸
        "\u00c3\u0086": "Æ",  # Ã (rare)
        "\u00c3\u0085": "Å",  # Ã (rare)
        "\u00c3\u0098": "Ø",  # Ã (rare)
        "Ã¦": "æ",
        "Ã¥": "å",
        "Ã¸": "ø",
        "Ã…": "Å",
        "Ã˜": "Ø",
        "Ã†": "Æ",
        "Ã©": "é",
    }
    for bad, good in replacements.items():
        if bad in c:
            c = c.replace(bad, good)
    return c

# --------- Resolver ---------
class RegionResolver:
    def __init__(self, sb: Client, ai: AsyncOpenAI):
        self.sb = sb
        self.ai = ai
        self.city_map: Dict[str, str] = {}     # cache from DB (lowercase city -> region)
        self.known_city_region: Dict[str, str] = dict(SEED_KNOWN_CITY_REGION)  # guardrail (empty)
        self.aliases: Dict[str, str] = dict(DEFAULT_ALIASES)  # empty
        self._warned_models: set[str] = set()

    def load_city_map(self, page_size: int = 1000):
        """Keyset pagination over city_to_region (by city) to surpass 1000-row cap."""
        last_city = None
        while True:
            q = (
                self.sb.table("city_to_region")
                .select("city,region")
                .order("city", desc=False)
                .limit(page_size)
            )
            if last_city:
                q = q.gt("city", last_city)
            resp = q.execute()
            rows = resp.data or []
            if not rows:
                break
            for r in rows:
                c = (r["city"] or "").strip()
                if not c:
                    continue
                self.city_map[c.lower()] = r["region"]
            last_city = rows[-1]["city"]

    def _lookup_cached(self, city: str) -> Optional[str]:
        cl = city.lower()
        if cl in self.city_map:
            return self.city_map[cl]
        # alias to canonical then lookup
        if cl in self.aliases:
            ali = self.aliases[cl].lower()
            return self.city_map.get(ali)
        return None

    def upsert_city_region(self, city: str, region: str) -> str:
        city = _norm_city(city)
        region = region if region in VALID_REGIONS else "Ukendt"
        self.sb.table("city_to_region").upsert({"city": city, "region": region}, on_conflict="city").execute()
        self.city_map[city.lower()] = region
        return region

    def _deterministic_region(self, city: str) -> Optional[str]:
        """Only use cache hit; otherwise defer to GPT-5 classification."""
        cl = city.lower()
        if cl in self.city_map:
            return self.city_map[cl]
        return None

    async def classify_region_with_model(self, city: str, location_hint: str, description_hint: str) -> str:
        city = _normalize_city_input(city)
        location_hint = (location_hint or "").strip()
        description_hint = (description_hint or "")[:600]

        system_msg = (
            "Du er en dansk sted-til-region klassifikationsmodel. "
            "Dit output SKAL være et funktionskald til pick_region med et felt 'region' som er én af: "
            ", ".join(sorted(list(VALID_REGIONS))) + ". "
            "Ret stavefejl, diakritik og tydelig mojibake (fx 'skÃ¦rbÃ¦k' => 'skærbæk'). "
            "Antag Danmark med mindre andet er tydeligt. Hvis usikker, vælg 'Ukendt'."
        )
        user_msg = (
            f"By: {city}\n"
            f"Lokationstekst: {location_hint}\n"
            f"Kontekst (uddrag): {description_hint}"
        )

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "pick_region",
                    "description": "Vælg præcis én region for byen",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "region": {
                                "type": "string",
                                "enum": list(VALID_REGIONS),
                            }
                        },
                        "required": ["region"],
                        "additionalProperties": False,
                    },
                },
            }
        ]

        async def _try_model(model_name: str) -> Optional[str]:
            try:
                resp = await self.ai.chat.completions.create(
                    model=model_name,
                    temperature=0,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    tools=tools,
                    tool_choice={"type": "function", "function": {"name": "pick_region"}},
                )
            except Exception:
                if model_name not in self._warned_models:
                    print(f"WARN: LLM call failed for model {model_name}, falling back")
                    self._warned_models.add(model_name)
                # Try plain text fallback without tools
                try:
                    resp = await self.ai.chat.completions.create(
                        model=model_name,
                        temperature=0,
                        max_tokens=8,
                        messages=[
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_msg + "\nSvar KUN med exakt regionsnavnet."},
                        ],
                    )
                except Exception:
                    if STRICT_GPT5 and model_name == MODEL_NAME:
                        # Strict mode: do not continue to other models
                        return None
                    return None

            msg = resp.choices[0].message
            # Prefer tool call
            tool_calls = getattr(msg, "tool_calls", None) or []
            if tool_calls:
                for tc in tool_calls:
                    if getattr(tc, "function", None) and tc.function.name == "pick_region":
                        try:
                            args = json.loads(tc.function.arguments or "{}")
                            region = args.get("region")
                            if region in VALID_REGIONS:
                                return region
                        except Exception:
                            pass
            # Fallback to plain text if tool call missing
            text = (msg.content or "").strip()
            text = re.sub(r"\s+", " ", text)
            if text in VALID_REGIONS:
                return text
            return None

        # Try primary model then fallback
        model_sequence = (MODEL_NAME,) if STRICT_GPT5 else (MODEL_NAME, FALLBACK_MODEL_NAME, "gpt-4o", "gpt-4o-mini")
        for model_name in model_sequence:
            out = await _try_model(model_name)
            if out in VALID_REGIONS:
                return out
            await asyncio.sleep(0.2)

        return "Ukendt"

    async def resolve_and_cache_region(self, city: str, location_hint: str, description_hint: str) -> str:
        city = _norm_city(city)
        if not city:
            return "Ukendt"

        # No region keyword shortcut — rely on GPT-5

        cached = self._lookup_cached(city)
        if cached in VALID_REGIONS:
            return cached

        det = self._deterministic_region(city)
        if det:
            # cache hit already present
            return det

        # LLM fallback
        region = await self.classify_region_with_model(city, location_hint, description_hint)
        if region and region != "Ukendt":
            self.upsert_city_region(city, region)
            return region
        # Do not cache 'Ukendt'; return as-is
        return region

    def update_job_region(self, job_id: str, region: str) -> bool:
        # Validate and normalize region
        if not region or region.strip() == "":
            region = "Ukendt"
        elif region not in VALID_REGIONS:
            print(f"WARNING: Invalid region '{region}' for job {job_id}, using 'Ukendt'")
            region = "Ukendt"
        
        try:
            # For PostgreSQL arrays, we need to use proper array syntax
            if JOBS_REGION_IS_ARRAY:
                # Use PostgreSQL array literal syntax: {value}
                payload = {"region": f"{{{region}}}"}
                print(f"DEBUG: Updating job {job_id} with array payload: {payload}")
            else:
                payload = {"region": region}
                print(f"DEBUG: Updating job {job_id} with text payload: {payload}")
            resp = self.sb.table("jobs").update(payload).eq("job_id", job_id).execute()
            return bool(resp.data)
        except Exception as e:
            print(f"ERROR: Failed to update job {job_id} with region '{region}': {e}")
            return False


# --------- Keyset scan over jobs (>1000) ---------
def iter_jobs_in_keyset(sb: Client, page_size: int = 1000):
    """
    Yields jobs in ascending job_id keyset pages, regardless of 1000-row cap.
    We *do not* filter by region in SQL to avoid array literal issues; we filter in Python.
    """
    last_job_id = None
    while True:
        q = (
            sb.table("jobs")
            .select("job_id, region, location, description")
            .is_("deleted_at", "null")
            .order("job_id", desc=False)
            .limit(page_size)
        )
        if last_job_id:
            q = q.gt("job_id", last_job_id)
        resp = q.execute()
        rows = resp.data or []
        if not rows:
            break
        for r in rows:
            yield r
        last_job_id = rows[-1]["job_id"]


def job_needs_region(row: dict) -> bool:
    """
    Decide in Python if a job needs region filled, avoiding PostgREST array literal issues.
    Supports both TEXT and TEXT[] schema.
    """
    reg = row.get("region", None)
    job_id = row.get("job_id", "unknown")
    
    if reg is None:
        print(f"DEBUG: Job {job_id} has no region field")
        return True
    
    # Array case: empty array or [""] => needs region
    if isinstance(reg, list):
        print(f"DEBUG: Job {job_id} has array region: {reg} (type: {type(reg)})")
        if len(reg) == 0:
            return True
        if len(reg) == 1 and (not isinstance(reg[0], str) or reg[0].strip() == ""):
            return True
        return False
    
    # Text case
    if isinstance(reg, str):
        print(f"DEBUG: Job {job_id} has text region: '{reg}' (type: {type(reg)})")
        return reg.strip() == ""
    
    # Unknown type -> treat as missing
    print(f"DEBUG: Job {job_id} has unknown region type: {type(reg)}, value: {reg}")
    return True


# --------- Runner ---------
async def main():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    ai = AsyncOpenAI(api_key=OPENAI_API_KEY)

    resolver = RegionResolver(sb, ai)

    # 1) Load current city map with keyset pagination
    resolver.load_city_map()

    updated = 0
    scanned = 0

    # 2) Walk jobs with keyset; filter missing region in Python
    async def process_row(row: dict):
        nonlocal updated
        job_id = row["job_id"]
        location = (row.get("location") or "").strip()
        description = (row.get("description") or "")

        # extract best city token
        city = _best_token_from_location(location)

        # short-circuit: if the "city" is actually a region keyword ("Vestjylland" etc.)
        if city in REGION_KEYWORDS:
            region = REGION_KEYWORDS[city]
        else:
            # if no city token, try a very light secondary pass from description
            if not city:
                # very conservative: look for "i <By>"
                m = re.search(r"\bi\s+([A-ZÆØÅ][a-zæøå]{2,}(?:\s+[A-ZÆØÅ][a-zæøå]{2,})*)\b", description[:300])
                if m:
                    guess = _clean_city_token(m.group(1)).lower()
                    if _is_valid_city(guess):
                        city = guess
            # resolve
            region = await resolver.resolve_and_cache_region(
                city=city,
                location_hint=location,
                description_hint=description,
            )

        if region != "Ukendt":
            if resolver.update_job_region(job_id, region):
                updated += 1

    # Process sequentially (jobs/day is small); you can make this concurrent if needed
    for row in iter_jobs_in_keyset(sb, page_size=1000):
        scanned += 1
        print(f"DEBUG: Processing job {row.get('job_id', 'unknown')}")
        if not job_needs_region(row):
            print(f"DEBUG: Job {row.get('job_id', 'unknown')} already has region, skipping")
            continue
        await process_row(row)

    print(f"Scanned: {scanned} jobs")
    print(f"Updated: {updated} jobs")

if __name__ == "__main__":
    asyncio.run(main())