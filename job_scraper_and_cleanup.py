#!/usr/bin/env python3
"""
Combined Job Scraper and Cleanup (Jobindex → Supabase)

What it does
------------
1) Scrapes Jobindex search results (category: "kontor") across all pages.
2) Saves new jobs and updates last_seen for existing jobs (via RLS client).
3) Cleans up old jobs not seen recently.
4) Prints end-of-run stats.

Key features
------------
- Bullet-proof pagination: only uses search pagination (scoped to container) and
  safe fallback by incrementing ?page=, plus post-nav validation that we stayed
  on /jobsoegning/... and there are job cards.
- Blocks heavy assets (images/fonts/media) but keeps CSS for layout.
- Dedup by job_id (Jobindex sometimes repeats “fremhævet” ads).
- Idle & page count guards to avoid infinite loops.
- Danish date parsing (i dag, i går, “for X dage siden”, “10. aug”, etc.).
- Per-page batch Saves to Supabase via your SupabaseRLSClient (RLS aware).
"""

import asyncio
import logging
import os
import random
import re
import sys
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, urljoin

from playwright.async_api import async_playwright
from supabase_rls_config import SupabaseRLSClient

# ---------------------- ENV ----------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ------------------- LOGGING ---------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

SEARCH_PATH_PREFIX = "/jobsoegning/"

class JobScraperAndCleanup:
    def __init__(self, supabase_url=None, supabase_key=None, cleanup_hours=24):
        self.base_url = "https://www.jobindex.dk"
        self.search_url = "https://www.jobindex.dk/jobsoegning/kontor"
        self.cleanup_hours = cleanup_hours

        # Stats counters
        self.scraped_this_run = 0

        # Supabase RLS client
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not self.supabase_url or not self.supabase_key:
            logger.error("❌ Supabase credentials not provided")
            raise ValueError("Supabase credentials required")

        self.supabase = SupabaseRLSClient(
            supabase_url=self.supabase_url,
            supabase_key=self.supabase_key,
            use_service_role=True,
        )
        logger.info("✅ Supabase RLS client initialized")

    # ----------------- SCRAPE -----------------
    async def scrape_jobs(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(
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
            context = await browser.new_context(
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
                if req.resource_type in {"image", "font", "media"}:
                    return await route.abort()
                return await route.continue_()
            await context.route("**/*", route_interceptor)

            page = await context.new_page()
            page.set_default_timeout(45000)
            page.set_default_navigation_timeout(45000)

            try:
                logger.info(f"🔍 Starting job scraping from: {self.search_url}")

                # Robust initial nav
                nav_ok = False
                for attempt in range(4):
                    try:
                        wait_until = ["domcontentloaded", "load", None, "networkidle"][attempt]
                        if wait_until:
                            await page.goto(self.search_url, wait_until=wait_until, timeout=60000)
                        else:
                            await page.goto(self.search_url, timeout=60000)
                            await asyncio.sleep(5)
                        nav_ok = True
                        logger.info("Navigation successful (%s)", wait_until or "basic")
                        break
                    except Exception as e:
                        logger.warning("Initial nav attempt %d failed: %s", attempt + 1, e)
                if not nav_ok:
                    logger.error("All initial navigation strategies failed")
                    return False

                # Guard: ensure it's a search URL
                if not urlparse(page.url).path.startswith(SEARCH_PATH_PREFIX):
                    logger.error(f"Unexpected start path for search: {page.url}")
                    return False

                total_jobs = 0
                page_num = 1
                seen_urls = {page.url}
                seen_job_ids = set()
                empty_pages_in_a_row = 0
                idle_pages = 0   # pages with < 3 unique jobs
                MAX_PAGES = 1000

                async def wait_for_any_selector(selectors, timeout_ms=10000):
                    for selector in selectors:
                        try:
                            await page.wait_for_selector(selector, timeout=timeout_ms, state="attached")
                            return True
                        except Exception:
                            continue
                    return False

                async def try_dismiss_cookies():
                    try:
                        for sel in [
                            'button:has-text("Accepter")',
                            'button:has-text("Acceptér")',
                            'button:has-text("OK")',
                            'text="Accepter alle"',
                        ]:
                            el = await page.query_selector(sel)
                            if el:
                                await el.click()
                                await asyncio.sleep(0.3 + random.random() * 0.4)
                                break
                    except Exception:
                        pass

                def _next_search_url(current_url: str) -> str:
                    """Increment ?page= for the current search URL. Defaults to page=2 if missing."""
                    parsed = urlparse(current_url)
                    qs = parse_qs(parsed.query)
                    current_page = int(qs.get("page", ["1"])[0] or "1")
                    qs["page"] = [str(current_page + 1)]
                    new_query = urlencode({k: v[0] for k, v in qs.items()})
                    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", new_query, ""))

                async def goto_next_page():
                    """
                    Navigate to the next **search** page only:
                      1) Click next inside search pagination containers.
                      2) Fallback: increment ?page=.
                      3) Validate path and presence of job cards.
                    """
                    prev_url = page.url

                    # 1) Scoped containers only
                    pagination_containers = [
                        ".jix_pagination",                 # Jobindex classic
                        'nav[aria-label="Pagination"]',
                        ".pagination",                      # generic
                    ]
                    next_clicked = False
                    for cont_sel in pagination_containers:
                        cont = page.locator(cont_sel).first
                        if await cont.count() == 0:
                            continue
                        next_link = cont.locator('a[rel="next"], a:has-text("Næste")').first
                        if await next_link.count() > 0:
                            try:
                                await next_link.scroll_into_view_if_needed()
                                with page.expect_navigation(wait_until="domcontentloaded", timeout=45000):
                                    await next_link.click()
                                next_clicked = True
                                break
                            except Exception:
                                # fall through to URL fallback
                                pass

                    # 2) Fallback: increment ?page= deterministically
                    if not next_clicked:
                        parsed = urlparse(page.url)
                        if not parsed.path.startswith(SEARCH_PATH_PREFIX):
                            return False
                        target = _next_search_url(page.url)
                        try:
                            await page.goto(target, wait_until="domcontentloaded", timeout=60000)
                        except Exception:
                            return False

                    await try_dismiss_cookies()
                    try:
                        await page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass

                    # 3) Validate: path + job cards + not same URL
                    if not urlparse(page.url).path.startswith(SEARCH_PATH_PREFIX):
                        logger.info(f"Navigation veered off search: {page.url} (stopping)")
                        return False

                    job_selector = (
                        '[id^="jobad-wrapper-"], .job-listing, .job-item, '
                        '[data-testid="job-listing"], .job-card, .job-ad'
                    )
                    if await page.locator(job_selector).first.count() == 0:
                        logger.info(f"Next page has no job listings visible: {page.url} (stopping)")
                        return False

                    if page.url == prev_url or page.url in seen_urls:
                        return False

                    seen_urls.add(page.url)
                    return True

                while True:
                    logger.info(f"📄 Scraping page {page_num}: {page.url}")

                    ready = await wait_for_any_selector(
                        [
                            '[id^="jobad-wrapper-"]', '.job-listing', '.job-item',
                            '[data-testid="job-listing"]', '.job-card', '.job-ad',
                        ],
                        timeout_ms=15000,
                    )
                    if not ready:
                        logger.warning("No job container found (timeout). Trying one slow pass…")
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(1.0 + random.random() * 0.5)
                        ready = await wait_for_any_selector(
                            [
                                '[id^="jobad-wrapper-"]', '.job-listing', '.job-item',
                                '[data-testid="job-listing"]', '.job-card', '.job-ad',
                            ],
                            timeout_ms=8000,
                        )

                    await try_dismiss_cookies()

                    page_jobs = await self.extract_jobs_from_page(page)
                    orig_count = len(page_jobs)

                    # Dedup within this run by job_id
                    if page_jobs:
                        unique_jobs = []
                        for j in page_jobs:
                            if j["job_id"] not in seen_job_ids:
                                seen_job_ids.add(j["job_id"])
                                unique_jobs.append(j)
                        page_jobs = unique_jobs

                        if len(page_jobs) < orig_count:
                            logger.info(f"Deduplicated: {orig_count} → {len(page_jobs)} unique jobs on page {page_num}")

                    dedup_only = (orig_count > 0 and len(page_jobs) == 0)

                    if page_jobs:
                        empty_pages_in_a_row = 0
                        total_jobs += len(page_jobs)
                        self.scraped_this_run = total_jobs
                        logger.info(f"Found {len(page_jobs)} jobs on page {page_num}")

                        # Idle page tracking
                        if len(page_jobs) < 3:
                            idle_pages += 1
                        else:
                            idle_pages = 0

                        # Save immediately per page
                        try:
                            if self.supabase.insert_jobs(page_jobs):
                                logger.info(f"✅ Saved {len(page_jobs)} jobs from page {page_num}")
                            else:
                                logger.warning(f"⚠️ Supabase insert returned False on page {page_num}")
                        except Exception as e:
                            logger.error(f"❌ Supabase insert failed on page {page_num}: {e}")
                    else:
                        empty_pages_in_a_row += 1
                        if not dedup_only:
                            idle_pages += 1
                        else:
                            idle_pages = max(0, idle_pages - 1)
                        logger.warning(f"No jobs parsed on page {page_num} (empty streak: {empty_pages_in_a_row})")

                    # Guards
                    if page_num >= MAX_PAGES or idle_pages >= 10:
                        logger.info(f"Guard stop at page {page_num}, url={page.url}, last_jobs={len(page_jobs)}")
                        break

                    if empty_pages_in_a_row >= 2:
                        await asyncio.sleep(2 + random.random())

                    navigated = await goto_next_page()
                    if not navigated:
                        if empty_pages_in_a_row == 0:
                            logger.info(f"No next page detected. Finishing at page {page_num}, url={page.url}")
                            break
                        else:
                            logger.info(f"No next page or navigation blocked. Finishing after empty pages at page {page_num}, url={page.url}")
                            break

                    page_num += 1
                    logger.info(f"➡️  Navigated to page {page_num}: {page.url}")

                logger.info(f"🎉 Scraping completed! Total jobs found: {total_jobs} across {page_num} pages")
                logger.info(f"📊 Final stats: seen_urls={len(seen_urls)}")
                return True

            except Exception as e:
                logger.error(f"Error during scraping: {e}")
                return False
            finally:
                await context.close()
                await browser.close()

    # ----------------- EXTRACT -----------------
    async def extract_jobs_from_page(self, page):
        jobs = []
        try:
            # Candidate containers
            job_selectors = [
                '[id^="jobad-wrapper-"]',
                '.job-listing',
                '.job-item',
                '[data-testid="job-listing"]',
                '.job-card',
                '.job-ad',
            ]
            job_elements = []
            for selector in job_selectors:
                job_elements = await page.query_selector_all(selector)
                if job_elements:
                    break

            if not job_elements:
                return []

            for job_element in job_elements:
                try:
                    job_data = await self.parse_job_listing(job_element)
                    if job_data:
                        jobs.append(job_data)
                except Exception:
                    continue
            return jobs

        except Exception as e:
            logger.error(f"Error extracting jobs from page: {e}")
            return []

    async def parse_job_listing(self, job_wrapper):
        try:
            # job_id (wrapper id, data-*, or from href)
            job_id = None
            try:
                wrapper_id = await job_wrapper.get_attribute("id")
                if wrapper_id and "jobad-wrapper-" in wrapper_id:
                    job_id = wrapper_id.replace("jobad-wrapper-", "")

                if not job_id:
                    for attr in ("data-jobid", "data-id"):
                        job_id = await job_wrapper.get_attribute(attr)
                        if job_id:
                            break

                if not job_id:
                    link_element = await job_wrapper.query_selector(
                        'a[href*="/vis-job/"], a[href*="/job/"], a[href*="/jobannonce/"]'
                    )
                    if link_element:
                        href = await link_element.get_attribute("href")
                        if href:
                            toks = [t for t in href.split("/") if t and any(ch.isdigit() for ch in t)]
                            if toks:
                                job_id = toks[-1].split("?")[0]
            except Exception:
                pass

            if not job_id:
                return None

            # title
            title = None
            try:
                el = await job_wrapper.query_selector("h4 a, .job-title a, .title a")
                if el:
                    title = self._normalize_whitespace(await el.inner_text() or "")
            except Exception:
                pass

            # company
            company = None
            try:
                el = await job_wrapper.query_selector(".jix-toolbar-top__company, .company, .employer, .job-company")
                if el:
                    company = self._normalize_whitespace(await el.inner_text() or "")
            except Exception:
                pass

            # location
            location = None
            try:
                el = await job_wrapper.query_selector(".jix_robotjob--area, .location, .job-location, .place")
                if el:
                    location = self._normalize_whitespace(await el.inner_text() or "")
            except Exception:
                pass

            # publication date
            publication_date = None
            try:
                el = await job_wrapper.query_selector(".date, .job-date, .published")
                if el:
                    date_text = self._normalize_whitespace(await el.inner_text() or "")
                    if date_text:
                        publication_date = self._parse_danish_date(date_text)
            except Exception:
                pass

            # short description
            description = None
            try:
                el = await job_wrapper.query_selector(
                    ".jix_robotjob--description, .description, .job-description, .summary, .job-summary"
                )
                if el:
                    description = self._normalize_whitespace(await el.inner_text() or "")
            except Exception:
                pass

            return {
                "job_id": job_id,
                "title": title or "Unknown Title",
                "company": company,
                "location": location,
                "publication_date": publication_date or datetime.now().strftime("%Y-%m-%d"),
                "job_url": f"https://www.jobindex.dk/vis-job/{job_id}",
                "company_url": None,
                "description": description,
            }

        except Exception:
            return None

    # ----------------- HELPERS -----------------
    @staticmethod
    def _normalize_whitespace(text):
        if not text:
            return text
        return re.sub(r"\s+", " ", text.strip())

    @staticmethod
    def _parse_danish_date(date_text: str) -> str:
        """Parse 'i dag', 'i går', 'for 3 dage siden', '10. aug', '15. september' → YYYY-MM-DD."""
        if not date_text:
            return datetime.now().strftime("%Y-%m-%d")

        t = date_text.lower().strip()
        today = datetime.now()

        if t in {"i dag", "today"}:
            return today.strftime("%Y-%m-%d")
        if t in {"i går", "i gaar", "yesterday"}:
            return (today - timedelta(days=1)).strftime("%Y-%m-%d")

        if "dage siden" in t or "days ago" in t:
            m = re.search(r"(\d+)", t)
            if m:
                days_ago = int(m.group(1))
                return (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")

        danish_months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
            "januar": 1, "februar": 2, "marts": 3, "april": 4, "maj": 5, "juni": 6,
            "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
        }
        m = re.search(r"(\d+)\.\s*([A-Za-zæøåÆØÅ]+)", t)
        if m:
            day = int(m.group(1))
            month_name = m.group(2).lower()
            if month_name in danish_months:
                month = danish_months[month_name]
                year = today.year
                if month > today.month:
                    year -= 1
                try:
                    return f"{year:04d}-{month:02d}-{day:02d}"
                except Exception:
                    pass

        return today.strftime("%Y-%m-%d")

    # ----------------- CLEANUP & STATS -----------------
    def cleanup_old_jobs(self):
        try:
            deleted_count = self.supabase.cleanup_old_jobs(self.cleanup_hours)
            logger.info(f"🧹 RLS cleanup completed: {deleted_count} jobs cleaned up")
            return {"total_checked": deleted_count, "total_deleted": deleted_count, "errors": 0}
        except Exception as e:
            logger.error(f"Error during RLS cleanup: {e}")
            return {"total_checked": 0, "total_deleted": 0, "errors": 1}

    def get_stats(self):
        try:
            stats = self.supabase.get_job_statistics()
            stats.update({"cleanup_hours": self.cleanup_hours, "scraped_jobs": self.scraped_this_run})
            return stats
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {
                "total_jobs": 0,
                "active_jobs": 0,
                "deleted_jobs": 0,
                "jobs_scraped_today": 0,
                "cleanup_hours": self.cleanup_hours,
                "scraped_jobs": self.scraped_this_run,
            }

# ----------------- MAIN -----------------
async def main():
    try:
        logger.info("🚀 Starting Combined Job Scraper and Cleanup")
        logger.info("=" * 60)

        scraper_cleanup = JobScraperAndCleanup()

        logger.info("📥 STEP 1: Scraping jobs from job websites")
        scraping_success = await scraper_cleanup.scrape_jobs()

        if scraping_success and scraper_cleanup.scraped_this_run > 0:
            logger.info("🧹 STEP 2: Cleaning up old jobs")
            cleanup_stats = scraper_cleanup.cleanup_old_jobs()

            stats = scraper_cleanup.get_stats()
            logger.info("📊 COMPREHENSIVE STATISTICS:")
            logger.info(f"  Total jobs in database: {stats.get('total_jobs')}")
            logger.info(f"  Active jobs: {stats.get('active_jobs')}")
            logger.info(f"  Deleted jobs: {stats.get('deleted_jobs')}")
            logger.info(f"  Jobs scraped this run: {stats.get('scraped_jobs')}")
            logger.info(f"  Jobs scraped today: {stats.get('jobs_scraped_today')}")
            logger.info(f"  Cleanup threshold: {stats.get('cleanup_hours')} hours")
            logger.info(f"  Jobs deleted this run: {cleanup_stats.get('total_deleted')}")
            logger.info("\n🎉 Combined scraper and cleanup completed successfully!")
        else:
            logger.warning("⚠️ No jobs scraped, skipping cleanup steps")
            if not scraping_success:
                logger.error("❌ Failed to scrape jobs")

    except Exception as e:
        logger.error(f"❌ Error in main: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())