"""Manager for bot configuration stored in JSON files."""
import json
from pathlib import Path
from typing import Dict, Optional, Set
from src.config.settings import CONFIG_FILE, LAST_SCRAPE_FILE, SCRAPE_INTERVAL_HOURS


class ConfigManager:
    """Manages channel mappings and scrape tracking."""

    def __init__(self):
        self.config_file = CONFIG_FILE
        self.last_scrape_file = LAST_SCRAPE_FILE
        self._ensure_files_exist()

    def _ensure_files_exist(self):
        """Create config files if they don't exist."""
        if not self.config_file.exists():
            self.config_file.write_text('{"global": {}}')
        if not self.last_scrape_file.exists():
            self.last_scrape_file.write_text('{"summer": [], "offseason": []}')

    # Channel Configuration Methods
    def get_config(self) -> Dict:
        """Load full configuration."""
        return json.loads(self.config_file.read_text())

    def get_guild_config(self, guild_id: int) -> Dict:
        """Get configuration for a specific guild."""
        config = self.get_config()
        return config.get(str(guild_id), {})

    def set_channel(self, guild_id: int, channel_type: str, channel_id: int):
        """Set a channel for a guild.

        Args:
            guild_id: Discord guild ID
            channel_type: Either 'summer' or 'offseason'
            channel_id: Discord channel ID
        """
        config = self.get_config()
        guild_key = str(guild_id)

        if guild_key not in config:
            config[guild_key] = {}

        config[guild_key][f"{channel_type}_channel"] = channel_id
        self.config_file.write_text(json.dumps(config, indent=2))

    def get_all_channels(self, channel_type: str) -> list[int]:
        """Get all configured channels of a specific type across all guilds.

        Args:
            channel_type: Either 'summer' or 'offseason'

        Returns:
            List of channel IDs
        """
        config = self.get_config()
        channels = []
        key = f"{channel_type}_channel"

        for guild_config in config.values():
            if key in guild_config:
                channels.append(guild_config[key])

        return channels

    # Last Scrape Tracking Methods
    def get_last_scrape(self) -> Dict[str, Set[str]]:
        """Get UUIDs from last scrape.

        Returns:
            Dict with 'summer' and 'offseason' keys containing sets of UUIDs
        """
        data = json.loads(self.last_scrape_file.read_text())
        return {
            "summer": set(data.get("summer", [])),
            "offseason": set(data.get("offseason", []))
        }

    def update_last_scrape(self, summer_ids: Set[str], offseason_ids: Set[str]):
        """Update last scrape tracking file.

        Args:
            summer_ids: Set of UUIDs for summer internships
            offseason_ids: Set of UUIDs for off-season internships
        """
        data = {
            "summer": list(summer_ids),
            "offseason": list(offseason_ids)
        }
        self.last_scrape_file.write_text(json.dumps(data, indent=2))

    # Scrape Interval Methods
    def get_scrape_interval(self) -> float:
        """Get the current scrape interval in hours.

        Returns:
            Scrape interval in hours (default from settings if not set)
        """
        config = self.get_config()
        global_config = config.get("global", {})
        return global_config.get("scrape_interval_hours", SCRAPE_INTERVAL_HOURS)

    def set_scrape_interval(self, hours: float):
        """Set the scrape interval in hours.

        Args:
            hours: Scrape interval in hours (must be > 0)
        """
        if hours <= 0:
            raise ValueError("Scrape interval must be greater than 0")

        config = self.get_config()
        if "global" not in config:
            config["global"] = {}

        config["global"]["scrape_interval_hours"] = hours
        self.config_file.write_text(json.dumps(config, indent=2))

    # Start Date Methods
    def get_scrape_start_timestamp(self) -> int:
        """Get the start timestamp for filtering internships.

        Returns:
            Unix timestamp (defaults to 3 days ago if not set)
        """
        config = self.get_config()
        global_config = config.get("global", {})

        # Check if user has set a custom start timestamp
        if "scrape_start_timestamp" in global_config:
            return global_config["scrape_start_timestamp"]

        # Default: 3 days ago
        from datetime import datetime, timedelta
        default_start = datetime.now() - timedelta(days=3)
        return int(default_start.timestamp())

    def set_scrape_start_timestamp(self, timestamp: int):
        """Set the start timestamp for filtering internships.

        Args:
            timestamp: Unix timestamp for filtering (must be > 0)
        """
        if timestamp <= 0:
            raise ValueError("Timestamp must be greater than 0")

        config = self.get_config()
        if "global" not in config:
            config["global"] = {}

        config["global"]["scrape_start_timestamp"] = timestamp
        self.config_file.write_text(json.dumps(config, indent=2))
