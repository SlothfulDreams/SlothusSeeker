"""GitHub client for fetching Jobright internship listings."""

import asyncio
import re
from datetime import datetime

import aiohttp

from src.config.settings import GITHUB_REPO_URL, GITHUB_TOKEN
from src.scraper.data_models import Internship, SEASONS, ScrapedData, build_job_id
from src.scraper.exceptions import FetchError, NetworkError, ParseError, RateLimitError
from src.utils.logger import setup_logger
from src.utils.retry import retry_with_backoff

logger = setup_logger(__name__)

README_MARKER = "Daily Job List"
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
TABLE_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")
WORK_MODE_RE = re.compile(r"\b(On Site|Hybrid|Remote)\b", re.IGNORECASE)
DATE_RE = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2}\b",
    re.IGNORECASE,
)


def _strip_markdown(value: str) -> str:
    value = value.replace("<br>", " ")
    value = re.sub(r"</?[^>]+>", " ", value)
    value = value.replace("**", "").replace("__", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _extract_link(cell: str) -> tuple[str, str]:
    match = MARKDOWN_LINK_RE.search(cell)
    if match:
        return _strip_markdown(match.group(1)), match.group(2).strip()
    return _strip_markdown(cell), ""


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    return all(TABLE_SEPARATOR_RE.match(cell.strip()) for cell in cells if cell)


def _parse_date_label(date_label: str) -> int:
    if not date_label:
        return 0

    normalized = date_label.replace("Sept", "Sep")
    for fmt in ("%b %d", "%B %d"):
        try:
            parsed = datetime.strptime(normalized, fmt)
            current_year = datetime.now().year
            return int(parsed.replace(year=current_year).timestamp())
        except ValueError:
            continue
    return 0


def _parse_location_work_date(rest: list[str]) -> tuple[list[str], str, str, int]:
    text = " ".join(_strip_markdown(cell) for cell in rest if cell).strip()
    if not text:
        return [], "", "", 0

    work_model = ""
    work_match = WORK_MODE_RE.search(text)
    if work_match:
        work_model = work_match.group(1).title()

    date_label = ""
    date_match = DATE_RE.search(text)
    if date_match:
        date_label = date_match.group(0)

    location_end = work_match.start() if work_match else len(text)
    location = text[:location_end].strip(" ,-")
    locations = [location] if location else []

    return locations, work_model, date_label, _parse_date_label(date_label)


def parse_jobright_readme(
    readme_text: str,
    start_timestamp: int | None = None,
) -> ScrapedData:
    """Parse Jobright README Markdown into season-bucketed internships."""
    scraped_data = ScrapedData()
    previous_company_name = ""
    previous_company_url = ""
    rows_processed = 0
    rows_filtered = 0

    for raw_line in readme_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue

        cells = _split_table_row(line)
        if len(cells) < 5 or _is_separator_row(cells):
            continue

        header = [cell.lower() for cell in cells[:5]]
        if header[:2] == ["company", "job title"]:
            continue

        company_cell, title_cell, *rest = cells
        company_name, company_url = _extract_link(company_cell)
        if company_name == "↳":
            company_name = previous_company_name
            company_url = previous_company_url
        elif company_name:
            previous_company_name = company_name
            previous_company_url = company_url

        title, url = _extract_link(title_cell)
        locations, work_model, date_label, date_posted = _parse_location_work_date(rest)

        if not company_name or not title or not url:
            continue

        rows_processed += 1
        internship = Internship(
            id=build_job_id([company_name, title, url, date_label]),
            company_name=company_name,
            title=title,
            locations=locations,
            work_model=work_model,
            url=url,
            date_posted=date_posted,
            date_posted_label=date_label,
            company_url=company_url,
        )

        if not internship.should_be_posted():
            continue

        if start_timestamp and date_posted and date_posted < start_timestamp:
            rows_filtered += 1
            continue

        scraped_data.add(internship)

    for season in SEASONS:
        getattr(scraped_data, season).sort(
            key=lambda item: item.date_posted,
            reverse=True,
        )

    logger.info(
        "Processed %s Jobright rows, filtered %s old rows, found %s season listings",
        rows_processed,
        rows_filtered,
        scraped_data.total_count(),
    )

    return scraped_data


class GitHubClient:
    """Client for fetching listings from GitHub."""

    def __init__(self):
        self.url = GITHUB_REPO_URL
        self.headers = {}
        if GITHUB_TOKEN:
            self.headers["Authorization"] = f"token {GITHUB_TOKEN}"
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with timeout configuration."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(headers=self.headers, timeout=timeout)
        return self._session

    async def close(self):
        """Cleanup aiohttp session. Call this when done with the client."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures session cleanup."""
        await self.close()

    async def _fetch_data(self) -> str:
        """Fetch raw README data from GitHub with retries."""

        async def _do_fetch():
            session = await self._get_session()
            async with session.get(self.url) as response:
                if response.status == 429:
                    raise RateLimitError("GitHub API rate limit exceeded")
                if response.status >= 500:
                    raise FetchError(f"GitHub server error: HTTP {response.status}")
                if response.status != 200:
                    raise FetchError(
                        f"Failed to fetch listings: HTTP {response.status}"
                    )

                text = await response.text()
                if README_MARKER not in text:
                    raise ParseError("Jobright README did not contain Daily Job List")
                return text

        try:
            return await retry_with_backoff(
                _do_fetch,
                max_retries=3,
                exceptions=(
                    NetworkError,
                    FetchError,
                    asyncio.TimeoutError,
                    aiohttp.ClientError,
                ),
            )
        except aiohttp.ClientError as exc:
            raise NetworkError(f"Network error: {exc}") from exc

    async def fetch_listings(self, start_timestamp: int | None = None) -> ScrapedData:
        """Fetch and parse listings from GitHub."""
        try:
            readme_text = await self._fetch_data()
        except asyncio.TimeoutError:
            raise NetworkError("Request timed out after 30 seconds")

        return parse_jobright_readme(readme_text, start_timestamp)

    async def get_allowlisted_listings(
        self,
        company_names: set[str],
        start_timestamp: int | None = None,
    ) -> ScrapedData:
        """Get allow-listed listings from the configured source."""
        all_listings = await self.fetch_listings(start_timestamp)
        return all_listings.filter_by_companies(company_names)
