"""Tests for GitHubClient."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.scraper.github_client import GitHubClient
from src.scraper.data_models import Internship, ScrapedData


@pytest.fixture
def sample_listings_data():
    """Sample listings.json data."""
    return [
        {
            "id": "summer-1",
            "company_name": "Google",
            "title": "SWE Intern",
            "locations": ["Mountain View, CA"],
            "terms": ["Summer 2026"],
            "sponsorship": "Offers Sponsorship",
            "active": True,
            "is_visible": True,
            "url": "https://example.com/1",
            "date_posted": 1732000000,  # Recent
            "date_updated": 1732000000,
            "source": "test",
            "company_url": ""
        },
        {
            "id": "summer-2",
            "company_name": "Meta",
            "title": "PM Intern",
            "locations": ["Menlo Park, CA"],
            "terms": ["Summer 2026"],
            "sponsorship": "",
            "active": True,
            "is_visible": True,
            "url": "https://example.com/2",
            "date_posted": 1731900000,  # Recent
            "date_updated": 1731900000,
            "source": "test",
            "company_url": ""
        },
        {
            "id": "offseason-1",
            "company_name": "Amazon",
            "title": "Data Intern",
            "locations": ["Seattle, WA"],
            "terms": ["Fall 2025"],
            "sponsorship": "",
            "active": True,
            "is_visible": True,
            "url": "https://example.com/3",
            "date_posted": 1731800000,  # Recent
            "date_updated": 1731800000,
            "source": "test",
            "company_url": ""
        },
        {
            "id": "old-1",
            "company_name": "OldCorp",
            "title": "Old Intern",
            "locations": ["Remote"],
            "terms": ["Summer 2026"],
            "sponsorship": "",
            "active": True,
            "is_visible": True,
            "url": "https://example.com/4",
            "date_posted": 1700000000,  # Old
            "date_updated": 1700000000,
            "source": "test",
            "company_url": ""
        },
        {
            "id": "inactive-1",
            "company_name": "InactiveCorp",
            "title": "Inactive Intern",
            "locations": ["Remote"],
            "terms": ["Summer 2026"],
            "sponsorship": "",
            "active": False,  # Inactive
            "is_visible": True,
            "url": "https://example.com/5",
            "date_posted": 1732000000,
            "date_updated": 1732000000,
            "source": "test",
            "company_url": ""
        }
    ]


class MockResponse:
    """Mock response object for aiohttp."""
    def __init__(self, json_data, status=200):
        self.status = status
        self._json_data = json_data

    async def json(self):
        return self._json_data


def create_mock_session(json_data, status=200):
    """Helper to create properly mocked aiohttp session."""
    mock_response = MockResponse(json_data, status)

    # __aexit__ must be an async function that accepts (exc_type, exc_val, exc_tb)
    # and returns False/None to propagate exceptions
    async def mock_aexit(*args):
        return None  # Don't suppress exceptions

    mock_get = AsyncMock()
    mock_get.__aenter__.return_value = mock_response
    mock_get.__aexit__ = mock_aexit

    mock_session_instance = AsyncMock()
    mock_session_instance.get = MagicMock(return_value=mock_get)

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session_instance
    mock_session.__aexit__ = mock_aexit

    return mock_session


class TestGitHubClientFetchListings:
    """Test GitHubClient fetch_listings method."""

    @pytest.mark.asyncio
    async def test_fetch_listings_success(self, sample_listings_data):
        """Test successfully fetching listings."""
        mock_session = create_mock_session(sample_listings_data)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            client = GitHubClient()
            result = await client.fetch_listings()

            assert isinstance(result, ScrapedData)
            # Without date filter, gets all active/visible: summer-1, summer-2, old-1
            assert len(result.summer) == 3
            assert len(result.offseason) == 1  # offseason-1
            # inactive-1 should be filtered out (not active)

    @pytest.mark.asyncio
    async def test_fetch_listings_with_date_filter(self, sample_listings_data):
        """Test fetching listings with start_timestamp filter."""
        start_timestamp = 1731850000  # After offseason-1, before summer-2

        mock_session = create_mock_session(sample_listings_data)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            client = GitHubClient()
            result = await client.fetch_listings(start_timestamp=start_timestamp)

            # Should only get entries newer than start_timestamp
            assert len(result.summer) == 2  # summer-1, summer-2
            assert len(result.offseason) == 0  # offseason-1 is too old

    @pytest.mark.asyncio
    async def test_fetch_listings_http_error(self):
        """Test handling HTTP errors."""
        mock_session = create_mock_session([], status=404)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            client = GitHubClient()
            with pytest.raises(Exception, match="Failed to fetch listings"):
                await client.fetch_listings()

    @pytest.mark.asyncio
    async def test_fetch_listings_filters_inactive(self, sample_listings_data):
        """Test that inactive internships are filtered out."""
        mock_session = create_mock_session(sample_listings_data)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            client = GitHubClient()
            result = await client.fetch_listings()

            # inactive-1 should not be in results
            all_ids = [i.id for i in result.summer + result.offseason]
            assert "inactive-1" not in all_ids

    @pytest.mark.asyncio
    async def test_fetch_listings_categorizes_correctly(self, sample_listings_data):
        """Test that internships are categorized correctly."""
        mock_session = create_mock_session(sample_listings_data)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            client = GitHubClient()
            result = await client.fetch_listings()

            summer_ids = {i.id for i in result.summer}
            offseason_ids = {i.id for i in result.offseason}

            assert "summer-1" in summer_ids
            assert "summer-2" in summer_ids
            assert "offseason-1" in offseason_ids


class TestGitHubClientGetNewListings:
    """Test GitHubClient get_new_listings method."""

    @pytest.mark.asyncio
    async def test_get_new_listings_all_new(self, sample_listings_data):
        """Test getting new listings when nothing was scraped before."""
        mock_session = create_mock_session(sample_listings_data)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            client = GitHubClient()
            last_scrape_ids = {"summer": set(), "offseason": set()}

            new_data, all_data = await client.get_new_listings(last_scrape_ids)

            # All active listings should be new (without date filter includes old-1)
            assert len(new_data.summer) == 3  # summer-1, summer-2, old-1
            assert len(new_data.offseason) == 1

    @pytest.mark.asyncio
    async def test_get_new_listings_filters_seen(self, sample_listings_data):
        """Test that previously seen listings are filtered out."""
        mock_session = create_mock_session(sample_listings_data)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            client = GitHubClient()
            last_scrape_ids = {
                "summer": {"summer-1"},  # Already seen
                "offseason": {"offseason-1"}  # Already seen
            }

            new_data, all_data = await client.get_new_listings(last_scrape_ids)

            # summer-2 and old-1 should be new (summer-1 filtered out)
            assert len(new_data.summer) == 2
            new_ids = {i.id for i in new_data.summer}
            assert "summer-2" in new_ids
            assert "old-1" in new_ids
            assert len(new_data.offseason) == 0

    @pytest.mark.asyncio
    async def test_get_new_listings_returns_all_data(self, sample_listings_data):
        """Test that get_new_listings returns both new and all data."""
        mock_session = create_mock_session(sample_listings_data)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            client = GitHubClient()
            last_scrape_ids = {"summer": set(), "offseason": set()}

            new_data, all_data = await client.get_new_listings(last_scrape_ids)

            # all_data should contain everything active/visible (without date filter includes old-1)
            assert len(all_data.summer) == 3  # summer-1, summer-2, old-1
            assert len(all_data.offseason) == 1

    @pytest.mark.asyncio
    async def test_get_new_listings_with_date_filter(self, sample_listings_data):
        """Test get_new_listings with start_timestamp."""
        start_timestamp = 1731850000

        mock_session = create_mock_session(sample_listings_data)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            client = GitHubClient()
            last_scrape_ids = {"summer": set(), "offseason": set()}

            new_data, all_data = await client.get_new_listings(
                last_scrape_ids,
                start_timestamp=start_timestamp
            )

            # Only entries after timestamp
            assert len(new_data.summer) == 2
            assert len(new_data.offseason) == 0
