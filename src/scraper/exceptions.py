"""Custom exceptions for the scraper module."""


class ScraperError(Exception):
    """Base exception for all scraper-related errors."""

    pass


class FetchError(ScraperError):
    """Failed to fetch data from GitHub."""

    pass


class ParseError(ScraperError):
    """Failed to parse listing data."""

    pass


class RateLimitError(ScraperError):
    """GitHub API rate limit exceeded."""

    pass


class NetworkError(ScraperError):
    """Network connectivity issue."""

    pass
