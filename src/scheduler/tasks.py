"""Background tasks for periodic scraping."""

import asyncio
from dataclasses import dataclass
from typing import Iterable
from typing import Optional

import discord
from discord.ext import commands, tasks

from src.bot.embeds import create_internship_embed
from src.config.config_manager import ConfigManager
from src.scraper.github_client import GitHubClient
from src.scraper.data_models import ScrapedData
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

POST_THROTTLE_SECONDS = 1.0


@dataclass(slots=True)
class ScrapeStats:
    """Summary of a scrape/post cycle."""

    summer_posted: int = 0
    offseason_posted: int = 0
    total_new: int = 0
    errors: int = 0


async def _post_internships(
    bot: commands.Bot, channel_type: str, channels: list[int], internships: Iterable
) -> tuple[int, int]:
    """Post internship embeds to configured channels.

    Args:
        bot: Discord bot instance
        channel_type: Either 'summer' or 'offseason'
        channels: List of channel IDs to post to
        internships: Iterable of internship models to post

    Returns:
        Tuple with (posted_count, error_count)
    """
    posted_count = 0
    error_count = 0
    internships = tuple(internships)

    for channel_id in channels:
        channel = bot.get_channel(channel_id)
        if not channel:
            logger.warning(f"Configured {channel_type} channel not found: {channel_id}")
            continue
        if not isinstance(channel, discord.abc.Messageable):
            logger.warning(
                f"Configured {channel_type} channel is not messageable: {channel_id}"
            )
            continue

        for internship in internships:
            embed = create_internship_embed(internship)
            try:
                await channel.send(embed=embed)
                posted_count += 1
                await asyncio.sleep(POST_THROTTLE_SECONDS)
            except Exception as e:
                error_count += 1
                logger.error(
                    f"Error posting {channel_type} internship to channel {channel_id}: {e}",
                    exc_info=True,
                )

    return posted_count, error_count


def _log_start_timestamp(start_timestamp: int | None) -> None:
    """Log the active date filter."""
    if not start_timestamp:
        return

    from datetime import datetime

    date_str = datetime.fromtimestamp(start_timestamp).strftime("%Y-%m-%d")
    logger.info(f"Filtering internships posted after {date_str}")


async def _fetch_new_listings(
    config_manager: ConfigManager,
) -> tuple[ScrapedData, ScrapedData]:
    """Fetch listings and apply the configured dedupe/date filters."""
    last_scrape = config_manager.get_last_scrape()
    start_timestamp = config_manager.get_scrape_start_timestamp()
    _log_start_timestamp(start_timestamp)

    async with GitHubClient() as github_client:
        return await github_client.get_new_listings(last_scrape, start_timestamp)


async def scrape_and_post(
    bot: commands.Bot, config_manager: ConfigManager
) -> ScrapeStats:
    """Scrape internships and post new ones to configured channels.

    Args:
        bot: Discord bot instance
        config_manager: Configuration manager instance

    Returns:
        Scrape/post statistics
    """
    logger.info("Starting scrape...")
    stats = ScrapeStats()

    try:
        new_listings, all_listings = await _fetch_new_listings(config_manager)

        stats.total_new = len(new_listings.summer) + len(new_listings.offseason)

        logger.info(f"Found {len(new_listings.summer)} new summer internships")
        logger.info(f"Found {len(new_listings.offseason)} new off-season internships")

        # Post summer internships
        summer_channels = config_manager.get_all_channels("summer")
        posted, errors = await _post_internships(
            bot, "summer", summer_channels, new_listings.summer
        )
        stats.summer_posted += posted
        stats.errors += errors

        # Post off-season internships
        offseason_channels = config_manager.get_all_channels("offseason")
        posted, errors = await _post_internships(
            bot, "offseason", offseason_channels, new_listings.offseason
        )
        stats.offseason_posted += posted
        stats.errors += errors

        # Update last scrape tracking
        config_manager.update_last_scrape(
            summer_ids=all_listings.get_all_ids("summer"),
            offseason_ids=all_listings.get_all_ids("offseason"),
        )

        logger.info(
            f"Scrape completed: {stats.summer_posted} summer, {stats.offseason_posted} offseason posted"
        )

    except Exception as e:
        logger.error(f"Error during scrape: {e}", exc_info=True)
        raise

    return stats


class ScraperTasks(commands.Cog):
    """Cog for background scraping tasks."""

    def __init__(self, bot: commands.Bot, config_manager: ConfigManager):
        self.bot = bot
        self.config_manager = config_manager
        # Get initial interval from config
        interval_hours = self.config_manager.get_scrape_interval()
        logger.info(f"Initializing scheduler with interval: {interval_hours} hours")
        # Set initial interval and start the task
        self.scrape_task.change_interval(hours=interval_hours)
        self.scrape_task.start()

    @tasks.loop(hours=1.0)  # Default interval, will be changed in __init__
    async def scrape_task(self):
        """Periodic scraping task."""
        # Check if BOTH channel types are configured before scraping
        summer_channels = self.config_manager.get_all_channels("summer")
        offseason_channels = self.config_manager.get_all_channels("offseason")

        if not summer_channels or not offseason_channels:
            logger.info(
                "Both summer and offseason channels must be configured. Skipping scheduled scrape"
            )
            return

        await scrape_and_post(self.bot, self.config_manager)

    @scrape_task.before_loop
    async def before_scrape_task(self):
        """Wait for bot to be ready before starting tasks."""
        await self.bot.wait_until_ready()
        current_interval = self.scrape_task.hours
        logger.info(f"Starting periodic scraping (every {current_interval} hours)")

    def cog_unload(self):
        """Stop tasks when cog is unloaded."""
        self.scrape_task.cancel()

    async def restart_scraper(self, new_interval_hours: float):
        """Restart the scraper task with a new interval.

        Args:
            new_interval_hours: New interval in hours
        """
        logger.info(
            f"Restarting scheduler with new interval: {new_interval_hours} hours"
        )

        # Change interval and restart the task
        self.scrape_task.change_interval(hours=new_interval_hours)
        self.scrape_task.restart()


def get_scraper_cog(bot: commands.Bot) -> Optional[ScraperTasks]:
    """Get the scraper cog instance from the bot.

    Args:
        bot: Discord bot instance

    Returns:
        ScraperTasks cog instance or None if not found
    """
    return bot.get_cog("ScraperTasks")


async def setup(bot: commands.Bot, config_manager: ConfigManager):
    """Add the cog to the bot."""
    await bot.add_cog(ScraperTasks(bot, config_manager))
