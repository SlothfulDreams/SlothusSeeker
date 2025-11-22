"""Main Discord bot implementation."""

import os

import discord
from discord.ext import commands

from src.config.config_manager import ConfigManager
from src.config.settings import DISCORD_BOT_TOKEN
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class InternshipBot(commands.Bot):
    """Discord bot for scraping and posting internship listings."""

    def __init__(self, config_manager: ConfigManager):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",  # Fallback prefix, mainly using slash commands
            intents=intents,
            help_command=None,
        )

        self.config_manager = config_manager

    async def setup_hook(self):
        """Setup hook called when the bot starts."""
        # Load commands
        from src.bot.commands import config as config_commands

        await config_commands.setup(self, self.config_manager)

        # Load scheduler
        from src.scheduler import tasks

        await tasks.setup(self, self.config_manager)

        # Sync commands with Discord
        logger.info("Syncing commands...")

        # Check if in development mode (test guild specified)
        test_guild_id = os.getenv("TEST_GUILD_ID")
        if test_guild_id:
            # Development mode: sync to test guild only (instant, no duplicates)
            try:
                guild_id = int(test_guild_id)
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info(
                    f"Commands synced to test guild {guild_id} ONLY (development mode)"
                )
            except ValueError:
                logger.warning(
                    f"Invalid TEST_GUILD_ID: {test_guild_id}, falling back to global sync"
                )
                await self.tree.sync()
                logger.info("Commands synced globally")
        else:
            # Production mode: sync globally
            await self.tree.sync()
            logger.info(
                "Commands synced globally (production mode, may take up to 1 hour)"
            )

    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")
        logger.info("Bot is ready!")

    async def on_guild_join(self, guild: discord.Guild):
        """Called when the bot joins a new guild."""
        print(f"[Bot] Joined new guild: {guild.name} (ID: {guild.id})")

    async def on_guild_remove(self, guild: discord.Guild):
        """Called when the bot is removed from a guild."""
        print(f"[Bot] Removed from guild: {guild.name} (ID: {guild.id})")


def create_bot() -> InternshipBot:
    """Create and configure the bot instance.

    Returns:
        Configured InternshipBot instance
    """
    config_manager = ConfigManager()
    return InternshipBot(config_manager)


def run_bot():
    """Run the bot."""
    bot = create_bot()
    bot.run(DISCORD_BOT_TOKEN)
