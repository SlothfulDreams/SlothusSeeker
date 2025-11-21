"""GitHub client for fetching internship listings."""
import aiohttp
from typing import List, Dict, Optional
from src.config.settings import GITHUB_REPO_URL, GITHUB_TOKEN
from src.scraper.data_models import Internship, ScrapedData


class GitHubClient:
    """Client for fetching listings from GitHub."""

    def __init__(self):
        self.url = GITHUB_REPO_URL
        self.headers = {}
        if GITHUB_TOKEN:
            self.headers["Authorization"] = f"token {GITHUB_TOKEN}"

    async def fetch_listings(self, start_timestamp: Optional[int] = None) -> ScrapedData:
        """Fetch and parse listings from GitHub.

        Args:
            start_timestamp: Only include internships posted after this timestamp

        Returns:
            ScrapedData object with summer and offseason listings separated
        """
        # Fetch data from GitHub
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url, headers=self.headers) as response:
                if response.status != 200:
                    raise Exception(f"Failed to fetch listings: HTTP {response.status}")

                data: List[Dict] = await response.json()

        # Parse and categorize internships
        scraped_data = ScrapedData()
        entries_processed = 0
        entries_skipped_old = 0

        for item in data:
            try:
                internship = Internship(**item)
                entries_processed += 1

                # Only process active and visible internships
                if not internship.should_be_posted():
                    continue

                # OPTIMIZATION: Stop processing if we hit old entries
                # Assumes listings.json is sorted newest-first by date_posted
                if start_timestamp and internship.date_posted < start_timestamp:
                    entries_skipped_old = len(data) - entries_processed
                    print(f"[Scraper] Stopping early: hit entries older than {start_timestamp}")
                    print(f"[Scraper] Processed {entries_processed} entries, skipped {entries_skipped_old} old entries")
                    break  # All remaining entries will be even older

                # Categorize by term
                if internship.is_summer:
                    scraped_data.summer.append(internship)
                elif internship.is_offseason:
                    scraped_data.offseason.append(internship)

            except Exception as e:
                # Skip invalid entries
                print(f"Warning: Failed to parse listing: {e}")
                continue

        if entries_skipped_old == 0:
            print(f"[Scraper] Processed all {entries_processed} entries")

        return scraped_data

    async def get_new_listings(
        self,
        last_scrape_ids: Dict[str, set],
        start_timestamp: Optional[int] = None
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
