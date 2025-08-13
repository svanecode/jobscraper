#!/usr/bin/env python3
"""
Refresh OpenAI Vector Store JSON data

Steps:
- Export all jobs where cfo_score >= 1 and deleted_at is null to a single JSON file
- Remove all JSON/JSONL files from the specified OpenAI vector store
- Upload the freshly exported JSON file to the vector store

Env vars:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY (recommended) or SUPABASE_ANON_KEY
  OPENAI_API_KEY

CLI:
  python openai_vectorstore_refresh.py \
    --vector-store-id vs_689c4ba3dd8c8191b4ced38afe9de3f1 \
    --output ./jobs_cfo_gte1.json
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

try:
    # openai>=1.0.0
    from openai import OpenAI
except Exception as e:  # pragma: no cover
    OpenAI = None  # type: ignore

# Prefer httpx for REST fallback
try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None  # type: ignore

# Load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("vectorstore-refresh")

DEFAULT_VECTOR_STORE_ID = "vs_689c4ba3dd8c8191b4ced38afe9de3f1"


def init_supabase() -> Client:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
    )
    if not supabase_url or not supabase_key:
        raise ValueError("Supabase credentials required (SUPABASE_URL + KEY)")
    client = create_client(supabase_url, supabase_key)
    logger.info(
        "✅ Supabase client initialized with %s",
        "SERVICE_ROLE_KEY" if os.getenv("SUPABASE_SERVICE_ROLE_KEY") else "ANON_KEY",
    )
    return client


def fetch_jobs(client: Client, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    # Select only non-vector columns to avoid uploading DB-side vectors
    # Adjust list if your schema differs
    selected_columns = (
        "id,job_id,title,job_url,company,company_url,location,publication_date,"
        "description,created_at,deleted_at,cfo_score,scored_at,last_seen,region"
    )
    query = (
        client.table("jobs")
        .select(selected_columns)
        .is_("deleted_at", "null")
        .gte("cfo_score", 1)
        .order("id", desc=False)
    )
    if limit:
        query = query.limit(limit)
    resp = query.execute()
    rows = resp.data or []
    logger.info("Fetched %d jobs (cfo_score >= 1, not soft-deleted)", len(rows))
    return rows


def write_json_file(records: List[Dict[str, Any]], output_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    logger.info("Wrote JSON file: %s (records=%d)", output_path, len(records))


def init_openai() -> "OpenAI":  # type: ignore[name-defined]
    if OpenAI is None:
        raise RuntimeError("openai package not available")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY required")
    client = OpenAI(api_key=api_key)
    logger.info("✅ OpenAI client initialized")
    return client


def list_vector_store_files(client: "OpenAI", vector_store_id: str) -> List[Dict[str, Any]]:  # type: ignore[name-defined]
    # Try SDK first
    try:
        files: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            page = client.beta.vector_stores.files.list(  # type: ignore[attr-defined]
                vector_store_id=vector_store_id,
                limit=100,
                after=cursor,
            )
            data = getattr(page, "data", [])
            files.extend(data)
            if not getattr(page, "has_more", False):
                break
            cursor = getattr(page, "last_id", None)
            if not cursor:
                break
        logger.info("Vector store has %d files attached", len(files))
        return files
    except AttributeError:
        # Fallback to REST API
        if httpx is None:
            raise RuntimeError("httpx is required for REST fallback but not installed")
        api_key = os.getenv("OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {api_key}", "OpenAI-Beta": "assistants=v2"}
        files: List[Dict[str, Any]] = []
        params: Dict[str, Any] = {"limit": 100}
        url = f"https://api.openai.com/v1/vector_stores/{vector_store_id}/files"
        while True:
            r = httpx.get(url, headers=headers, params=params, timeout=60)
            r.raise_for_status()
            body = r.json()
            data = body.get("data", [])
            files.extend(data)
            if not body.get("has_more"):
                break
            last_id = body.get("last_id")
            if not last_id:
                break
            params["after"] = last_id
        logger.info("Vector store has %d files attached (REST)", len(files))
        return files


def get_file_info(client: "OpenAI", file_id: str) -> Dict[str, Any]:  # type: ignore[name-defined]
    # Try SDK
    try:
        info = client.files.retrieve(file_id)
        return info.model_dump() if hasattr(info, "model_dump") else info.__dict__
    except Exception:
        # REST fallback
        if httpx is None:
            raise
        api_key = os.getenv("OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {api_key}"}
        url = f"https://api.openai.com/v1/files/{file_id}"
        r = httpx.get(url, headers=headers, timeout=60)
        r.raise_for_status()
        return r.json()


def delete_vector_store_file(client: "OpenAI", vector_store_id: str, vs_file_id_or_file_id: str) -> None:  # type: ignore[name-defined]
    try:
        client.beta.vector_stores.files.delete(  # type: ignore[attr-defined]
            vector_store_id=vector_store_id,
            file_id=vs_file_id_or_file_id,
        )
    except AttributeError:
        if httpx is None:
            raise RuntimeError("httpx is required for REST fallback but not installed")
        api_key = os.getenv("OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {api_key}", "OpenAI-Beta": "assistants=v2"}
        url = f"https://api.openai.com/v1/vector_stores/{vector_store_id}/files/{vs_file_id_or_file_id}"
        r = httpx.delete(url, headers=headers, timeout=60)
        r.raise_for_status()


def attach_file_to_vector_store(client: "OpenAI", vector_store_id: str, file_id: str) -> None:  # type: ignore[name-defined]
    try:
        client.beta.vector_stores.files.create(  # type: ignore[attr-defined]
            vector_store_id=vector_store_id,
            file_id=file_id,
        )
    except AttributeError:
        if httpx is None:
            raise RuntimeError("httpx is required for REST fallback but not installed")
        api_key = os.getenv("OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {api_key}", "OpenAI-Beta": "assistants=v2", "Content-Type": "application/json"}
        url = f"https://api.openai.com/v1/vector_stores/{vector_store_id}/files"
        payload = {"file_id": file_id}
        r = httpx.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()


def delete_file_asset(client: "OpenAI", file_id: str) -> None:  # type: ignore[name-defined]
    # Delete the file from your organization (fully removes it)
    try:
        client.files.delete(file_id)
    except Exception:
        if httpx is None:
            raise
        api_key = os.getenv("OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {api_key}"}
        url = f"https://api.openai.com/v1/files/{file_id}"
        r = httpx.delete(url, headers=headers, timeout=60)
        r.raise_for_status()


def upload_file(client: "OpenAI", path: str) -> str:  # type: ignore[name-defined]
    with open(path, "rb") as f:
        uploaded = client.files.create(
            file=f,
            purpose="assistants",
        )
    file_id = getattr(uploaded, "id", None)
    if not file_id:
        raise RuntimeError("Upload did not return a file id")
    logger.info("Uploaded file %s -> id=%s", os.path.basename(path), file_id)
    return file_id


def refresh_vector_store_with_json(
    vector_store_id: str,
    output_json_path: str,
) -> None:
    oa = init_openai()

    # 1) Remove all files from the vector store (ensure a clean slate)
    vs_files = list_vector_store_files(oa, vector_store_id)
    removed = 0
    for vsf in vs_files:
        # Vector store file association id (vsf_...) and underlying file asset id (file-...)
        vsf_id = getattr(vsf, "id", None) or (vsf.get("id") if isinstance(vsf, dict) else None)
        file_id = getattr(vsf, "file_id", None) or (vsf.get("file_id") if isinstance(vsf, dict) else None)
        if not vsf_id and not file_id:
            continue
        try:
            meta = None
            try:
                if file_id:
                    meta = get_file_info(oa, file_id)
            except Exception:
                meta = None
            filename = (meta or {}).get("filename", "") or (meta or {}).get("name", "")
            # First detach from vector store (use vector store file id), then delete the file asset
            if vsf_id:
                delete_vector_store_file(oa, vector_store_id, vsf_id)
            if file_id:
                delete_file_asset(oa, file_id)
            removed += 1
            if filename:
                logger.info("Deleted file: %s (%s)", filename, file_id)
            else:
                logger.info("Deleted file (vsf_id=%s, file_id=%s)", vsf_id, file_id)
        except Exception as e:
            logger.warning("Could not inspect/delete file_id=%s: %s", file_id, e)
    logger.info("Removed %d files from vector store %s", removed, vector_store_id)

    # 2) Upload new JSON file and attach to vector store
    new_file_id = upload_file(oa, output_json_path)
    attach_file_to_vector_store(oa, vector_store_id, new_file_id)
    logger.info(
        "Attached new file to vector store: %s (file_id=%s)", vector_store_id, new_file_id
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh OpenAI vector store with DB JSON")
    parser.add_argument(
        "--vector-store-id",
        dest="vector_store_id",
        default=os.getenv("OPENAI_VECTOR_STORE_ID"),
        help=(
            "OpenAI vector store id (e.g. vs_123...). "
            "Can also be set via OPENAI_VECTOR_STORE_ID or VECTOR_STORE_ID env var."
        ),
    )
    parser.add_argument(
        "--output",
        dest="output",
        default="./jobs_cfo_gte1.json",
        help="Path for the exported JSON file",
    )
    parser.add_argument(
        "--limit",
        dest="limit",
        type=int,
        default=None,
        help="Optional limit for number of records (for testing)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Allow fully env-driven execution (no CLI flags needed)
    vector_store_id = (
        args.vector_store_id
        or os.getenv("OPENAI_VECTOR_STORE_ID")
        or os.getenv("VECTOR_STORE_ID")
        or DEFAULT_VECTOR_STORE_ID
    )
    if not vector_store_id:
        raise SystemExit(
            "Vector store id required. Set OPENAI_VECTOR_STORE_ID (or VECTOR_STORE_ID) in .env"
        )

    output_path = (
        args.output
        or os.getenv("OPENAI_VECTORSTORE_OUTPUT")
        or "./jobs_cfo_gte1.json"
    )
    # Always append a UTC timestamp to ensure a unique filename per run
    def _timestamped_path(path: str) -> str:
        base_dir = os.path.dirname(os.path.abspath(path)) or "."
        base_name = os.path.basename(path)
        stem, ext = os.path.splitext(base_name)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        if not ext:
            ext = ".json"
        return os.path.join(base_dir, f"{stem}_{ts}{ext}")
    output_path = _timestamped_path(output_path)
    limit_env = os.getenv("EXPORT_LIMIT")
    limit = args.limit if args.limit is not None else (int(limit_env) if (limit_env or "").isdigit() else None)

    sb = init_supabase()
    rows = fetch_jobs(sb, limit=limit)
    write_json_file(rows, output_path)

    refresh_vector_store_with_json(
        vector_store_id=vector_store_id,
        output_json_path=output_path,
    )


if __name__ == "__main__":
    main()

