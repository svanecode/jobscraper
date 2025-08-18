#!/usr/bin/env python3
"""
Job Information Scraper
Scrapes missing company information from individual Jobindex job URLs
and fills only missing fields in Supabase.

Key features:
- Robust keyset pagination that overkommer Supabase 1000-row limit
  via komposit-cursor på (created_at DESC, job_id DESC) – undgår
  både dubletter og huller når flere rækker har samme created_at.
- Robust Playwright-setup (timeouts, retries, cookie-banner handling)
- Blokerer tunge assets (images/fonts/media) men bevarer CSS
- Normaliserer whitespace; resolver relative company-URLs
- Concurrency-control + throttling
- Sikker opdatering: udfylder kun NULL/tomme DB-felter
"""

import asyncio
import logging
import os
import re
from typing import List, Dict, Optional
from urllib.parse import urljoin
from time import sleep

from playwright.async_api import async_playwright
from supabase import create_client, Client
try:  # optional fast-path deps
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None  # type: ignore
try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore

# --------- ENV ---------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --------- LOGGING ---------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# PostgREST OR filter for null or empty-string fields (empty string is represented as eq.)
EMPTY_STR_FILTER = (
    "company.is.null,company.eq.,"
    "company_url.is.null,company_url.eq.,"
    "description.is.null,description.eq."
)

# --------- SCRAPER ---------
class JobInfoScraper:
    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        self.base_url = "https://www.jobindex.dk"

        # Supabase
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = (
            supabase_key
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_ANON_KEY")
        )
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Supabase credentials required")

        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        if os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
            logger.info("✅ Supabase client initialized with SERVICE_ROLE_KEY (RLS bypass)")
        else:
            logger.info("✅ Supabase client initialized with ANON_KEY")

        # Playwright
        self._playwright = None
        self._browser = None
        self._context = None

        # HTTP client (fast path)
        self._http_client: Optional["httpx.AsyncClient"] = None

    # ---------- Browser lifecycle ----------
    async def setup_browser(self):
        if self._browser:
            return

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-features=VizDisplayCompositor",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-sync",
                "--disable-translate",
                "--hide-scrollbars",
                "--mute-audio",
                "--no-first-run",
                "--safebrowsing-disable-auto-update",
                "--ignore-certificate-errors",
                "--ignore-ssl-errors",
                "--ignore-certificate-errors-spki-list",
                "--disable-setuid-sandbox",
                "--disable-accelerated-2d-canvas",
                "--no-zygote",
            ],
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "da-DK,da;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate",
                "Upgrade-Insecure-Requests": "1",
            },
            bypass_csp=True,
        )

        # Block heavy assets (keep CSS)
        async def route_interceptor(route):
            req = route.request
            if req.resource_type in {"image", "font", "media", "script"}:
                return await route.abort()
            return await route.continue_()

        await self._context.route("**/*", route_interceptor)

    async def teardown_browser(self):
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
        finally:
            if self._playwright:
                await self._playwright.stop()
            self._playwright = None
            self._browser = None
            self._context = None

    # ---------- HTTP client lifecycle (fast path) ----------
    async def setup_http_client(self):
        if self._http_client is not None or httpx is None:
            return
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "da-DK,da;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
        }
        timeout = httpx.Timeout(15.0, connect=10.0, read=15.0)
        self._http_client = httpx.AsyncClient(http2=True, headers=headers, timeout=timeout, follow_redirects=True)

    async def teardown_http_client(self):
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            finally:
                self._http_client = None

    # ---------- Supabase retry wrapper ----------
    def _sb_retry(self, build_query_callable, tries: int = 3):
        """Kør en Supabase query med simple retries/backoff."""
        last_err = None
        for i in range(tries):
            try:
                q = build_query_callable()
                return q.execute()
            except Exception as e:
                last_err = e
                if i < tries - 1:
                    sleep(0.5 * (2 ** i))
        raise last_err

    # ---------- DB pagination (robust komposit-cursor) ----------
    def iter_missing_info_jobs(self, batch_size: int = 1000):
        """
        Yield aktive jobs med manglende company/company_url/description.
        Keyset pagination på (created_at DESC, job_id DESC) for at undgå
        dubletter/udfald når flere rækker deler samme created_at.
        """
        last_created_at: Optional[str] = None
        last_job_id: Optional[str] = None  # job_id er tekst (fx 'h1586919')

        while True:
            def build_query():
                q = (
                    self.supabase
                    .table("jobs")
                    .select("job_id, created_at")
                    .is_("deleted_at", "null")
                    .or_(EMPTY_STR_FILTER)
                    .order("created_at", desc=True)
                    .order("job_id", desc=True)
                    .limit(batch_size)
                )
                if last_created_at is not None and last_job_id is not None:
                    # (created_at < last_created_at) OR (created_at = last_created_at AND job_id < last_job_id)
                    q = q.or_(f"created_at.lt.{last_created_at},and(created_at.eq.{last_created_at},job_id.lt.{last_job_id})")
                return q

            resp = self._sb_retry(build_query)
            rows = resp.data or []
            if not rows:
                break

            for r in rows:
                yield r

            # Sæt ny cursor til sidste række i den nuværende side
            tail = rows[-1]
            last_created_at = tail["created_at"]
            last_job_id = tail["job_id"]

    # ---------- Helpers ----------
    @staticmethod
    def _normalize_whitespace(text: Optional[str]) -> Optional[str]:
        if not isinstance(text, str):
            return text
        return re.sub(r"\s+", " ", text.strip())

    def _abs_url(self, href: Optional[str]) -> Optional[str]:
        if not href:
            return None
        href = href.strip()
        if not href:
            return None
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("/"):
            return urljoin(self.base_url, href)
        return href

    async def _try_dismiss_cookies(self, page):
        try:
            selectors = [
                'button:has-text("Accepter")',
                'button:has-text("Acceptér")',
                'button:has-text("OK")',
                'text="Accepter alle"',
            ]
            for sel in selectors:
                el = await page.query_selector(sel)
                if el:
                    await el.click()
                    await asyncio.sleep(0.4)
                    break
        except Exception:
            pass

    # ---------- Scrape single job ----------
    async def scrape_job_info_http(self, job_id: str) -> Optional[Dict]:
        """Fast path: fetch and parse with HTTP client. Fallback to browser if needed."""
        await self.setup_http_client()
        if self._http_client is None or BeautifulSoup is None:
            return None
        job_url = f"{self.base_url}/vis-job/{job_id}"
        info: Dict[str, Optional[str]] = {}
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                resp = await self._http_client.get(job_url)
                if resp.status_code >= 400:
                    last_err = RuntimeError(f"HTTP {resp.status_code}")
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                html = resp.text
                soup = BeautifulSoup(html, "lxml")

                # ------- Title -------
                title = None
                t_el = soup.select_one("h1.sr-only") or soup.select_one("h4 a") or soup.select_one("h1")
                if t_el and t_el.get_text(strip=True):
                    title = self._normalize_whitespace(t_el.get_text(" "))
                if not title:
                    pt = soup.title.get_text(strip=True) if soup.title else None
                    if pt and " | Job" in pt:
                        title = self._normalize_whitespace(pt.split(" | Job")[0])
                if title and title.startswith("Jobannonce: "):
                    title = title[len("Jobannonce: ") :].strip()
                info["title"] = title

                # ------- Company + URL -------
                company_name = None
                company_url = None
                comp_el = soup.select_one(".jix-toolbar-top__company")
                if comp_el:
                    raw = self._normalize_whitespace(comp_el.get_text(" ") or "") or ""
                    if raw.endswith(" søger for kunde"):
                        raw = raw.replace(" søger for kunde", "").strip()
                    company_name = raw or None
                    link_el = comp_el.select_one("a")
                    if link_el and link_el.get("href"):
                        company_url = self._abs_url(link_el.get("href"))
                # Fallbacks
                if not company_name:
                    job_link = soup.select_one("h4 a")
                    if job_link and job_link.get("href") and "frivilligjob.dk" in job_link.get("href") and title and " - " in title:
                        company_name = title.split(" - ")[-1].strip()
                if not company_name:
                    body_text = self._normalize_whitespace(soup.get_text(" ") or "") or ""
                    for pat in [
                        r"([A-ZÆØÅ][A-Za-zÆØÅæøå0-9&\.\-\s]+?)\s+A/S",
                        r"([A-ZÆØÅ][A-Za-zÆØÅæøå0-9&\.\-\s]+?)\s+ApS",
                    ]:
                        m = re.search(pat, body_text, re.IGNORECASE)
                        if m:
                            company_name = self._normalize_whitespace(m.group(1))
                            break
                info["company"] = company_name
                info["company_url"] = company_url

                # ------- Description -------
                description = None
                primary = soup.select_one(".jix_robotjob-inner")
                if primary:
                    # prefer first long <p>
                    p = next((p for p in primary.find_all("p") if self._normalize_whitespace(p.get_text(" ") or "") and len(self._normalize_whitespace(p.get_text(" ") or "")) > 40), None)
                    if p:
                        description = self._normalize_whitespace(p.get_text(" ") or "")
                if not description:
                    job_content = soup.select_one(".PaidJob-inner") or primary
                    if job_content:
                        parts: List[str] = []
                        for p in job_content.find_all("p"):
                            t = self._normalize_whitespace(p.get_text(" ") or "")
                            if t and len(t) > 40:
                                parts.append(t)
                        if parts:
                            description = " ".join(parts)
                if not description:
                    body_text = self._normalize_whitespace(soup.get_text(" ") or "") or ""
                    patterns = [
                        r"(?:Vi søger|We are looking for|We seek).*?(?=\n\n|\n[A-ZÆØÅ]|$)",
                        r"(?:Jobbet|The position|The role).*?(?=\n\n|\n[A-ZÆØÅ]|$)",
                        r"(?:Ansvar|Responsibilities|Duties).*?(?=\n\n|\n[A-ZÆØÅ]|$)",
                    ]
                    for pat in patterns:
                        matches = re.findall(pat, body_text, re.DOTALL | re.IGNORECASE)
                        if matches:
                            cand = self._normalize_whitespace(matches[0])
                            if cand and len(cand) > 40:
                                description = cand
                                break
                if description:
                    for pat in [
                        r"Indrykket:.*?(?=\n|$)",
                        r"Hentet fra.*?(?=\n|$)",
                        r"Se jobbet.*?(?=\n|$)",
                        r"Anbefalede job.*?(?=\n|$)",
                        r"Gem.*?(?=\n|$)",
                        r"Del.*?(?=\n|$)",
                        r"Kopier.*?(?=\n|$)",
                        r"For jobsøgere.*?(?=\n|$)",
                        r"For arbejdsgivere.*?(?=\n|$)",
                        r"Jobsøgning.*?(?=\n|$)",
                        r"Arbejdspladser.*?(?=\n|$)",
                        r"Test dig selv.*?(?=\n|$)",
                        r"Guides.*?(?=\n|$)",
                        r"Kurser.*?(?=\n|$)",
                        r"Log ind.*?(?=\n|$)",
                        r"Opret profil.*?(?=\n|$)",
                    ]:
                        description = re.sub(pat, "", description, flags=re.IGNORECASE)
                    description = self._normalize_whitespace(description)
                    if description and len(description) < 20:
                        description = None
                info["description"] = description

                # ------- Location -------
                location = None
                loc_el = soup.select_one(".jix_robotjob--area, .location, .job-location, .place")
                if loc_el:
                    location = self._normalize_whitespace(loc_el.get_text(" ") or "")
                if location:
                    info["location"] = location

                logger.info(
                    f"⚡ HTTP scraped {job_id} | title='{info.get('title')}', company='{info.get('company')}', desc_len={len(info.get('description') or '')}"
                )
                return info
            except Exception as e:
                last_err = e
                await asyncio.sleep(0.3 * (attempt + 1))
        logger.warning(f"HTTP scrape failed for {job_id}: {last_err}")
        return None

    async def scrape_job_info(self, job_id: str, page=None) -> Optional[Dict]:
        job_url = f"{self.base_url}/vis-job/{job_id}"
        created_temp_page = False

        if page is None:
            await self.setup_browser()
            page = await self._context.new_page()
            created_temp_page = True

        # default timeouts
        page.set_default_timeout(45000)
        page.set_default_navigation_timeout(45000)

        try:
            logger.info(f"🔎 Scraping job info: {job_url}")

            # Robust navigation (retries + settle)
            for attempt in range(3):
                try:
                    await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                    await self._try_dismiss_cookies(page)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(1 + attempt)

            info: Dict[str, Optional[str]] = {}

            # ------- Title -------
            title = None
            try:
                t_el = await page.query_selector("h1.sr-only, h4 a, h1")
                if t_el:
                    t = await t_el.inner_text()
                    title = self._normalize_whitespace(t)
                    if title and title.startswith("Jobannonce: "):
                        title = title[len("Jobannonce: "):].strip()
            except Exception:
                pass

            if not title:
                try:
                    pt = await page.title()
                    if pt and " | Job" in pt:
                        title = self._normalize_whitespace(pt.split(" | Job")[0])
                except Exception:
                    pass

            info["title"] = title

            # ------- Company + URL -------
            company_name = None
            company_url = None

            try:
                comp_el = await page.query_selector(".jix-toolbar-top__company")
                if comp_el:
                    raw = await comp_el.inner_text()
                    raw = self._normalize_whitespace(raw) or ""
                    if raw.endswith(" søger for kunde"):
                        raw = raw.replace(" søger for kunde", "").strip()
                    company_name = raw or None

                    link = await comp_el.query_selector("a")
                    if link:
                        href = await link.get_attribute("href")
                        company_url = self._abs_url(href)
            except Exception:
                pass

            # Fallback: derive from title if it's a frivilligjob.dk style
            if not company_name:
                try:
                    job_link_element = await page.query_selector("h4 a")
                    if job_link_element:
                        href = await job_link_element.get_attribute("href")
                        if href and "frivilligjob.dk" in href and title and " - " in title:
                            company_name = title.split(" - ")[-1].strip()
                except Exception:
                    pass

            # Fallback: heuristic in body text (A/S, ApS)
            if not company_name:
                try:
                    body = await page.inner_text("body")
                    for pat in [
                        r"([A-ZÆØÅ][A-Za-zÆØÅæøå0-9&\.\-\s]+?)\s+A/S",
                        r"([A-ZÆØÅ][A-Za-zÆØÅæøå0-9&\.\-\s]+?)\s+ApS",
                    ]:
                        m = re.search(pat, body, re.IGNORECASE)
                        if m:
                            company_name = self._normalize_whitespace(m.group(1))
                            break
                except Exception:
                    pass

            info["company"] = company_name
            info["company_url"] = company_url

            # ------- Description -------
            description = None

            # Primary containers (structured)
            try:
                el = await page.query_selector(".jix_robotjob-inner p")
                if el:
                    txt = self._normalize_whitespace(await el.inner_text() or "")
                    if txt and len(txt) > 40:
                        description = txt
            except Exception:
                pass

            if not description:
                try:
                    job_content = await page.query_selector(".PaidJob-inner, .jix_robotjob-inner")
                    if job_content:
                        p_elements = await job_content.query_selector_all("p")
                        parts = []
                        for p in p_elements:
                            t = self._normalize_whitespace(await p.inner_text() or "")
                            if t and len(t) > 40:
                                parts.append(t)
                        if parts:
                            description = " ".join(parts)
                except Exception:
                    pass

            # Heuristic fallback from body text
            if not description:
                try:
                    body = await page.inner_text("body")
                    body = self._normalize_whitespace(body) or ""
                    patterns = [
                        r"(?:Vi søger|We are looking for|We seek).*?(?=\n\n|\n[A-ZÆØÅ]|$)",
                        r"(?:Jobbet|The position|The role).*?(?=\n\n|\n[A-ZÆØÅ]|$)",
                        r"(?:Ansvar|Responsibilities|Duties).*?(?=\n\n|\n[A-ZÆØÅ]|$)",
                    ]
                    for pat in patterns:
                        matches = re.findall(pat, body, re.DOTALL | re.IGNORECASE)
                        if matches:
                            cand = self._normalize_whitespace(matches[0])
                            if cand and len(cand) > 40:
                                description = cand
                                break
                except Exception:
                    pass

            # Clean out obvious chrome
            if description:
                for pat in [
                    r"Indrykket:.*?(?=\n|$)",
                    r"Hentet fra.*?(?=\n|$)",
                    r"Se jobbet.*?(?=\n|$)",
                    r"Anbefalede job.*?(?=\n|$)",
                    r"Gem.*?(?=\n|$)",
                    r"Del.*?(?=\n|$)",
                    r"Kopier.*?(?=\n|$)",
                    r"For jobsøgere.*?(?=\n|$)",
                    r"For arbejdsgivere.*?(?=\n|$)",
                    r"Jobsøgning.*?(?=\n|$)",
                    r"Arbejdspladser.*?(?=\n|$)",
                    r"Test dig selv.*?(?=\n|$)",
                    r"Guides.*?(?=\n|$)",
                    r"Kurser.*?(?=\n|$)",
                    r"Log ind.*?(?=\n|$)",
                    r"Opret profil.*?(?=\n|$)",
                ]:
                    description = re.sub(pat, "", description, flags=re.IGNORECASE)
                description = self._normalize_whitespace(description)
                if description and len(description) < 20:
                    description = None

            info["description"] = description

            # ------- Location -------
            location = None
            try:
                loc_el = await page.query_selector(".jix_robotjob--area, .location, .job-location, .place")
                if loc_el:
                    location = self._normalize_whitespace(await loc_el.inner_text() or "")
            except Exception:
                pass
            if location:
                info["location"] = location

            # Done
            logger.info(
                f"✅ Scraped {job_id} | "
                f"title='{info.get('title')}', company='{info.get('company')}', "
                f"company_url='{info.get('company_url')}', "
                f"desc_len={len(info.get('description') or '')}, "
                f"location='{info.get('location')}'"
            )
            return info

        except Exception as e:
            logger.error(f"❌ Error scraping job {job_id}: {e}")
            return None
        finally:
            if created_temp_page and page:
                try:
                    await page.close()
                except Exception:
                    pass

    # ---------- DB update (fill only missing) ----------
    def update_job_info(self, job_id: str, job_info: Dict) -> bool:
        try:
            # sanitize
            sanitized: Dict[str, str] = {}
            for k, v in job_info.items():
                if v is None:
                    continue
                if isinstance(v, str):
                    v2 = v.strip()
                    if not v2:
                        continue
                    sanitized[k] = v2
                else:
                    sanitized[k] = v

            if not sanitized:
                logger.warning(f"No valid scraped data for job {job_id}")
                return False

            # fetch current
            def build_query_current():
                return (
                    self.supabase
                    .table("jobs")
                    .select("title,company,location,description,company_url")
                    .eq("job_id", job_id)
                    .limit(1)
                )

            current_resp = self._sb_retry(build_query_current)
            current = (current_resp.data or [{}])[0]

            def is_empty(val) -> bool:
                return val is None or (isinstance(val, str) and val.strip() == "")

            update_data: Dict[str, str] = {}
            for key in ["title", "company", "location", "description", "company_url"]:
                if key in sanitized and is_empty(current.get(key)):
                    update_data[key] = sanitized[key]

            if not update_data:
                logger.info(f"ℹ️ No missing fields to update for job {job_id}")
                return True

            def build_update():
                return (
                    self.supabase
                    .table("jobs")
                    .update(update_data)
                    .eq("job_id", job_id)
                )

            response = self._sb_retry(build_update)
            if response.data:
                logger.info(f"🔧 Updated job {job_id} fields: {list(update_data.keys())}")
                return True

            logger.error(f"Failed to update job {job_id}")
            return False

        except Exception as e:
            logger.error(f"❌ Error updating job {job_id}: {e}")
            return False

    # ---------- Orchestrator ----------
    async def process_jobs_with_missing_info(
        self,
        max_jobs: Optional[int] = None,
        delay: float = 1.0,
        concurrency: int = 3,
        batch_flush: int = 200,
    ):
        """
        Process all jobs with missing info using keyset pagination.
        Limits concurrency and throttles between tasks.
        """
        # Note: defer browser setup until needed (fallback), but create HTTP client now
        await self.setup_http_client()
        semaphore = asyncio.Semaphore(max(1, int(concurrency)))

        total_seen = 0
        total_processed = 0
        total_updated = 0
        total_errors = 0

        async def process_single(job_idx: int, job: Dict):
            nonlocal total_processed, total_updated, total_errors
            job_id = job.get("job_id")
            if not job_id:
                logger.warning("Job without job_id encountered. Skipping.")
                return

            async with semaphore:
                logger.info(f"➡️  Processing #{job_idx}: {job_id}")
                try:
                    # 1) Fast path: HTTP fetch + parse
                    info = await self.scrape_job_info_http(job_id)
                    updated = False
                    if info:
                        updated = self.update_job_info(job_id, info)
                    # 2) Fallback to Playwright if HTTP failed to update
                    if not updated:
                        await self.setup_browser()
                        page = await self._context.new_page()
                        page.set_default_timeout(45000)
                        page.set_default_navigation_timeout(45000)
                        try:
                            info_pw = await self.scrape_job_info(job_id, page=page)
                            if info_pw and self.update_job_info(job_id, info_pw):
                                total_updated += 1
                            else:
                                total_errors += 1
                        finally:
                            try:
                                await page.close()
                            except Exception:
                                pass
                    else:
                        total_updated += 1
                except Exception as e:
                    total_errors += 1
                    logger.error(f"❌ Error processing job {job_id}: {e}")
                finally:
                    total_processed += 1
                    if delay and delay > 0:
                        await asyncio.sleep(delay)

        job_idx = 0
        batch: List[asyncio.Task] = []

        try:
            for job in self.iter_missing_info_jobs(batch_size=1000):
                total_seen += 1
                job_idx += 1
                if max_jobs is not None and total_seen > max_jobs:
                    break

                task = asyncio.create_task(process_single(job_idx, job))
                batch.append(task)

                if len(batch) >= batch_flush:
                    await asyncio.gather(*batch)
                    batch = []

            if batch:
                await asyncio.gather(*batch)

        except KeyboardInterrupt:
            logger.warning("Interrupted by user.")
        finally:
            await self.teardown_http_client()
            await self.teardown_browser()

        logger.info("=== PROCESSING COMPLETE ===")
        logger.info(f"Total matching (seen): {total_seen}")
        logger.info(f"Total processed     : {total_processed}")
        logger.info(f"Successfully updated: {total_updated}")
        logger.info(f"Errors              : {total_errors}")

    # ---------- Stats (server-side counts to avoid 1000-row cap) ----------
    def get_missing_info_stats(self) -> Dict:
        try:
            # Total aktive
            total_resp = (
                self.supabase
                .table("jobs")
                .select("id", count="exact")
                .is_("deleted_at", "null")
                .execute()
            )
            total_jobs = total_resp.count or 0

            # Antal hvor mindst ét felt mangler
            miss_resp = (
                self.supabase
                .table("jobs")
                .select("id", count="exact")
                .is_("deleted_at", "null")
                .or_(EMPTY_STR_FILTER)
                .execute()
            )
            missing_info = miss_resp.count or 0

            # Nedbrydning pr. felt – hver for sig med count
            def _count(filter_str: str) -> int:
                r = (
                    self.supabase
                    .table("jobs")
                    .select("id", count="exact")
                    .is_("deleted_at", "null")
                    .or_(filter_str)
                    .execute()
                )
                return r.count or 0

            missing_fields = {
                "company": _count("company.is.null,company.eq."),
                "company_url": _count("company_url.is.null,company_url.eq."),
                "description": _count("description.is.null,description.eq."),
            }

            pct = (missing_info / total_jobs * 100) if total_jobs else 0.0
            return {
                "total_jobs": total_jobs,
                "missing_info": missing_info,
                "missing_fields": missing_fields,
                "missing_percentage": pct,
            }
        except Exception as e:
            logger.error(f"Error getting missing info stats: {e}")
            return {
                "total_jobs": 0,
                "missing_info": 0,
                "missing_fields": {},
                "missing_percentage": 0.0,
            }


# --------- MAIN ---------
async def main():
    try:
        scraper = JobInfoScraper()

        stats = scraper.get_missing_info_stats()
        logger.info("=== INITIAL STATISTICS ===")
        logger.info(f"Total active jobs     : {stats['total_jobs']}")
        logger.info(f"Jobs with missing info: {stats['missing_info']} ({stats['missing_percentage']:.1f}%)")
        logger.info("Missing fields breakdown:")
        for field, count in stats["missing_fields"].items():
            pct = (count / stats["total_jobs"] * 100) if stats["total_jobs"] else 0
            logger.info(f"  {field}: {count} jobs ({pct:.1f}%)")

        await scraper.process_jobs_with_missing_info(
            max_jobs=None,   # sæt et tal for test (fx 50)
            delay=float(os.getenv("SCRAPER_DELAY", "0.2")),
            concurrency=int(os.getenv("SCRAPER_CONCURRENCY", "10")),
            batch_flush=int(os.getenv("SCRAPER_BATCH_FLUSH", "500")),
        )

        final = scraper.get_missing_info_stats()
        logger.info("=== FINAL STATISTICS ===")
        logger.info(f"Total active jobs     : {final['total_jobs']}")
        logger.info(f"Jobs with missing info: {final['missing_info']} ({final['missing_percentage']:.1f}%)")
        logger.info("Missing fields breakdown:")
        for field, count in final["missing_fields"].items():
            pct = (count / final["total_jobs"] * 100) if final["total_jobs"] else 0
            logger.info(f"  {field}: {count} jobs ({pct:.1f}%)")

    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())