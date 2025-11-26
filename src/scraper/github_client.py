"""GitHub client for fetching internship listings."""

import asyncio
import json
from typing import Dict, List, Optional

import aiohttp

from src.config.settings import GITHUB_REPO_URL, GITHUB_TOKEN
from src.scraper.data_models import Internship, ScrapedData
from src.scraper.exceptions import FetchError, NetworkError, ParseError, RateLimitError
from src.utils.logger import setup_logger
from src.utils.retry import retry_with_backoff

logger = setup_logger(__name__)


class GitHubClient:
    """Client for fetching listings from GitHub."""

    def __init__(self):
        self.url = GITHUB_REPO_URL
        self.headers = {}
        if GITHUB_TOKEN:
            self.headers["Authorization"] = f"token {GITHUB_TOKEN}"
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with timeout configuration.

        Returns:
            ClientSession instance with configured timeout
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
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

    async def _fetch_data(self) -> List[Dict]:
        """Fetch raw data from GitHub with retries.

        Returns:
            List of dictionaries containing internship data
        """

        async def _do_fetch():
            session = await self._get_session()
            async with session.get(self.url) as response:
                if response.status == 429:
                    raise RateLimitError("GitHub API rate limit exceeded")
                elif response.status >= 500:
                    raise FetchError(f"GitHub server error: HTTP {response.status}")
                elif response.status != 200:
                    raise FetchError(
                        f"Failed to fetch listings: HTTP {response.status}"
                    )

                # Check content type and parse accordingly
                content_type = response.headers.get("Content-Type", "")
                logger.debug(f"Response Content-Type: {content_type}")

                try:
                    # GitHub raw URLs often return text/plain even for JSON files
                    if "application/json" in content_type:
                        # Direct JSON parsing
                        data = await response.json()
                    else:
                        # Text response (common for raw GitHub URLs) - get text then parse
                        text = await response.text()
                        logger.debug(f"Received text response, length: {len(text)}")
                        data = json.loads(text)

                    return data
                except json.JSONDecodeError as e:
                    raise ParseError(f"Invalid JSON response: {e}")
                except Exception as e:
                    raise ParseError(f"Failed to parse response: {e}")

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
        except aiohttp.ClientError as e:
            raise NetworkError(f"Network error: {e}")

    async def fetch_listings(
        self, start_timestamp: Optional[int] = None
    ) -> ScrapedData:
        """Fetch and parse listings from GitHub.

        Args:
            start_timestamp: Only include internships posted after this timestamp

        Returns:
            ScrapedData object with summer and offseason listings separated
        """
        # Fetch data from GitHub with retry logic
        try:
            data = await self._fetch_data()
        except asyncio.TimeoutError:
            raise NetworkError("Request timed out after 30 seconds")

        # Parse and categorize internships
        scraped_data = ScrapedData()
        entries_processed = 0
        entries_filtered = 0

        for item in data:
            try:
                internship = Internship(**item)
                entries_processed += 1

                # Only process active and visible internships
                if not internship.should_be_posted():
                    continue

                # Filter by date (but don't break - data is unsorted)
                if start_timestamp and internship.date_posted < start_timestamp:
                    entries_filtered += 1
                    continue  # Skip old entry, keep processing others

                # Categorize by term
                if internship.is_summer:
                    scraped_data.summer.append(internship)
                elif internship.is_offseason:
                    scraped_data.offseason.append(internship)

            except Exception as e:
                # Skip invalid entries
                logger.warning(f"Failed to parse listing: {e}")
                continue

        # Sort results by date (newest first) since GitHub data is unsorted
        scraped_data.summer.sort(key=lambda x: x.date_posted, reverse=True)
        scraped_data.offseason.sort(key=lambda x: x.date_posted, reverse=True)

        logger.info(
            f"Processed {entries_processed} entries, "
            f"filtered {entries_filtered} old entries, "
            f"found {len(scraped_data.summer)} summer + {len(scraped_data.offseason)} off-season"
        )

        return scraped_data

    async def get_new_listings(
        self, last_scrape_ids: Dict[str, set], start_timestamp: Optional[int] = None
    ) -> tuple[ScrapedData, ScrapedData]:
        """Get only new listings that weren't in the last scrape.

        Args:
            last_scrape_ids: Dict with 'summer' and 'offseason' keys containing sets of UUIDs
            start_timestamp: Only include internships posted after this timestamp

        Returns:
            Tuple of (new_data, all_listings)
        """
        all_listings = await self.fetch_listings(start_timestamp)

        # Filter out already-posted listings
        new_data = ScrapedData()

        for internship in all_listings.summer:
            if internship.id not in last_scrape_ids.get("summer", set()):
                new_data.summer.append(internship)

        for internship in all_listings.offseason:
            if internship.id not in last_scrape_ids.get("offseason", set()):
                new_data.offseason.append(internship)

        return new_data, all_listings
