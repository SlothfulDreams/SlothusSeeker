"""Custom exceptions for the scraper module."""


class ScraperError(Exception):
    """Base exception for all scraper-related errors."""


class FetchError(ScraperError):
    """Failed to fetch data from GitHub."""


class ParseError(ScraperError):
    """Failed to parse listing data."""


class RateLimitError(ScraperError):
    """GitHub API rate limit exceeded."""


class NetworkError(ScraperError):
    """Network connectivity issue."""
