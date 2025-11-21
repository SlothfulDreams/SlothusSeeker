"""Tests for data models."""
import pytest
from datetime import datetime
from src.scraper.data_models import Internship, ScrapedData


class TestInternshipModel:
    """Test Internship Pydantic model."""

    @pytest.fixture
    def sample_summer_internship(self):
        """Create a sample summer internship."""
        return {
            "id": "test-uuid-123",
            "company_name": "Google",
            "title": "Software Engineering Intern",
            "locations": ["Mountain View, CA", "New York, NY"],
            "terms": ["Summer 2026"],
            "sponsorship": "Offers Sponsorship",
            "active": True,
            "is_visible": True,
            "url": "https://example.com/apply",
            "date_posted": 1700000000,
            "date_updated": 1700000000,
            "source": "reddoy",
            "company_url": "https://google.com"
        }

    @pytest.fixture
    def sample_offseason_internship(self):
        """Create a sample off-season internship."""
        return {
            "id": "test-uuid-456",
            "company_name": "Meta",
            "title": "Product Manager Intern",
            "locations": ["Menlo Park, CA"],
            "terms": ["Fall 2025"],
            "sponsorship": "Does not offer sponsorship",
            "active": True,
            "is_visible": True,
            "url": "https://example.com/apply2",
            "date_posted": 1699000000,
            "date_updated": 1699000000,
            "source": "pitt-csc",
            "company_url": ""
        }

    def test_internship_creation(self, sample_summer_internship):
        """Test creating an Internship model."""
        internship = Internship(**sample_summer_internship)

        assert internship.id == "test-uuid-123"
        assert internship.company_name == "Google"
        assert internship.title == "Software Engineering Intern"
        assert len(internship.locations) == 2

    def test_is_summer_property(self, sample_summer_internship):
        """Test is_summer property."""
        internship = Internship(**sample_summer_internship)
        assert internship.is_summer is True

    def test_is_summer_property_multiple_terms(self):
        """Test is_summer with multiple terms including summer."""
        data = {
            "id": "test-uuid",
            "company_name": "Test",
            "title": "Test Intern",
            "locations": ["Remote"],
            "terms": ["Summer 2026", "Summer 2027"],
            "sponsorship": "",
            "active": True,
            "is_visible": True,
            "url": "https://test.com",
            "date_posted": 1700000000,
            "date_updated": 1700000000,
            "source": "test",
            "company_url": ""
        }
        internship = Internship(**data)
        assert internship.is_summer is True

    def test_is_offseason_fall(self, sample_offseason_internship):
        """Test is_offseason property with Fall."""
        internship = Internship(**sample_offseason_internship)
        assert internship.is_offseason is True

    def test_is_offseason_winter(self):
        """Test is_offseason property with Winter."""
        data = {
            "id": "test-uuid",
            "company_name": "Test",
            "title": "Test Intern",
            "locations": ["Remote"],
            "terms": ["Winter 2026"],
            "sponsorship": "",
            "active": True,
            "is_visible": True,
            "url": "https://test.com",
            "date_posted": 1700000000,
            "date_updated": 1700000000,
            "source": "test",
            "company_url": ""
        }
        internship = Internship(**data)
        assert internship.is_offseason is True

    def test_is_offseason_spring(self):
        """Test is_offseason property with Spring."""
        data = {
            "id": "test-uuid",
            "company_name": "Test",
            "title": "Test Intern",
            "locations": ["Remote"],
            "terms": ["Spring 2027"],
            "sponsorship": "",
            "active": True,
            "is_visible": True,
            "url": "https://test.com",
            "date_posted": 1700000000,
            "date_updated": 1700000000,
            "source": "test",
            "company_url": ""
        }
        internship = Internship(**data)
        assert internship.is_offseason is True

    def test_should_be_posted_active_visible(self, sample_summer_internship):
        """Test should_be_posted when active and visible."""
        internship = Internship(**sample_summer_internship)
        assert internship.should_be_posted() is True

    def test_should_be_posted_inactive(self, sample_summer_internship):
        """Test should_be_posted when inactive."""
        sample_summer_internship["active"] = False
        internship = Internship(**sample_summer_internship)
        assert internship.should_be_posted() is False

    def test_should_be_posted_not_visible(self, sample_summer_internship):
        """Test should_be_posted when not visible."""
        sample_summer_internship["is_visible"] = False
        internship = Internship(**sample_summer_internship)
        assert internship.should_be_posted() is False

    def test_posted_date_str(self, sample_summer_internship):
        """Test posted_date_str property."""
        internship = Internship(**sample_summer_internship)
        date_str = internship.posted_date_str

        # Should be formatted as "Month Day, Year"
        assert isinstance(date_str, str)
        assert "," in date_str
        assert "202" in date_str  # Year should contain 202X

    def test_location_str_multiple_locations(self, sample_summer_internship):
        """Test location_str with multiple locations."""
        internship = Internship(**sample_summer_internship)
        assert internship.location_str == "Mountain View, CA, New York, NY"

    def test_location_str_single_location(self, sample_offseason_internship):
        """Test location_str with single location."""
        internship = Internship(**sample_offseason_internship)
        assert internship.location_str == "Menlo Park, CA"

    def test_location_str_no_location(self, sample_summer_internship):
        """Test location_str with no locations."""
        sample_summer_internship["locations"] = []
        internship = Internship(**sample_summer_internship)
        assert internship.location_str == "Location not specified"


class TestScrapedDataModel:
    """Test ScrapedData model."""

    def test_scraped_data_initialization(self):
        """Test ScrapedData initializes with empty lists."""
        data = ScrapedData()
        assert data.summer == []
        assert data.offseason == []

    def test_get_all_ids_summer(self):
        """Test get_all_ids for summer internships."""
        data = ScrapedData()
        data.summer = [
            Internship(
                id="uuid1",
                company_name="Test1",
                title="Test",
                locations=["Remote"],
                terms=["Summer 2026"],
                sponsorship="",
                active=True,
                is_visible=True,
                url="https://test.com",
                date_posted=1700000000,
                date_updated=1700000000,
                source="test",
                company_url=""
            ),
            Internship(
                id="uuid2",
                company_name="Test2",
                title="Test",
                locations=["Remote"],
                terms=["Summer 2026"],
                sponsorship="",
                active=True,
                is_visible=True,
                url="https://test.com",
                date_posted=1700000000,
                date_updated=1700000000,
                source="test",
                company_url=""
            )
        ]

        ids = data.get_all_ids("summer")
        assert ids == {"uuid1", "uuid2"}

    def test_get_all_ids_offseason(self):
        """Test get_all_ids for offseason internships."""
        data = ScrapedData()
        data.offseason = [
            Internship(
                id="uuid3",
                company_name="Test3",
                title="Test",
                locations=["Remote"],
                terms=["Fall 2025"],
                sponsorship="",
                active=True,
                is_visible=True,
                url="https://test.com",
                date_posted=1700000000,
                date_updated=1700000000,
                source="test",
                company_url=""
            )
        ]

        ids = data.get_all_ids("offseason")
        assert ids == {"uuid3"}

    def test_get_all_ids_empty(self):
        """Test get_all_ids with no internships."""
        data = ScrapedData()
        ids = data.get_all_ids("summer")
        assert ids == set()
