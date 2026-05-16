"""Managers for Supabase-backed bot configuration and local runtime settings."""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.config.settings import (
    CONFIG_FILE,
    DEFAULT_SCRAPE_DAYS_BACK,
    SCRAPE_INTERVAL_MINUTES,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
)
from src.scraper.data_models import Internship, SEASONS, normalize_company_name

SupabaseRow = dict[str, Any]


def _posted_job_row(
    guild_id: str,
    season: str,
    channel_id: int,
    internship: Internship,
) -> SupabaseRow:
    return {
        "job_id": internship.id,
        "guild_id": str(guild_id),
        "season": season,
        "channel_id": str(channel_id),
        "company_name": internship.company_name,
        "title": internship.title,
        "url": internship.url,
        "job_year": internship.job_year,
        "date_posted_label": internship.date_posted_label,
    }


class ConfigManager:
    """Manages Supabase channel mappings, companies, posted jobs, and settings."""

    def __init__(self, supabase_client=None):
        self.config_file = CONFIG_FILE
        self.client = supabase_client or self._create_supabase_client()
        self._ensure_files_exist()

    def _create_supabase_client(self):
        """Create a Supabase client lazily so tests can inject fakes."""
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables are required"
            )

        try:
            from supabase import create_client
        except ImportError as exc:
            raise RuntimeError(
                "supabase is not installed. Run dependencies through uv before starting the bot."
            ) from exc

        return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    def _ensure_files_exist(self):
        """Create local runtime config file if it does not exist."""
        if not self.config_file.exists():
            self.config_file.write_text('{"global": {}}')

    async def _execute(self, query):
        """Execute a Supabase query without blocking the event loop."""
        response = await asyncio.to_thread(query.execute)
        return response.data

    # Supabase server/channel configuration methods
    async def get_guild_config(self, guild_id: int) -> SupabaseRow:
        """Get configuration for a specific guild."""
        data = await self._execute(
            self.client.table("discord_servers")
            .select("*")
            .eq("guild_id", str(guild_id))
            .maybe_single()
        )
        return data or {}

    async def set_channel(
        self,
        guild_id: int,
        server_name: str,
        channel_type: str,
        channel_id: int,
    ) -> None:
        """Set a season channel for a guild."""
        if channel_type not in SEASONS:
            raise ValueError(f"Unknown season channel type: {channel_type}")

        await self._upsert_guild_fields(
            guild_id=guild_id,
            server_name=server_name,
            fields={f"{channel_type}_channel_id": str(channel_id)},
        )

    async def set_sudo_channel(
        self, guild_id: int, server_name: str, channel_id: int
    ) -> None:
        """Set the sudo channel ID for a guild."""
        await self._upsert_guild_fields(
            guild_id=guild_id,
            server_name=server_name,
            fields={"sudo_id": str(channel_id)},
        )

    async def _upsert_guild_fields(
        self, guild_id: int, server_name: str, fields: dict[str, str]
    ) -> None:
        payload = {
            "guild_id": str(guild_id),
            "server_name": server_name,
            **fields,
        }
        await self._execute(
            self.client.table("discord_servers").upsert(
                payload,
                on_conflict="guild_id",
            )
        )

    async def get_channel_destinations(self, channel_type: str) -> list[SupabaseRow]:
        """Get configured guild/channel destinations for a specific season."""
        if channel_type not in SEASONS:
            raise ValueError(f"Unknown season channel type: {channel_type}")

        key = f"{channel_type}_channel_id"
        rows = await self._execute(
            self.client.table("discord_servers")
            .select(f"guild_id,{key}")
            .not_.is_(key, "null")
        )
        return [
            {"guild_id": str(row["guild_id"]), "channel_id": int(row[key])}
            for row in rows or []
            if row.get("guild_id") and row.get(key)
        ]

    async def has_any_configured_channel(self) -> bool:
        """Return whether at least one server has any season channel configured."""
        rows = await self._execute(
            self.client.table("discord_servers").select(
                "spring_channel_id,summer_channel_id,fall_channel_id"
            )
        )
        return any(
            row.get(f"{season}_channel_id")
            for row in rows or []
            for season in SEASONS
        )

    # Supabase company allow-list methods
    async def add_company(self, company_name: str) -> SupabaseRow:
        """Insert a lowercase unique company name into Supabase."""
        normalized = normalize_company_name(company_name)
        rows = await self._execute(
            self.client.table("companies")
            .upsert({"company_name": normalized}, on_conflict="company_name")
            .select("id,company_name")
        )
        return (rows or [{}])[0]

    async def list_companies(self) -> list[SupabaseRow]:
        """List companies ordered by ID."""
        rows = await self._execute(
            self.client.table("companies").select("id,company_name").order("id")
        )
        return rows or []

    async def delete_company(self, company_id: int) -> bool:
        """Delete a company by ID."""
        rows = await self._execute(
            self.client.table("companies")
            .delete()
            .eq("id", company_id)
            .select("id")
        )
        return bool(rows)

    async def get_company_names(self) -> set[str]:
        """Return normalized allow-listed company names."""
        rows = await self._execute(
            self.client.table("companies").select("company_name")
        )
        return {
            normalize_company_name(row["company_name"])
            for row in rows or []
            if row.get("company_name")
        }

    # Supabase posted job tracking methods
    async def get_posted_job_ids(self, guild_id: str, season: str) -> set[str]:
        """Return job IDs already posted to a guild for a season."""
        rows = await self._execute(
            self.client.table("posted_jobs")
            .select("job_id")
            .eq("guild_id", str(guild_id))
            .eq("season", season)
        )
        return {row["job_id"] for row in rows or [] if row.get("job_id")}

    async def record_posted_jobs(
        self,
        guild_id: str,
        season: str,
        channel_id: int,
        internships: list[Internship],
    ) -> None:
        """Record successfully posted jobs in Supabase."""
        if not internships:
            return

        rows = [
            _posted_job_row(guild_id, season, channel_id, internship)
            for internship in internships
        ]
        await self._execute(
            self.client.table("posted_jobs").upsert(
                rows,
                on_conflict="job_id,guild_id,season",
            )
        )

    # Local global settings methods
    def get_config(self) -> dict[str, Any]:
        """Load local global configuration."""
        return json.loads(self.config_file.read_text())

    def _atomic_write(self, file_path: Path, data: dict[str, Any]) -> None:
        """Write data to a file atomically using temp file + rename."""
        temp_file = file_path.with_suffix(".tmp")
        temp_file.write_text(json.dumps(data, indent=2))
        temp_file.replace(file_path)

    def _get_global_config(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Load config and ensure the global settings object exists."""
        config = self.get_config()
        global_config = config.setdefault("global", {})
        return config, global_config

    def get_scrape_interval_minutes(self) -> int:
        """Get the current scrape interval in minutes."""
        _, global_config = self._get_global_config()
        if "scrape_interval_minutes" in global_config:
            return global_config["scrape_interval_minutes"]
        if "scrape_interval_hours" in global_config:
            return max(1, int(global_config["scrape_interval_hours"] * 60))
        return SCRAPE_INTERVAL_MINUTES

    def set_scrape_interval_minutes(self, minutes: int) -> None:
        """Set the scrape interval in minutes."""
        if minutes <= 0:
            raise ValueError("Scrape interval must be greater than 0")

        config, global_config = self._get_global_config()
        global_config.pop("scrape_interval_hours", None)
        global_config["scrape_interval_minutes"] = minutes
        self._atomic_write(self.config_file, config)

    def get_scrape_start_timestamp(self) -> int:
        """Get the start timestamp for filtering internships."""
        _, global_config = self._get_global_config()

        if "scrape_start_timestamp" in global_config:
            return global_config["scrape_start_timestamp"]

        default_start = datetime.now() - timedelta(days=DEFAULT_SCRAPE_DAYS_BACK)
        return int(default_start.timestamp())

    def set_scrape_start_timestamp(self, timestamp: int) -> None:
        """Set the start timestamp for filtering internships."""
        if timestamp <= 0:
            raise ValueError("Timestamp must be greater than 0")

        config, global_config = self._get_global_config()
        global_config["scrape_start_timestamp"] = timestamp
        self._atomic_write(self.config_file, config)
