"""Data models for internship listings."""

import hashlib
import re
from datetime import datetime

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
YEAR_RE = re.compile(r"\b20\d{2}\b")
SEASON_IDENTITY_WORDS = {
    word for words in SEASON_MATCH_WORDS.values() for word in words
}
JOB_TITLE_STOP_WORDS = {
    "intern",
    "internship",
    "co",
    "op",
    "coop",
    "student",
}
LOCATION_EXACT_ALIASES = {
    "nyc": "new york ny",
    "new york city": "new york ny",
    "new york new york": "new york ny",
    "sf": "san francisco ca",
    "san francisco california": "san francisco ca",
    "remote in usa": "remote us",
    "remote in us": "remote us",
    "remote united states": "remote us",
    "remote in united states": "remote us",
}
US_STATE_ALIASES = {
    "alabama": "al",
    "alaska": "ak",
    "arizona": "az",
    "arkansas": "ar",
    "california": "ca",
    "colorado": "co",
    "connecticut": "ct",
    "delaware": "de",
    "district of columbia": "dc",
    "florida": "fl",
    "georgia": "ga",
    "hawaii": "hi",
    "idaho": "id",
    "illinois": "il",
    "indiana": "in",
    "iowa": "ia",
    "kansas": "ks",
    "kentucky": "ky",
    "louisiana": "la",
    "maine": "me",
    "maryland": "md",
    "massachusetts": "ma",
    "michigan": "mi",
    "minnesota": "mn",
    "mississippi": "ms",
    "missouri": "mo",
    "montana": "mt",
    "nebraska": "ne",
    "nevada": "nv",
    "new hampshire": "nh",
    "new jersey": "nj",
    "new mexico": "nm",
    "new york": "ny",
    "north carolina": "nc",
    "north dakota": "nd",
    "ohio": "oh",
    "oklahoma": "ok",
    "oregon": "or",
    "pennsylvania": "pa",
    "rhode island": "ri",
    "south carolina": "sc",
    "south dakota": "sd",
    "tennessee": "tn",
    "texas": "tx",
    "utah": "ut",
    "vermont": "vt",
    "virginia": "va",
    "washington": "wa",
    "west virginia": "wv",
    "wisconsin": "wi",
    "wyoming": "wy",
}
US_REGION_COMPONENT_ALIASES = {
    **US_STATE_ALIASES,
    **{abbreviation: abbreviation for abbreviation in US_STATE_ALIASES.values()},
}
US_COUNTRY_COMPONENT_ALIASES = {
    "usa": "us",
    "us": "us",
    "u s": "us",
    "united states": "us",
    "united states of america": "us",
}


def normalize_company_name(company_name: str) -> str:
    """Normalize company names for case-insensitive Supabase matching."""
    cleaned = re.sub(r"\s+", " ", company_name.strip())
    return cleaned.lower()


def _normalize_identity_text(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = cleaned.replace("&", " and ")
    cleaned = YEAR_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_job_title(title: str) -> str:
    """Normalize role titles for cross-source duplicate detection."""
    normalized = _normalize_identity_text(title)
    ignored_words = JOB_TITLE_STOP_WORDS | SEASON_IDENTITY_WORDS
    words = [word for word in normalized.split() if word not in ignored_words]
    return " ".join(words)


def _location_components(location: str) -> list[str]:
    return [
        normalized
        for component in re.split(r"[,;/\n]+", location)
        if (normalized := _normalize_identity_text(component))
    ]


def _normalize_location_v1(location: str) -> str:
    """Original location identity format, retained for posted-history matching."""
    normalized = _normalize_identity_text(location)
    if normalized in LOCATION_EXACT_ALIASES:
        return LOCATION_EXACT_ALIASES[normalized]

    components = _location_components(location)
    if len(components) <= 1:
        return (
            US_COUNTRY_COMPONENT_ALIASES.get(normalized)
            or US_REGION_COMPONENT_ALIASES.get(normalized)
            or normalized
        )

    country = US_COUNTRY_COMPONENT_ALIASES.get(components[-1])
    if country:
        components = components[:-1]

    region = US_REGION_COMPONENT_ALIASES.get(components[-1])
    if region:
        components[-1] = region

    if country:
        components.append(country)

    return " ".join(components)


def normalize_location(location: str) -> str:
    """Canonicalize equivalent US locations without merging distinct places."""
    normalized = _normalize_identity_text(location.replace(".", ""))
    remote_country = re.fullmatch(r"remote(?: in)? (.+)|(.+) remote", normalized)
    if remote_country:
        country = remote_country.group(1) or remote_country.group(2)
        if country in US_COUNTRY_COMPONENT_ALIASES:
            return "remote us"

    components = _location_components(location)
    if len(components) > 1 and (
        components[-1] in US_COUNTRY_COMPONENT_ALIASES or components[-1] == "u s a"
    ):
        without_country = _normalize_location_v1(",".join(components[:-1]))
        if without_country.split()[-1] in US_REGION_COMPONENT_ALIASES:
            return without_country
    return _normalize_location_v1(location)


def is_us_location(location: str) -> bool:
    """Recognize explicit US locations, not arbitrary cities or bare Remote."""
    # Work arrangement is not country evidence. Keep any geographic qualifier.
    location = re.sub(
        r"\b(?:remote|hybrid|on[ -]?site|in[ -]person)\b",
        "",
        location,
        flags=re.IGNORECASE,
    )
    location = re.sub(r"^\s*in\s+", "", location, flags=re.IGNORECASE)
    location = location.replace(".", "").strip(" ,()-")
    components = _location_components(location)
    if not components:
        return False

    if components[-1] in US_COUNTRY_COMPONENT_ALIASES:
        # Country alone, city/state + country, or city + state + country.
        return len(components) <= 2 or (
            len(components) == 3
            and components[-2] in US_REGION_COMPONENT_ALIASES
        )

    if len(components) == 2:
        return components[-1] in US_REGION_COMPONENT_ALIASES

    if len(components) == 1:
        name = components[0]
        # Georgia alone could mean the country; bare state codes are ambiguous.
        return name in (US_STATE_ALIASES.keys() - {"georgia"}) or name in {
            "nyc", "new york city", "sf", "south sf", "la",
        }
    return False


def locations_are_us_only(locations: list[str]) -> bool:
    """Fail closed for missing, foreign, mixed-country, or unknown locations."""
    return bool(locations) and all(
        is_us_location(part)
        for location in locations
        for part in re.split(r"[;/\n]+", location)
    )


def infer_job_year(title: str, terms: list[str] | None = None) -> str:
    """Return the title year, falling back to source terms when needed."""
    title_years = set(YEAR_RE.findall(title))
    fallback_years = set(YEAR_RE.findall(" ".join(terms or [])))
    return ",".join(sorted(title_years or fallback_years))


def _location_key(locations: list[str] | None, normalizer=normalize_location) -> str:
    normalized_locations = {
        normalized
        for location in locations or []
        if (normalized := normalizer(location))
    }
    return ",".join(sorted(normalized_locations))


def detect_seasons(title: str) -> list[str]:
    """Return seasons explicitly mentioned in the job title."""
    return [season for season in SEASONS if SEASON_PATTERNS[season].search(title)]


def build_job_id(
    company_name: str,
    title: str,
    locations: list[str] | None = None,
    terms: list[str] | None = None,
    *,
    location_normalizer=normalize_location,
) -> str:
    """Build a stable cross-source ID from canonical job identity fields."""
    identity = "|".join(
        [
            _normalize_identity_text(company_name),
            normalize_job_title(title),
            _location_key(locations, location_normalizer),
            infer_job_year(title, terms),
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def build_legacy_job_ids(
    company_name: str, title: str, locations: list[str], terms: list[str] | None = None
) -> set[str]:
    """Match v1 raw locations and its common explicit-US country variant."""
    def with_country(location: str) -> str:
        normalized = normalize_location(location)
        if normalized and normalized.split()[-1] in US_REGION_COMPONENT_ALIASES:
            return f"{normalized} us"
        return normalized

    return {
        build_job_id(
            company_name, title, locations, terms, location_normalizer=normalizer
        )
        for normalizer in (_normalize_location_v1, with_country)
    }


def _unique_known_seasons(seasons: list[str]) -> list[str]:
    return [season for season in SEASONS if season in seasons]


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
    job_year: str = ""
    season_tags: list[str] = Field(default_factory=list)
    source: str = ""
    legacy_ids: set[str] = Field(default_factory=set)
    source_urls: set[str] = Field(default_factory=set)

    @property
    def company_key(self) -> str:
        """Normalized company name for allow-list matching."""
        return normalize_company_name(self.company_name)

    @property
    def seasons(self) -> list[str]:
        """Seasons explicitly present in the title."""
        return _unique_known_seasons(self.season_tags) or detect_seasons(self.title)

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
        """Require a URL, a season, and confirmed US-only locations."""
        return bool(self.url and self.seasons and locations_are_us_only(self.locations))


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
        for listing in listings:
            if listing.id == internship.id:
                listing.legacy_ids.update(internship.legacy_ids)
                listing.source_urls.update(internship.source_urls | {internship.url})
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
