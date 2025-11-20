"""Background tasks for periodic scraping."""
import asyncio
from typing import Optional
from discord.ext import commands, tasks
from src.scraper.github_client import GitHubClient
from src.config.config_manager import ConfigManager
from src.bot.embeds import create_internship_embed


async def scrape_and_post(bot: commands.Bot, config_manager: ConfigManager):
    """Scrape internships and post new ones to configured channels.

    Args:
        bot: Discord bot instance
        config_manager: Configuration manager instance
    """
    print("[Scraper] Starting scrape...")

    try:
        # Initialize GitHub client
        github_client = GitHubClient()

        # Get last scrape data
        last_scrape = config_manager.get_last_scrape()

        # Fetch new listings
        new_listings, all_listings = await github_client.get_new_listings(last_scrape)

        print(f"[Scraper] Found {len(new_listings.summer)} new summer internships")
        print(f"[Scraper] Found {len(new_listings.offseason)} new off-season internships")

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
                        print(f"[Scraper] Error posting to channel {channel_id}: {e}")

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
        config_manager.update_last_scrape(
            summer_ids=all_listings.get_all_ids("summer"),
            offseason_ids=all_listings.get_all_ids("offseason")
        )

        print("[Scraper] Scrape completed successfully")

    except Exception as e:
        print(f"[Scraper] Error during scrape: {e}")
        raise


class ScraperTasks(commands.Cog):
    """Cog for background scraping tasks."""

    def __init__(self, bot: commands.Bot, config_manager: ConfigManager):
        self.bot = bot
        self.config_manager = config_manager
        # Get initial interval from config
        interval_hours = self.config_manager.get_scrape_interval()
        self._start_scraper(interval_hours)

    def _start_scraper(self, hours: float):
        """Start the scraper task with a specific interval."""
        # Create a new loop with the specified interval
        @tasks.loop(hours=hours)
        async def scrape_task():
            """Periodic scraping task."""
            await scrape_and_post(self.bot, self.config_manager)

        @scrape_task.before_loop
        async def before_scrape_task():
            """Wait for bot to be ready before starting tasks."""
            await self.bot.wait_until_ready()
            print(f"[Scraper] Starting periodic scraping (every {hours} hours)")

        # Store the task
        self.scrape_task = scrape_task
        self.scrape_task.start()

    def cog_unload(self):
        """Stop tasks when cog is unloaded."""
        if hasattr(self, 'scrape_task'):
            self.scrape_task.cancel()

    async def restart_scraper(self, new_interval_hours: float):
        """Restart the scraper task with a new interval.

        Args:
            new_interval_hours: New interval in hours
        """
        print(f"[Scraper] Restarting with new interval: {new_interval_hours} hours")

        # Cancel existing task
        if hasattr(self, 'scrape_task'):
            self.scrape_task.cancel()

        # Start new task with new interval
        self._start_scraper(new_interval_hours)


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
