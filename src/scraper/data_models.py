"""Data models for internship listings."""
from datetime import datetime
from typing import List
from pydantic import BaseModel, Field


class Internship(BaseModel):
    """Model for a single internship listing."""

    id: str = Field(..., description="Unique UUID for the internship")
    company_name: str
    title: str
    locations: List[str]
    terms: List[str]  # e.g., ["Summer 2026"]
    sponsorship: str
    active: bool
    is_visible: bool
    url: str
    date_posted: int  # Unix timestamp
    date_updated: int  # Unix timestamp
    source: str = ""
    company_url: str = ""

    @property
    def is_summer(self) -> bool:
        """Check if this is a summer internship."""
        return any("Summer" in term for term in self.terms)

    @property
    def is_offseason(self) -> bool:
        """Check if this is an off-season internship (Fall/Winter/Spring)."""
        offseason_keywords = ["Fall", "Winter", "Spring"]
        return any(
            keyword in term
            for term in self.terms
            for keyword in offseason_keywords
        )

    @property
    def posted_date_str(self) -> str:
        """Get formatted posted date."""
        return datetime.fromtimestamp(self.date_posted).strftime("%B %d, %Y")

    @property
    def location_str(self) -> str:
        """Get formatted location string."""
        if not self.locations:
            return "Location not specified"
        return ", ".join(self.locations)

    def should_be_posted(self) -> bool:
        """Check if this internship should be posted to Discord."""
        return self.active and self.is_visible


class ScrapedData(BaseModel):
    """Model for scraped data organized by type."""

    summer: List[Internship] = Field(default_factory=list)
    offseason: List[Internship] = Field(default_factory=list)

    def get_all_ids(self, category: str) -> set[str]:
        """Get all IDs for a specific category."""
        listings = getattr(self, category, [])
        return {listing.id for listing in listings}
