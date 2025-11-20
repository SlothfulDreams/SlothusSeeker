"""GitHub client for fetching internship listings."""
import aiohttp
from typing import List, Dict
from src.config.settings import GITHUB_REPO_URL, GITHUB_TOKEN
from src.scraper.data_models import Internship, ScrapedData


class GitHubClient:
    """Client for fetching listings from GitHub."""

    def __init__(self):
        self.url = GITHUB_REPO_URL
        self.headers = {}
        if GITHUB_TOKEN:
            self.headers["Authorization"] = f"token {GITHUB_TOKEN}"

    async def fetch_listings(self) -> ScrapedData:
        """Fetch and parse listings from GitHub.

        Returns:
            ScrapedData object with summer and offseason listings separated
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url, headers=self.headers) as response:
                if response.status != 200:
                    raise Exception(f"Failed to fetch listings: HTTP {response.status}")

                data: List[Dict] = await response.json()

        # Parse and categorize internships
        scraped_data = ScrapedData()

        for item in data:
            try:
                internship = Internship(**item)

                # Only process active and visible internships
                if not internship.should_be_posted():
                    continue

                # Categorize by term
                if internship.is_summer:
                    scraped_data.summer.append(internship)
                elif internship.is_offseason:
                    scraped_data.offseason.append(internship)

            except Exception as e:
                # Skip invalid entries
                print(f"Warning: Failed to parse listing: {e}")
                continue

        return scraped_data

    async def get_new_listings(self, last_scrape_ids: Dict[str, set]) -> ScrapedData:
        """Get only new listings that weren't in the last scrape.

        Args:
            last_scrape_ids: Dict with 'summer' and 'offseason' keys containing sets of UUIDs

        Returns:
            ScrapedData with only new internships
        """
        all_listings = await self.fetch_listings()

        # Filter out already-posted listings
        new_data = ScrapedData()

        for internship in all_listings.summer:
            if internship.id not in last_scrape_ids.get("summer", set()):
                new_data.summer.append(internship)

        for internship in all_listings.offseason:
            if internship.id not in last_scrape_ids.get("offseason", set()):
                new_data.offseason.append(internship)

        return new_data, all_listings
