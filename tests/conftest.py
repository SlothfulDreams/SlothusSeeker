"""Pytest configuration and fixtures."""
import os
import pytest

# Set environment variables BEFORE any imports
# This must happen at module level to work before settings.py is imported
os.environ["DISCORD_BOT_TOKEN"] = "test_token_123456789"
os.environ["GITHUB_TOKEN"] = ""  # Optional, can be empty
os.environ["SCRAPE_INTERVAL_HOURS"] = "6"
os.environ["GITHUB_REPO_URL"] = "https://test.com/listings.json"
