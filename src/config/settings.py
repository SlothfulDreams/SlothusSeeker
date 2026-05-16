"""Application settings loaded from environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

JOBRIGHT_README_URL = (
    "https://raw.githubusercontent.com/jobright-ai/"
    "2026-Software-Engineer-Internship/master/README.md"
)
SIMPLIFY_SUMMER_README_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/"
    "Summer2026-Internships/dev/README.md"
)
SIMPLIFY_OFF_SEASON_README_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/"
    "Summer2026-Internships/dev/README-Off-Season.md"
)


def _get_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} environment variable is required")
    return value


def _get_int(name: str, default: int, minimum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc

    if minimum is not None:
        return max(minimum, value)
    return value


def _get_float(name: str, default: float, minimum: float | None = None) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc

    if minimum is not None:
        return max(minimum, value)
    return value


def _get_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


# Discord Configuration
DISCORD_BOT_TOKEN = _get_required("DISCORD_BOT_TOKEN")

# GitHub Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Optional
GITHUB_REPO_URL = os.getenv("GITHUB_REPO_URL", JOBRIGHT_README_URL)
SIMPLIFY_SUMMER_REPO_URL = os.getenv(
    "SIMPLIFY_SUMMER_REPO_URL",
    SIMPLIFY_SUMMER_README_URL,
)
SIMPLIFY_OFF_SEASON_REPO_URL = os.getenv(
    "SIMPLIFY_OFF_SEASON_REPO_URL",
    SIMPLIFY_OFF_SEASON_README_URL,
)

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Scraping Configuration
SCRAPE_INTERVAL_MINUTES = _get_int("SCRAPE_INTERVAL_MINUTES", 15, minimum=1)
DEFAULT_SCRAPE_DAYS_BACK = _get_int("DEFAULT_SCRAPE_DAYS_BACK", 3, minimum=1)
POST_THROTTLE_SECONDS = _get_float("POST_THROTTLE_SECONDS", 1.0, minimum=0.0)

# Display Configuration
COMPANIES_PER_PAGE = _get_int("COMPANIES_PER_PAGE", 10, minimum=1)

# Discord Command Registration
SYNC_COMMANDS_ON_START = _get_bool("SYNC_COMMANDS_ON_START")

# File paths
BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_FILE = BASE_DIR / "config.json"
