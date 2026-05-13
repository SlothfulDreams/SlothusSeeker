"""Data models for internship listings."""

import hashlib
import re
from datetime import datetime
from typing import Iterable

from pydantic import BaseModel, Field

SEASONS = ("spring", "summer", "fall")
SEASON_DISPLAY_NAMES = {
    "spring": "Spring/Winter",
    "summer": "Summer",
    "fall": "Fall",
}
SEASON_MATCH_WORDS = {
    "spring": ("spring", "winter"),
    "summer": ("summer",),
    "fall": ("fall",),
}
SEASON_PATTERNS = {
    season: re.compile(rf"\b({'|'.join(words)})\b", re.IGNORECASE)
    for season, words in SEASON_MATCH_WORDS.items()
}


def normalize_company_name(company_name: str) -> str:
    """Normalize company names for case-insensitive Supabase matching."""
    cleaned = re.sub(r"\s+", " ", company_name.strip())
    return cleaned.lower()


def detect_seasons(title: str) -> list[str]:
    """Return seasons explicitly mentioned in the job title."""
    return [season for season in SEASONS if SEASON_PATTERNS[season].search(title)]


def build_job_id(parts: Iterable[str]) -> str:
    """Build a stable ID from Jobright row fields."""
    normalized = "|".join(part.strip().lower() for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class Internship(BaseModel):
    """Model for a single internship listing."""

    id: str = Field(..., description="Stable identifier for the internship")
    company_name: str
    title: str
    locations: list[str] = Field(default_factory=list)
    work_model: str = ""
    url: str
    date_posted: int = 0
    date_posted_label: str = ""
    company_url: str = ""

    @property
    def company_key(self) -> str:
        """Normalized company name for allow-list matching."""
        return normalize_company_name(self.company_name)

    @property
    def seasons(self) -> list[str]:
        """Seasons explicitly present in the title."""
        return detect_seasons(self.title)

    @property
    def primary_season(self) -> str | None:
        """First matched season, used for embed color and compact previews."""
        seasons = self.seasons
        return seasons[0] if seasons else None

    @property
    def posted_date_str(self) -> str:
        """Get formatted posted date."""
        if self.date_posted_label:
            return self.date_posted_label
        if not self.date_posted:
            return "Date not specified"
        return datetime.fromtimestamp(self.date_posted).strftime("%B %d, %Y")

    @property
    def location_str(self) -> str:
        """Get formatted location string."""
        if not self.locations:
            return "Location not specified"
        return ", ".join(self.locations)

    def should_be_posted(self) -> bool:
        """Check if this internship has enough data to post to Discord."""
        return bool(self.url and self.seasons)


class ScrapedData(BaseModel):
    """Model for scraped data organized by season."""

    spring: list[Internship] = Field(default_factory=list)
    summer: list[Internship] = Field(default_factory=list)
    fall: list[Internship] = Field(default_factory=list)

    def add(self, internship: Internship) -> None:
        """Add an internship to every explicitly matched season bucket."""
        for season in internship.seasons:
            self.add_to_season(season, internship)

    def add_to_season(self, season: str, internship: Internship) -> None:
        """Add an internship to a season bucket if it is not already present."""
        listings = getattr(self, season)
        if internship.id in {listing.id for listing in listings}:
            return
        listings.append(internship)

    def filter_by_companies(self, company_names: set[str]) -> "ScrapedData":
        """Return only listings whose normalized company name is allow-listed."""
        normalized_names = {normalize_company_name(name) for name in company_names}
        filtered = ScrapedData()
        for season in SEASONS:
            setattr(
                filtered,
                season,
                [
                    listing
                    for listing in getattr(self, season)
                    if listing.company_key in normalized_names
                ],
            )
        return filtered

    def get_all_ids(self, category: str) -> set[str]:
        """Get all IDs for a specific season."""
        listings = getattr(self, category, [])
        return {listing.id for listing in listings}

    def total_count(self) -> int:
        """Count listings across all season buckets."""
        return sum(len(getattr(self, season)) for season in SEASONS)
