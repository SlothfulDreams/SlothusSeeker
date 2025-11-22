"""Background tasks for periodic scraping."""

import asyncio
from typing import Optional

from discord.ext import commands, tasks

from src.bot.embeds import create_internship_embed
from src.config.config_manager import ConfigManager
from src.scraper.github_client import GitHubClient
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


async def scrape_and_post(bot: commands.Bot, config_manager: ConfigManager):
    """Scrape internships and post new ones to configured channels.

    Args:
        bot: Discord bot instance
        config_manager: Configuration manager instance
    """
    logger.info("Starting scrape...")

    try:
        # Initialize GitHub client
        github_client = GitHubClient()

        # Get last scrape data and start timestamp
        last_scrape = config_manager.get_last_scrape()
        start_timestamp = config_manager.get_scrape_start_timestamp()

        if start_timestamp:
            from datetime import datetime

            date_str = datetime.fromtimestamp(start_timestamp).strftime("%Y-%m-%d")
            logger.info(f"Filtering internships posted after {date_str}")

        # Fetch new listings
        new_listings, all_listings = await github_client.get_new_listings(
            last_scrape, start_timestamp
        )

        logger.info(f"Found {len(new_listings.summer)} new summer internships")
        logger.info(f"Found {len(new_listings.offseason)} new off-season internships")

        # Post summer internships
        summer_channels = config_manager.get_all_channels("summer")
        for channel_id in summer_channels:
            channel = bot.get_channel(channel_id)
            if channel:
                for internship in new_listings.summer:
                    embed = create_internship_embed(internship)
                    try:
                        await channel.send(embed=embed)
                        await asyncio.sleep(1)  # Rate limit prevention
                    except Exception as e:
                        logger.error(
                            f"Error posting to channel {channel_id}: {e}", exc_info=True
                        )

        # Post off-season internships
        offseason_channels = config_manager.get_all_channels("offseason")
        for channel_id in offseason_channels:
            channel = bot.get_channel(channel_id)
            if channel:
                for internship in new_listings.offseason:
                    embed = create_internship_embed(internship)
                    try:
                        await channel.send(embed=embed)
                        await asyncio.sleep(1)  # Rate limit prevention
                    except Exception as e:
                        print(f"[Scraper] Error posting to channel {channel_id}: {e}")

        # Update last scrape tracking
        await config_manager.update_last_scrape(
            summer_ids=all_listings.get_all_ids("summer"),
            offseason_ids=all_listings.get_all_ids("offseason"),
        )

        logger.info("Scrape completed successfully")

    except Exception as e:
        logger.error(f"Error during scrape: {e}", exc_info=True)
        raise


async def scrape_and_post_with_stats(
    bot: commands.Bot, config_manager: ConfigManager
) -> dict:
    """Scrape internships and post new ones with statistics tracking.

    Args:
        bot: Discord bot instance
        config_manager: Configuration manager instance

    Returns:
        Dictionary with statistics: summer_posted, offseason_posted, total_new, errors
    """
    logger.info("Starting scrape with stats tracking...")

    stats = {"summer_posted": 0, "offseason_posted": 0, "total_new": 0, "errors": 0}

    try:
        # Initialize GitHub client
        github_client = GitHubClient()

        # Get last scrape data and start timestamp
        last_scrape = config_manager.get_last_scrape()
        start_timestamp = config_manager.get_scrape_start_timestamp()

        if start_timestamp:
            from datetime import datetime

            date_str = datetime.fromtimestamp(start_timestamp).strftime("%Y-%m-%d")
            logger.info(f"Filtering internships posted after {date_str}")

        # Fetch new listings
        new_listings, all_listings = await github_client.get_new_listings(
            last_scrape, start_timestamp
        )

        stats["total_new"] = len(new_listings.summer) + len(new_listings.offseason)

        logger.info(f"Found {len(new_listings.summer)} new summer internships")
        logger.info(f"Found {len(new_listings.offseason)} new off-season internships")

        # Post summer internships
        summer_channels = config_manager.get_all_channels("summer")
        for channel_id in summer_channels:
            channel = bot.get_channel(channel_id)
            if channel:
                for internship in new_listings.summer:
                    embed = create_internship_embed(internship)
                    try:
                        await channel.send(embed=embed)
                        stats["summer_posted"] += 1
                        await asyncio.sleep(1)  # Rate limit prevention
                    except Exception as e:
                        stats["errors"] += 1
                        logger.error(
                            f"Error posting to channel {channel_id}: {e}", exc_info=True
                        )

        # Post off-season internships
        offseason_channels = config_manager.get_all_channels("offseason")
        for channel_id in offseason_channels:
            channel = bot.get_channel(channel_id)
            if channel:
                for internship in new_listings.offseason:
                    embed = create_internship_embed(internship)
                    try:
                        await channel.send(embed=embed)
                        stats["offseason_posted"] += 1
                        await asyncio.sleep(1)  # Rate limit prevention
                    except Exception as e:
                        stats["errors"] += 1
                        logger.error(
                            f"Error posting to channel {channel_id}: {e}", exc_info=True
                        )

        # Update last scrape tracking
        await config_manager.update_last_scrape(
            summer_ids=all_listings.get_all_ids("summer"),
            offseason_ids=all_listings.get_all_ids("offseason"),
        )

        logger.info(
            f"Scrape completed: {stats['summer_posted']} summer, {stats['offseason_posted']} offseason posted"
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
        # Check if any channels are configured before scraping
        summer_channels = self.config_manager.get_all_channels("summer")
        offseason_channels = self.config_manager.get_all_channels("offseason")

        if not summer_channels and not offseason_channels:
            logger.info("No channels configured, skipping scheduled scrape")
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
