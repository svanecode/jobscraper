#!/usr/bin/env python3
"""
Job Information Scraper
Scrapes missing company information from individual job URLs
"""

import asyncio
import logging
import os
import re
from typing import List, Dict, Optional
from playwright.async_api import async_playwright
from supabase import create_client, Client

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, continue without it

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# PostgREST OR filter for null or empty-string fields (empty string is represented as eq.)
EMPTY_STR_FILTER = 'company.is.null,company.eq.,company_url.is.null,company_url.eq.,description.is.null,description.eq.'


class JobInfoScraper:
    def __init__(self, supabase_url=None, supabase_key=None):
        self.base_url = "https://www.jobindex.dk"
        # Playwright resources
        self._playwright = None
        self._browser = None
        self._context = None

        # Initialize Supabase client
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY')

        if self.supabase_url and self.supabase_key:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            if os.getenv('SUPABASE_SERVICE_ROLE_KEY'):
                logger.info("Supabase client initialized with SERVICE_ROLE_KEY (RLS bypass)")
            else:
                logger.info("Supabase client initialized with ANON_KEY")
        else:
            logger.error("Supabase credentials not provided. Cannot proceed.")
            raise ValueError("Supabase credentials required")

    async def setup_browser(self):
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        self._context = await self._browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            viewport={'width': 1920, 'height': 1080}
        )

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

    # ---------- Keyset pagination over all matching jobs ----------
    def iter_missing_info_jobs(self, batch_size: int = 1000):
        """
        Yield all active jobs with missing info (null/empty company, company_url, or description),
        ordered by created_at DESC, using keyset pagination to avoid OFFSET costs and the 1000-row cap.
        
        Note: We intentionally do not require `job_info` to be NULL so that we can re-fill fields
        that might have been cleared or were missing when first processed.
        """
        last_created_at = None

        while True:
            q = (
                self.supabase
                .table('jobs')
                .select('*')
                .is_('deleted_at', 'null')
                .or_(EMPTY_STR_FILTER)
                .order('created_at', desc=True)
                .limit(batch_size)
            )
            if last_created_at:
                # get strictly older rows than the last one we saw
                q = q.lt('created_at', last_created_at)

            resp = q.execute()
            rows = resp.data or []
            if not rows:
                break

            for r in rows:
                yield r

            last_created_at = rows[-1]['created_at']

    async def scrape_job_info(self, job_id: str, page=None) -> Optional[Dict]:
        """
        Scrape detailed job information from a specific job URL
        """
        job_url = f"https://www.jobindex.dk/vis-job/{job_id}"
        created_temp_page = False

        if page is None:
            await self.setup_browser()
            page = await self._context.new_page()
            created_temp_page = True

        try:
            logger.info(f"Scraping job info from: {job_url}")
            # Robust navigation with simple retries
            last_error = None
            for attempt in range(3):
                try:
                    await page.goto(job_url, wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_load_state('domcontentloaded', timeout=10000)
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    if attempt < 2:
                        await asyncio.sleep(1 + attempt)
                    else:
                        raise

            job_info: Dict[str, Optional[str]] = {}

            # --- Title ---
            title = None
            try:
                title_element = await page.query_selector('h4 a')
                if title_element:
                    t = (await title_element.inner_text()) or ''
                    t = t.strip()
                    if t:
                        title = t
                        logger.debug(f"Found title in h4: '{title}'")
            except Exception as e:
                logger.debug(f"Error getting title from h4: {e}")

            if not title:
                try:
                    title_element = await page.query_selector('h1.sr-only')
                    if title_element:
                        t = (await title_element.inner_text()) or ''
                        t = t.strip()
                        if t.startswith('Jobannonce: '):
                            t = t[len('Jobannonce: '):].strip()
                        if t:
                            title = t
                            logger.debug(f"Found title in sr-only h1: '{title}'")
                except Exception as e:
                    logger.debug(f"Error getting title from sr-only h1: {e}")

            if not title:
                try:
                    page_title = await page.title()
                    if page_title and '| Job' in page_title:
                        # "Title - JobID | Job"
                        title = page_title.split(' - ')[0].strip()
                        logger.debug(f"Found title from page title: '{title}'")
                except Exception as e:
                    logger.debug(f"Error getting title from page title: {e}")

            job_info['title'] = title

            # --- Company + URL ---
            company_name = None
            company_url = None

            try:
                company_element = await page.query_selector('.jix-toolbar-top__company')
                if company_element:
                    company_text = (await company_element.inner_text()) or ''
                    company_text = company_text.strip()
                    if company_text:
                        if ' søger for kunde' in company_text:
                            company_name = company_text.replace(' søger for kunde', '').strip()
                        else:
                            company_name = company_text
                        company_link = await company_element.query_selector('a')
                        if company_link:
                            company_url = await company_link.get_attribute('href')
                            if company_url:
                                company_url = company_url.strip()
                                if company_url.startswith('/'):
                                    company_url = f"{self.base_url}{company_url}"
                        logger.debug(f"Company: '{company_name}', URL: '{company_url}'")
            except Exception as e:
                logger.debug(f"Error getting company from toolbar: {e}")

            if not company_name:
                try:
                    job_link_element = await page.query_selector('h4 a')
                    if job_link_element:
                        href = await job_link_element.get_attribute('href')
                        if href and 'frivilligjob.dk' in href and title and ' - ' in title:
                            company_name = title.split(' - ')[-1].strip()
                except Exception as e:
                    logger.debug(f"Error extracting company from job link: {e}")

            if not company_name:
                try:
                    page_text = await page.inner_text('body')
                    company_patterns = [
                        r'([A-ZÆØÅ][A-Za-zÆØÅæøå0-9&\.\-\s]+?)\s+A/S',
                        r'([A-ZÆØÅ][A-Za-zÆØÅæøå0-9&\.\-\s]+?)\s+ApS',
                    ]
                    for pattern in company_patterns:
                        m = re.search(pattern, page_text, re.IGNORECASE)
                        if m:
                            company_name = m.group(1).strip()
                            break
                except Exception as e:
                    logger.debug(f"Error finding company in text: {e}")

            job_info['company'] = company_name
            job_info['company_url'] = company_url

            # --- Description ---
            description = None

            try:
                desc_element = await page.query_selector('.jix_robotjob-inner p')
                if desc_element:
                    description = (await desc_element.inner_text() or '').strip()
                    if description:
                        logger.debug("Found description in .jix_robotjob-inner p")
            except Exception as e:
                logger.debug(f"Error getting description from .jix_robotjob-inner p: {e}")

            if not description:
                try:
                    job_content = await page.query_selector('.PaidJob-inner')
                    if job_content:
                        p_elements = await job_content.query_selector_all('p')
                        parts = []
                        for p in p_elements:
                            t = (await p.inner_text() or '').strip()
                            if t and len(t) > 10:
                                parts.append(t)
                        if parts:
                            description = ' '.join(parts)
                            logger.debug("Found description in .PaidJob-inner")
                except Exception as e:
                    logger.debug(f"Error getting description from .PaidJob-inner: {e}")

            if not description:
                try:
                    job_content = await page.query_selector('.jix_robotjob-inner')
                    if job_content:
                        content_text = await job_content.inner_text()
                        for line in (l.strip() for l in content_text.split('\n')):
                            if len(line) > 20 and not any(s in line.lower() for s in [
                                'indrykket:', 'hentet fra', 'se jobbet', 'se rejsetid'
                            ]):
                                if line not in {title, company_name}:
                                    description = line
                                    break
                except Exception as e:
                    logger.debug(f"Error scanning job content text: {e}")

            if not description:
                try:
                    page_text = await page.inner_text('body')
                    desc_patterns = [
                        r'(?:Vi søger|We are looking for|We seek).*?(?=\n\n|\n[A-ZÆØÅ]|$)',
                        r'(?:Jobbet|The position|The role).*?(?=\n\n|\n[A-ZÆØÅ]|$)',
                        r'(?:Ansvar|Responsibilities|Duties).*?(?=\n\n|\n[A-ZÆØÅ]|$)',
                    ]
                    for pattern in desc_patterns:
                        matches = re.findall(pattern, page_text, re.DOTALL | re.IGNORECASE)
                        if matches:
                            potential = matches[0].strip()
                            if len(potential) > 20:
                                description = re.sub(r'\s+', ' ', potential)
                                break
                except Exception as e:
                    logger.debug(f"Error finding description via patterns: {e}")

            if description:
                unwanted_patterns = [
                    r'Indrykket:.*?(?=\n|$)',
                    r'Hentet fra.*?(?=\n|$)',
                    r'Se jobbet.*?(?=\n|$)',
                    r'Anbefalede job.*?(?=\n|$)',
                    r'Gem.*?(?=\n|$)',
                    r'Del.*?(?=\n|$)',
                    r'Kopier.*?(?=\n|$)',
                    r'30\.400 job i dag.*?(?=\n|$)',
                    r'For jobsøgere.*?(?=\n|$)',
                    r'For arbejdsgivere.*?(?=\n|$)',
                    r'Jobsøgning.*?(?=\n|$)',
                    r'Arbejdspladser.*?(?=\n|$)',
                    r'Test dig selv.*?(?=\n|$)',
                    r'Guides.*?(?=\n|$)',
                    r'Kurser.*?(?=\n|$)',
                    r'Log ind.*?(?=\n|$)',
                    r'Opret profil.*?(?=\n|$)',
                ]
                for pat in unwanted_patterns:
                    description = re.sub(pat, '', description, flags=re.IGNORECASE)
                description = re.sub(r'\s+', ' ', description).strip()
                if len(description) < 10:
                    description = None

            job_info['description'] = description

            # --- Location ---
            location = None
            try:
                location_element = await page.query_selector('.jix_robotjob--area')
                if location_element:
                    location = (await location_element.inner_text() or '').strip()
            except Exception as e:
                logger.debug(f"Error getting location: {e}")
            if location:
                job_info['location'] = location

            logger.info(f"Successfully scraped info for job {job_id}")
            logger.info(f"Title: '{job_info.get('title')}'")
            logger.info(f"Company: '{job_info.get('company')}'")
            desc_preview = (job_info.get('description') or '')[:100]
            logger.info(f"Description: '{desc_preview}...'")
            logger.info(f"Location: '{job_info.get('location')}'")

            return job_info

        except Exception as e:
            logger.error(f"Error scraping job {job_id}: {e}")
            return None
        finally:
            if created_temp_page and page:
                try:
                    await page.close()
                except Exception:
                    pass

    def update_job_info(self, job_id: str, job_info: Dict) -> bool:
        """
        Update only fields that are missing (NULL/empty) in DB with scraped non-empty values.
        Avoid overwriting existing non-empty values.
        """
        try:
            # Sanitize scraped values
            sanitized: Dict[str, str] = {}
            for key, value in job_info.items():
                if value is None:
                    continue
                if isinstance(value, str):
                    v = value.strip()
                    if not v:
                        continue
                    sanitized[key] = v
                else:
                    sanitized[key] = value

            if not sanitized:
                logger.warning(f"No valid scraped data for job {job_id}")
                return False

            # Fetch current DB values to only fill missing fields
            current_resp = (
                self.supabase
                .table('jobs')
                .select('title,company,location,description,company_url')
                .eq('job_id', job_id)
                .limit(1)
                .execute()
            )
            current = (current_resp.data or [{}])[0]

            def is_empty(val) -> bool:
                if val is None:
                    return True
                if isinstance(val, str) and val.strip() == '':
                    return True
                return False

            update_data: Dict[str, str] = {}
            for key in ['title', 'company', 'location', 'description', 'company_url']:
                scraped_val = sanitized.get(key)
                if scraped_val is None:
                    continue
                if is_empty(current.get(key)):
                    update_data[key] = scraped_val

            if not update_data:
                logger.info(f"No missing fields to update for job {job_id}")
                return True

            response = (
                self.supabase
                .table('jobs')
                .update(update_data)
                .eq('job_id', job_id)
                .execute()
            )

            if response.data:
                logger.info(f"Updated job {job_id} with: {list(update_data.keys())}")
                return True
            else:
                logger.error(f"Failed to update job {job_id}")
                return False

        except Exception as e:
            logger.error(f"Error updating job {job_id}: {e}")
            return False

    async def process_jobs_with_missing_info(self, max_jobs: Optional[int] = None, delay: float = 1.0, concurrency: int = 3):
        """
        Stream-process ALL jobs with missing info (newest first) using keyset pagination.
        Limits concurrency and throttles between tasks.
        """
        await self.setup_browser()
        semaphore = asyncio.Semaphore(max(1, int(concurrency)))

        total_seen = 0
        total_processed = 0
        total_updated = 0
        total_errors = 0

        async def process_single(job_idx: int, job: Dict):
            nonlocal total_processed, total_updated, total_errors
            job_id = job.get('job_id')
            if not job_id:
                logger.warning("Job without job_id found, skipping")
                return

            # No longer using a job_info marker column to skip; always attempt to backfill missing fields

            async with semaphore:
                logger.info(f"Processing #{job_idx}: {job_id}")
                page = await self._context.new_page()
                try:
                    job_info = await self.scrape_job_info(job_id, page=page)
                    if job_info and self.update_job_info(job_id, job_info):
                        total_updated += 1
                    else:
                        total_errors += 1
                except Exception as e:
                    total_errors += 1
                    logger.error(f"Error processing job {job_id}: {e}")
                finally:
                    total_processed += 1
                    try:
                        await page.close()
                    except Exception:
                        pass
                    if delay and delay > 0:
                        await asyncio.sleep(delay)

        # Process in batches to avoid holding everything in memory
        job_idx = 0
        try:
            batch: List[asyncio.Task] = []
            for job in self.iter_missing_info_jobs(batch_size=1000):
                total_seen += 1
                job_idx += 1

                # Respect max_jobs if provided
                if max_jobs is not None and total_seen > max_jobs:
                    break

                task = asyncio.create_task(process_single(job_idx, job))
                batch.append(task)

                # Optional: keep batches reasonably bounded to give cancellation points
                if len(batch) >= 200:
                    await asyncio.gather(*batch)
                    batch = []

            if batch:
                await asyncio.gather(*batch)

        except KeyboardInterrupt:
            logger.warning("Interrupted by user.")
        finally:
            await self.teardown_browser()

        logger.info("=== PROCESSING COMPLETE ===")
        logger.info(f"Total seen (matching filter): {total_seen}")
        logger.info(f"Total processed: {total_processed}")
        logger.info(f"Successfully updated: {total_updated}")
        logger.info(f"Errors: {total_errors}")

    def get_missing_info_stats(self) -> Dict:
        """
        Get statistics about jobs with missing information
        """
        try:
            all_jobs_response = (
                self.supabase
                .table('jobs')
                .select('company,company_url,description')
                .is_('deleted_at', 'null')
                .execute()
            )
            data = all_jobs_response.data or []
            total_jobs = len(data)
            missing_info_count = 0
            missing_fields = {'company': 0, 'company_url': 0, 'description': 0}

            for job in data:
                has_missing = False
                if not (job.get('company') or '').strip():
                    missing_fields['company'] += 1
                    has_missing = True
                if not (job.get('company_url') or '').strip():
                    missing_fields['company_url'] += 1
                    has_missing = True
                if not (job.get('description') or '').strip():
                    missing_fields['description'] += 1
                    has_missing = True
                if has_missing:
                    missing_info_count += 1

            return {
                "total_jobs": total_jobs,
                "missing_info": missing_info_count,
                "missing_fields": missing_fields,
                "missing_percentage": (missing_info_count / total_jobs * 100) if total_jobs > 0 else 0
            }
        except Exception as e:
            logger.error(f"Error getting missing info stats: {e}")
            return {
                "total_jobs": 0,
                "missing_info": 0,
                "missing_fields": {},
                "missing_percentage": 0,
                "processed_by_job_info": 0,
                "processed_percentage": 0
            }


async def main():
    """Main function to run the job info scraper"""
    try:
        scraper = JobInfoScraper()

        stats = scraper.get_missing_info_stats()
        logger.info("=== INITIAL STATISTICS ===")
        logger.info(f"Total active jobs: {stats['total_jobs']}")
        logger.info(f"Jobs with missing info: {stats['missing_info']} ({stats['missing_percentage']:.1f}%)")
        logger.info("Missing fields breakdown:")
        for field, count in stats['missing_fields'].items():
            pct = (count / stats['total_jobs'] * 100) if stats['total_jobs'] > 0 else 0
            logger.info(f"  {field}: {count} jobs ({pct:.1f}%)")

        await scraper.process_jobs_with_missing_info(
            max_jobs=None,     # or set a number for testing
            delay=2.0,         # throttle between tasks
            concurrency=3      # parallel tabs
        )

        final_stats = scraper.get_missing_info_stats()
        logger.info("=== FINAL STATISTICS ===")
        logger.info(f"Total active jobs: {final_stats['total_jobs']}")
        logger.info(f"Jobs with missing info: {final_stats['missing_info']} ({final_stats['missing_percentage']:.1f}%)")
        logger.info("Missing fields breakdown:")
        for field, count in final_stats['missing_fields'].items():
            pct = (count / final_stats['total_jobs'] * 100) if final_stats['total_jobs'] > 0 else 0
            logger.info(f"  {field}: {count} jobs ({pct:.1f}%)")

    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())