"""GitHub client for fetching Jobright internship listings."""

import asyncio
import re
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import NamedTuple

import aiohttp

from src.config.settings import (
    GITHUB_REPO_URL,
    GITHUB_TOKEN,
    SIMPLIFY_OFF_SEASON_REPO_URL,
    SIMPLIFY_SUMMER_REPO_URL,
)
from src.scraper.data_models import (
    Internship,
    SEASONS,
    ScrapedData,
    build_job_id,
    detect_seasons,
    infer_job_year,
)
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
SIMPLIFY_MARKER = "Internship Roles"
SIMPLIFY_TARGET_SECTIONS = (
    "Software Engineering Internship Roles",
    "Data Science, AI & Machine Learning Internship Roles",
)
AGE_RE = re.compile(r"^\s*(\d+)\s*(h|d|mo)\s*$", re.IGNORECASE)


def _strip_markdown(value: str) -> str:
    value = value.replace("<br>", " ")
    value = re.sub(r"</?[^>]+>", " ", value)
    value = value.replace("**", "").replace("__", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _strip_html_markdown(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(
        r"</?(?:details|summary|strong|div|sub|i|p|a|img)[^>]*>",
        " ",
        value,
    )
    return _strip_markdown(value)


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


def _parse_age_label(age_label: str) -> int:
    match = AGE_RE.match(age_label)
    if not match:
        return 0

    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "h":
        delta = timedelta(hours=amount)
    elif unit == "d":
        delta = timedelta(days=amount)
    else:
        delta = timedelta(days=amount * 30)
    return int((datetime.now() - delta).timestamp())


def _parse_location_work_date(rest: list[str]) -> tuple[list[str], str, str, int]:
    if not rest:
        return [], "", "", 0

    # Read the location column independently: searching the combined row for
    # "Remote" used to discard country qualifiers such as "Remote in USA".
    location_cell = re.sub(r"<br\s*/?>", "\n", rest[0], flags=re.IGNORECASE)
    locations = [
        location
        for line in location_cell.splitlines()
        if (location := _strip_markdown(line))
    ]
    text = " ".join(_strip_markdown(cell) for cell in rest[1:] if cell).strip()

    work_model = ""
    work_match = WORK_MODE_RE.search(text)
    if work_match:
        work_model = work_match.group(1).title()

    date_label = ""
    date_match = DATE_RE.search(text)
    if date_match:
        date_label = date_match.group(0)

    return locations, work_model, date_label, _parse_date_label(date_label)


def _readme_title(readme_text: str) -> str:
    for line in readme_text.splitlines():
        if line.lstrip().startswith("#"):
            return _strip_html_markdown(line.lstrip("# "))
    return ""


def _first_numeric_year(*values: str) -> str:
    for value in values:
        for token in re.split(r"\D+", value):
            if token.isnumeric() and len(token) == 4 and token.startswith("20"):
                return token
    return ""


def _default_terms_from_source(
    readme_text: str,
    source_url: str = "",
    season: str = "",
) -> list[str]:
    year = _first_numeric_year(_readme_title(readme_text), source_url)
    if not year:
        return []
    return [f"{season} {year}".strip()]


class _SimplifyCell(NamedTuple):
    text: str
    links: list[str]


class _SimplifyRowCells(NamedTuple):
    company: _SimplifyCell
    title: _SimplifyCell
    location: _SimplifyCell
    terms: _SimplifyCell | None
    application: _SimplifyCell
    age: _SimplifyCell


class _SimplifyTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[_SimplifyCell]] = []
        self._current_row: list[_SimplifyCell] | None = None
        self._current_cell_text: list[str] | None = None
        self._current_cell_links: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag == "td" and self._current_row is not None:
            self._current_cell_text = []
            self._current_cell_links = []
        elif tag == "br" and self._current_cell_text is not None:
            self._current_cell_text.append("\n")
        elif tag == "a" and self._current_cell_links is not None:
            href = dict(attrs).get("href")
            if href:
                self._current_cell_links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "summary" and self._current_cell_text is not None:
            self._current_cell_text.append("\n")
        elif tag == "td" and self._current_row is not None:
            text = self._clean_text("".join(self._current_cell_text or []))
            self._current_row.append(
                _SimplifyCell(text=text, links=self._current_cell_links or [])
            )
            self._current_cell_text = None
            self._current_cell_links = None
        elif tag == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data: str) -> None:
        if self._current_cell_text is not None:
            self._current_cell_text.append(data)

    @staticmethod
    def _clean_text(value: str) -> str:
        lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
        return "\n".join(line for line in lines if line)


def _simplify_sections(readme_text: str) -> list[str]:
    sections = []
    active_lines: list[str] | None = None

    for line in readme_text.splitlines():
        if line.startswith("## "):
            if active_lines:
                sections.append("\n".join(active_lines))
            active_lines = (
                [line]
                if any(section_name in line for section_name in SIMPLIFY_TARGET_SECTIONS)
                else None
            )
            continue

        if active_lines is not None:
            active_lines.append(line)

    if active_lines:
        sections.append("\n".join(active_lines))
    return sections


def _simplify_company_name(cell_text: str) -> str:
    if cell_text.strip() == "↳":
        return "↳"
    return re.sub(r"^[^\w]+", "", cell_text).strip()


def _simplify_application_url(links: list[str]) -> str:
    for link in links:
        if "simplify.jobs/p/" not in link:
            return link
    return links[0] if links else ""


def _simplify_locations(cell_text: str) -> list[str]:
    locations = []
    for line in cell_text.splitlines() or [cell_text]:
        location = re.sub(r"^\d+\s+locations?\s*", "", line, flags=re.IGNORECASE)
        location = location.strip(" ,-")
        if location:
            locations.append(location)
    return locations


def _simplify_row_cells(row: list[_SimplifyCell]) -> _SimplifyRowCells | None:
    if len(row) < 5:
        return None

    has_terms_column = len(row) >= 6
    return _SimplifyRowCells(
        company=row[0],
        title=row[1],
        location=row[2],
        terms=row[3] if has_terms_column else None,
        application=row[4] if has_terms_column else row[3],
        age=row[5] if has_terms_column else row[4],
    )


def _merge_scraped_data(target: ScrapedData, source: ScrapedData) -> None:
    for season in SEASONS:
        for internship in getattr(source, season):
            target.add_to_season(season, internship)


def parse_jobright_readme(
    readme_text: str,
    start_timestamp: int | None = None,
    default_terms: list[str] | None = None,
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
        job_year = infer_job_year(title, default_terms)
        internship = Internship(
            id=build_job_id(
                company_name=company_name,
                title=title,
                locations=locations,
                terms=default_terms,
            ),
            company_name=company_name,
            title=title,
            locations=locations,
            work_model=work_model,
            url=url,
            date_posted=date_posted,
            date_posted_label=date_label,
            company_url=company_url,
            job_year=job_year,
            source="Jobright",
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


def parse_simplify_readme(
    readme_text: str,
    *,
    source_name: str,
    default_seasons: list[str] | None = None,
    default_terms: list[str] | None = None,
    start_timestamp: int | None = None,
) -> ScrapedData:
    """Parse selected Simplify README sections into season-bucketed internships."""
    scraped_data = ScrapedData()
    previous_company_name = ""
    previous_company_url = ""
    rows_processed = 0
    rows_filtered = 0

    for section in _simplify_sections(readme_text):
        parser = _SimplifyTableParser()
        parser.feed(section)

        for row in parser.rows:
            cells = _simplify_row_cells(row)
            if cells is None:
                continue

            company_name = _simplify_company_name(cells.company.text)
            company_url = cells.company.links[0] if cells.company.links else ""
            if company_name == "↳":
                company_name = previous_company_name
                company_url = previous_company_url
            elif company_name:
                previous_company_name = company_name
                previous_company_url = company_url

            title = _strip_html_markdown(cells.title.text)
            locations = _simplify_locations(cells.location.text)
            terms = cells.terms.text if cells.terms else " ".join(default_terms or [])
            seasons = default_seasons or []
            if not seasons:
                seasons = detect_seasons(f"{title} {terms}")

            url = _simplify_application_url(cells.application.links)
            age_label = _strip_html_markdown(cells.age.text)
            date_posted = _parse_age_label(age_label)

            if not company_name or not title or not url:
                continue

            rows_processed += 1
            terms_for_year = [terms] if terms else []
            job_year = infer_job_year(title, terms_for_year)
            internship = Internship(
                id=build_job_id(
                    company_name=company_name,
                    title=title,
                    locations=locations,
                    terms=terms_for_year,
                ),
                company_name=company_name,
                title=title,
                locations=locations,
                url=url,
                date_posted=date_posted,
                date_posted_label=age_label,
                company_url=company_url,
                job_year=job_year,
                season_tags=seasons,
                source=source_name,
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
        "Processed %s %s rows, filtered %s old rows, found %s season listings",
        rows_processed,
        source_name,
        rows_filtered,
        scraped_data.total_count(),
    )

    return scraped_data


class GitHubClient:
    """Client for fetching listings from GitHub."""

    def __init__(self):
        self.url = GITHUB_REPO_URL
        self.simplify_summer_url = SIMPLIFY_SUMMER_REPO_URL
        self.simplify_off_season_url = SIMPLIFY_OFF_SEASON_REPO_URL
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

    async def _fetch_url(self, url: str, marker: str) -> str:
        """Fetch raw README data from GitHub with retries."""

        async def _do_fetch():
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 429:
                    raise RateLimitError("GitHub API rate limit exceeded")
                if response.status >= 500:
                    raise FetchError(f"GitHub server error: HTTP {response.status}")
                if response.status != 200:
                    raise FetchError(
                        f"Failed to fetch listings: HTTP {response.status}"
                    )

                text = await response.text()
                if marker not in text:
                    raise ParseError(f"GitHub README did not contain {marker}")
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
        """Fetch and parse listings from Jobright and Simplify."""
        try:
            jobright_text, simplify_summer_text, simplify_off_season_text = (
                await asyncio.gather(
                    self._fetch_url(self.url, README_MARKER),
                    self._fetch_url(self.simplify_summer_url, SIMPLIFY_MARKER),
                    self._fetch_url(self.simplify_off_season_url, SIMPLIFY_MARKER),
                )
            )
        except asyncio.TimeoutError:
            raise NetworkError("Request timed out after 30 seconds")

        listings = parse_jobright_readme(
            jobright_text,
            start_timestamp,
            default_terms=_default_terms_from_source(jobright_text, self.url),
        )
        _merge_scraped_data(
            listings,
            parse_simplify_readme(
                simplify_summer_text,
                source_name="Simplify Summer",
                default_seasons=["summer"],
                default_terms=_default_terms_from_source(
                    simplify_summer_text,
                    self.simplify_summer_url,
                    season="Summer",
                ),
                start_timestamp=start_timestamp,
            ),
        )
        _merge_scraped_data(
            listings,
            parse_simplify_readme(
                simplify_off_season_text,
                source_name="Simplify Off-Season",
                default_terms=_default_terms_from_source(
                    simplify_off_season_text,
                    self.simplify_off_season_url,
                ),
                start_timestamp=start_timestamp,
            ),
        )
        return listings

    async def get_allowlisted_listings(
        self,
        company_names: set[str],
        start_timestamp: int | None = None,
    ) -> ScrapedData:
        """Get allow-listed listings from the configured source."""
        all_listings = await self.fetch_listings(start_timestamp)
        return all_listings.filter_by_companies(company_names)
