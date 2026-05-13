"""Background tasks for periodic scraping."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

import discord
from discord.ext import commands, tasks

from src.bot.embeds import create_internship_embed
from src.config.config_manager import ConfigManager
from src.config.settings import POST_THROTTLE_SECONDS
from src.scraper.data_models import (
    SEASON_DISPLAY_NAMES,
    SEASONS,
    Internship,
    ScrapedData,
)
from src.scraper.github_client import GitHubClient
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

EVERYONE_MENTION = "@everyone"
EVERYONE_ALLOWED_MENTIONS = discord.AllowedMentions(everyone=True)


@dataclass(slots=True)
class ScrapeStats:
    """Summary of a scrape/post cycle."""

    posted_by_season: dict[str, int] = field(
        default_factory=lambda: {season: 0 for season in SEASONS}
    )
    total_new: int = 0
    errors: int = 0

    @property
    def total_posted(self) -> int:
        return sum(self.posted_by_season.values())


async def _post_internships(
    bot: commands.Bot,
    channel_type: str,
    channel_id: int,
    internships: Iterable[Internship],
) -> tuple[list[Internship], int]:
    """Post internship embeds to one configured channel.

    Args:
        bot: Discord bot instance
        channel_type: One of the configured seasons
        channel_id: Channel ID to post to
        internships: Iterable of internship models to post

    Returns:
        Tuple with successfully posted internships and error count
    """
    posted_internships = []
    error_count = 0
    internships = tuple(internships)

    channel = bot.get_channel(channel_id)
    if not channel:
        logger.warning("Configured %s channel not found: %s", channel_type, channel_id)
        return posted_internships, error_count
    if not isinstance(channel, discord.abc.Messageable):
        logger.warning(
            "Configured %s channel is not messageable: %s",
            channel_type,
            channel_id,
        )
        return posted_internships, error_count

    for internship in internships:
        embed = create_internship_embed(internship)
        try:
            await channel.send(
                content=EVERYONE_MENTION,
                embed=embed,
                allowed_mentions=EVERYONE_ALLOWED_MENTIONS,
            )
            posted_internships.append(internship)
            await asyncio.sleep(POST_THROTTLE_SECONDS)
        except Exception as e:
            error_count += 1
            logger.error(
                "Error posting %s internship to channel %s: %s",
                channel_type,
                channel_id,
                e,
                exc_info=True,
            )

    return posted_internships, error_count


def _log_start_timestamp(start_timestamp: int | None) -> None:
    """Log the active date filter."""
    if not start_timestamp:
        return

    date_str = datetime.fromtimestamp(start_timestamp).strftime("%Y-%m-%d")
    logger.info("Filtering internships posted after %s", date_str)


async def _fetch_allowlisted_listings(
    config_manager: ConfigManager,
) -> ScrapedData:
    """Fetch listings and apply configured company/date filters."""
    start_timestamp = config_manager.get_scrape_start_timestamp()
    company_names = await config_manager.get_company_names()
    _log_start_timestamp(start_timestamp)

    if not company_names:
        logger.info("No companies configured. Skipping Jobright fetch.")
        return ScrapedData()

    async with GitHubClient() as github_client:
        return await github_client.get_allowlisted_listings(
            company_names,
            start_timestamp,
        )


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
        allowlisted_listings = await _fetch_allowlisted_listings(config_manager)
        new_job_keys: set[tuple[str, str]] = set()

        for season in SEASONS:
            listings = getattr(allowlisted_listings, season)
            destinations = await config_manager.get_channel_destinations(season)

            if not destinations:
                logger.info(
                    "No %s channel configured. Leaving matching jobs eligible for later.",
                    SEASON_DISPLAY_NAMES[season].lower(),
                )
                continue

            for destination in destinations:
                posted_ids = await config_manager.get_posted_job_ids(
                    destination["guild_id"],
                    season,
                )
                pending_listings = [
                    internship
                    for internship in listings
                    if internship.id not in posted_ids
                ]
                for internship in pending_listings:
                    new_job_keys.add((season, internship.id))

                logger.info(
                    "Found %s new %s internships for guild %s",
                    len(pending_listings),
                    SEASON_DISPLAY_NAMES[season].lower(),
                    destination["guild_id"],
                )

                posted_internships, errors = await _post_internships(
                    bot,
                    season,
                    destination["channel_id"],
                    pending_listings,
                )
                stats.posted_by_season[season] += len(posted_internships)
                stats.errors += errors
                if posted_internships:
                    await config_manager.record_posted_jobs(
                        destination["guild_id"],
                        season,
                        destination["channel_id"],
                        posted_internships,
                    )

        stats.total_new = len(new_job_keys)

        logger.info(
            "Scrape completed: %s total posts across %s new listings",
            stats.total_posted,
            stats.total_new,
        )

    except Exception as e:
        logger.error("Error during scrape: %s", e, exc_info=True)
        raise

    return stats


class ScraperTasks(commands.Cog):
    """Cog for background scraping tasks."""

    def __init__(self, bot: commands.Bot, config_manager: ConfigManager):
        self.bot = bot
        self.config_manager = config_manager
        interval_minutes = self.config_manager.get_scrape_interval_minutes()
        logger.info(
            "Initializing scheduler with interval: %s minutes",
            interval_minutes,
        )
        self.scrape_task.change_interval(minutes=interval_minutes)
        self.scrape_task.start()

    @tasks.loop(minutes=15.0)  # Default interval, will be changed in __init__
    async def scrape_task(self):
        """Periodic scraping task."""
        if not await self.config_manager.has_any_configured_channel():
            logger.info("No season channels configured. Skipping scheduled scrape")
            return

        await scrape_and_post(self.bot, self.config_manager)

    @scrape_task.before_loop
    async def before_scrape_task(self):
        """Wait for bot to be ready before starting tasks."""
        await self.bot.wait_until_ready()
        current_interval = self.scrape_task.minutes
        logger.info("Starting periodic scraping every %s minutes", current_interval)

    def cog_unload(self):
        """Stop tasks when cog is unloaded."""
        self.scrape_task.cancel()

    async def restart_scraper(self, new_interval_minutes: int):
        """Restart the scraper task with a new interval.

        Args:
            new_interval_minutes: New interval in minutes
        """
        logger.info(
            "Restarting scheduler with new interval: %s minutes",
            new_interval_minutes,
        )

        self.scrape_task.change_interval(minutes=new_interval_minutes)
        self.scrape_task.restart()


def get_scraper_cog(bot: commands.Bot) -> ScraperTasks | None:
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
