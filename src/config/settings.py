"""Application settings loaded from environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Discord Configuration
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not DISCORD_BOT_TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is required")

# GitHub Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Optional
GITHUB_REPO_URL = os.getenv(
    "GITHUB_REPO_URL",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json",
)

# Scraping Configuration
SCRAPE_INTERVAL_HOURS = int(os.getenv("SCRAPE_INTERVAL_HOURS", "6"))

# File paths
BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_FILE = BASE_DIR / "config.json"
LAST_SCRAPE_FILE = BASE_DIR / "last_scrape.json"
