"""Background tasks for periodic scraping."""

import asyncio
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
from src.scraper.diagnostics import ScrapeStats
from src.scraper.github_client import GitHubClient
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

EVERYONE_MENTION = "@everyone"
EVERYONE_ALLOWED_MENTIONS = discord.AllowedMentions(everyone=True)


class DeliveryRecordingError(RuntimeError):
    """Discord accepted a message but its deduplication checkpoint failed."""


async def _post_internships(
    bot: commands.Bot,
    channel_type: str,
    channel_id: int,
    internships: Iterable[Internship],
    *,
    config_manager: ConfigManager,
    guild_id: str,
    stats: ScrapeStats | None = None,
) -> tuple[list[Internship], int]:
    """Post internship embeds to one configured channel.

    Args:
        bot: Discord bot instance
        channel_type: One of the configured seasons
        channel_id: Channel ID to post to
        internships: Iterable of internship models to post
        config_manager: Persists each successful delivery
        guild_id: Guild owning the destination's posting history

    Returns:
        Tuple with successfully posted internships and error count
    """
    stats = stats if stats is not None else ScrapeStats()
    posted_internships = []
    error_count = 0
    internships = tuple(internships)
    if not internships:
        return posted_internships, error_count

    channel = bot.get_channel(channel_id)
    if not channel:
        logger.warning("Configured %s channel not found: %s", channel_type, channel_id)
        stats.errors += 1
        return posted_internships, 1
    if not isinstance(channel, discord.abc.Messageable):
        logger.warning(
            "Configured %s channel is not messageable: %s",
            channel_type,
            channel_id,
        )
        stats.errors += 1
        return posted_internships, 1

    for internship in internships:
        embed = create_internship_embed(internship)
        try:
            await channel.send(
                content=EVERYONE_MENTION,
                embed=embed,
                allowed_mentions=EVERYONE_ALLOWED_MENTIONS,
            )
        except Exception as e:
            error_count += 1
            stats.errors += 1
            logger.error(
                "Error posting %s internship to channel %s: %s",
                channel_type,
                channel_id,
                e,
                exc_info=True,
            )
            continue

        stats.posted_by_season[channel_type] += 1
        # Checkpoint before throttling or sending anything else. A write failure
        # must not be treated as a failed send and followed by more untracked posts.
        try:
            await config_manager.record_posted_jobs(
                guild_id, channel_type, channel_id, [internship]
            )
        except Exception as exc:
            stats.unrecorded += 1
            raise DeliveryRecordingError(
                f"Sent job {internship.id} to channel {channel_id}, but could not "
                "record the delivery. Remaining batch stopped."
            ) from exc
        stats.recorded += 1
        posted_internships.append(internship)
        await asyncio.sleep(POST_THROTTLE_SECONDS)

    return posted_internships, error_count


def _log_start_timestamp(start_timestamp: int | None) -> None:
    """Log the active date filter."""
    if not start_timestamp:
        return

    date_str = datetime.fromtimestamp(start_timestamp).strftime("%Y-%m-%d")
    logger.info("Filtering internships posted after %s", date_str)


async def _fetch_allowlisted_listings(
    config_manager: ConfigManager, stats: ScrapeStats,
) -> ScrapedData:
    """Fetch listings and apply configured company/date filters."""
    start_timestamp = config_manager.get_scrape_start_timestamp()
    company_names = await config_manager.get_company_names()
    _log_start_timestamp(start_timestamp)

    if not company_names:
        stats.outcome = "skipped"
        stats.note = "No companies configured. Use /companies add first."
        logger.info(stats.note)
        return ScrapedData()

    async with GitHubClient() as github_client:
        return await github_client.get_allowlisted_listings(
            company_names,
            start_timestamp,
            diagnostics=stats.sources,
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
    monitor = bot.scrape_monitor
    stats = monitor.begin()

    try:
        if not await config_manager.has_any_configured_channel():
            stats.outcome = "skipped"
            stats.note = "No season channels configured. Use /config set-season-channel first."
            return stats

        allowlisted_listings = await _fetch_allowlisted_listings(config_manager, stats)
        if stats.outcome == "skipped":
            return stats
        new_job_keys: set[tuple[str, str]] = set()

        for season in SEASONS:
            listings = getattr(allowlisted_listings, season)
            destinations = await config_manager.get_channel_destinations(season)

            if not destinations:
                stats.unconfigured += len(listings)
                logger.info(
                    "No %s channel configured. Leaving matching jobs eligible for later.",
                    SEASON_DISPLAY_NAMES[season].lower(),
                )
                continue

            for destination in destinations:
                posted_history = await config_manager.get_posted_history(
                    destination["guild_id"],
                    season,
                )
                pending_listings = [
                    internship
                    for internship in listings
                    if not posted_history.contains(internship)
                ]
                stats.already_posted += len(listings) - len(pending_listings)
                for internship in pending_listings:
                    new_job_keys.add((season, internship.id))
                stats.total_new = len(new_job_keys)

                logger.info(
                    "Found %s new %s internships for guild %s",
                    len(pending_listings),
                    SEASON_DISPLAY_NAMES[season].lower(),
                    destination["guild_id"],
                )

                await _post_internships(
                    bot,
                    season,
                    destination["channel_id"],
                    pending_listings,
                    config_manager=config_manager,
                    guild_id=destination["guild_id"],
                    stats=stats,
                )

        stats.outcome = "partial" if stats.errors else "success"

        logger.info(
            "Scrape completed: %s total posts across %s new listings",
            stats.total_posted,
            stats.total_new,
        )

    except asyncio.CancelledError:
        stats.outcome = "interrupted"
        stats.note = "Scrape interrupted; completed delivery checkpoints are retained."
        raise
    except Exception as e:
        stats.outcome = "failed"
        stats.errors += 1
        stats.note = (
            "A message was sent but its delivery could not be recorded. Batch stopped; check logs."
            if isinstance(e, DeliveryRecordingError)
            else "Scrape failed. Check logs for details."
        )
        logger.error("Error during scrape: %s", e, exc_info=True)
        raise
    finally:
        monitor.finish(stats)

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
