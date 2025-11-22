"""Tests for ConfigManager."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.config.config_manager import ConfigManager


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temporary config directory."""
    return tmp_path


@pytest.fixture
def config_manager(temp_config_dir, monkeypatch):
    """Create ConfigManager with temporary files."""
    config_file = temp_config_dir / "config.json"
    last_scrape_file = temp_config_dir / "last_scrape.json"

    # Monkey patch the file paths
    monkeypatch.setattr("src.config.config_manager.CONFIG_FILE", config_file)
    monkeypatch.setattr("src.config.config_manager.LAST_SCRAPE_FILE", last_scrape_file)

    return ConfigManager()


class TestConfigManagerInitialization:
    """Test ConfigManager initialization."""

    def test_creates_config_files(self, config_manager, temp_config_dir):
        """Test that config files are created on init."""
        config_file = temp_config_dir / "config.json"
        last_scrape_file = temp_config_dir / "last_scrape.json"

        assert config_file.exists()
        assert last_scrape_file.exists()

    def test_config_file_has_default_structure(self, config_manager):
        """Test that config.json has correct default structure."""
        config = config_manager.get_config()
        assert "global" in config

    def test_last_scrape_file_has_default_structure(self, config_manager):
        """Test that last_scrape.json has correct default structure."""
        last_scrape = config_manager.get_last_scrape()
        assert "summer" in last_scrape
        assert "offseason" in last_scrape
        assert isinstance(last_scrape["summer"], set)
        assert isinstance(last_scrape["offseason"], set)


class TestChannelConfiguration:
    """Test channel configuration methods."""

    def test_set_summer_channel(self, config_manager):
        """Test setting summer channel."""
        guild_id = 123456789
        channel_id = 987654321

        config_manager.set_channel(guild_id, "summer", channel_id)

        guild_config = config_manager.get_guild_config(guild_id)
        assert guild_config["summer_channel"] == channel_id

    def test_set_offseason_channel(self, config_manager):
        """Test setting offseason channel."""
        guild_id = 123456789
        channel_id = 111222333

        config_manager.set_channel(guild_id, "offseason", channel_id)

        guild_config = config_manager.get_guild_config(guild_id)
        assert guild_config["offseason_channel"] == channel_id

    def test_get_all_summer_channels(self, config_manager):
        """Test getting all summer channels."""
        config_manager.set_channel(111, "summer", 1001)
        config_manager.set_channel(222, "summer", 2002)
        config_manager.set_channel(333, "offseason", 3003)  # Different type

        summer_channels = config_manager.get_all_channels("summer")
        assert 1001 in summer_channels
        assert 2002 in summer_channels
        assert 3003 not in summer_channels

    def test_get_guild_config_nonexistent(self, config_manager):
        """Test getting config for guild that doesn't exist."""
        guild_config = config_manager.get_guild_config(999999)
        assert guild_config == {}


class TestScrapeInterval:
    """Test scrape interval methods."""

    def test_get_default_scrape_interval(self, config_manager):
        """Test getting default scrape interval."""
        interval = config_manager.get_scrape_interval()
        assert interval == 6.0  # Default from settings

    def test_set_scrape_interval(self, config_manager):
        """Test setting custom scrape interval."""
        config_manager.set_scrape_interval(3.5)
        interval = config_manager.get_scrape_interval()
        assert interval == 3.5

    def test_set_scrape_interval_invalid(self, config_manager):
        """Test setting invalid scrape interval raises error."""
        with pytest.raises(ValueError):
            config_manager.set_scrape_interval(0)

        with pytest.raises(ValueError):
            config_manager.set_scrape_interval(-1)


class TestStartDate:
    """Test start date/timestamp methods."""

    def test_get_default_start_timestamp(self, config_manager):
        """Test getting default start timestamp (1 days ago)."""
        timestamp = config_manager.get_scrape_start_timestamp()

        # Should be approximately 3 days ago
        three_days_ago = datetime.now() - timedelta(days=1)
        timestamp_date = datetime.fromtimestamp(timestamp)

        # Allow 1 minute tolerance for test execution time
        assert abs((timestamp_date - three_days_ago).total_seconds()) < 60

    def test_set_custom_start_timestamp(self, config_manager):
        """Test setting custom start timestamp."""
        custom_timestamp = int((datetime.now() - timedelta(days=7)).timestamp())
        config_manager.set_scrape_start_timestamp(custom_timestamp)

        timestamp = config_manager.get_scrape_start_timestamp()
        assert timestamp == custom_timestamp

    def test_set_start_timestamp_invalid(self, config_manager):
        """Test setting invalid start timestamp raises error."""
        with pytest.raises(ValueError):
            config_manager.set_scrape_start_timestamp(0)

        with pytest.raises(ValueError):
            config_manager.set_scrape_start_timestamp(-100)


class TestLastScrapeTracking:
    """Test last scrape tracking methods."""

    def test_update_last_scrape(self, config_manager):
        """Test updating last scrape tracking."""
        summer_ids = {"uuid1", "uuid2", "uuid3"}
        offseason_ids = {"uuid4", "uuid5"}

        config_manager.update_last_scrape(summer_ids, offseason_ids)

        last_scrape = config_manager.get_last_scrape()
        assert last_scrape["summer"] == summer_ids
        assert last_scrape["offseason"] == offseason_ids

    def test_last_scrape_persists(self, config_manager, temp_config_dir, monkeypatch):
        """Test that last scrape data persists across instances."""
        summer_ids = {"uuid1", "uuid2"}
        offseason_ids = {"uuid3"}

        config_manager.update_last_scrape(summer_ids, offseason_ids)

        # Create new instance (simulating restart)
        config_file = temp_config_dir / "config.json"
        last_scrape_file = temp_config_dir / "last_scrape.json"
        monkeypatch.setattr("src.config.config_manager.CONFIG_FILE", config_file)
        monkeypatch.setattr(
            "src.config.config_manager.LAST_SCRAPE_FILE", last_scrape_file
        )

        new_manager = ConfigManager()
        last_scrape = new_manager.get_last_scrape()

        assert last_scrape["summer"] == summer_ids
        assert last_scrape["offseason"] == offseason_ids
