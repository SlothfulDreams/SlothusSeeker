"""Main Discord bot implementation."""

import discord
from discord import app_commands
from discord.ext import commands

from src.config.config_manager import ConfigManager
from src.config.settings import DISCORD_BOT_TOKEN, SYNC_COMMANDS_ON_START
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class InternshipBot(commands.Bot):
    """Discord bot for scraping and posting internship listings."""

    def __init__(self, config_manager: ConfigManager):
        intents = discord.Intents.default()
        super().__init__(
            command_prefix="!",  # Fallback prefix, mainly using slash commands
            intents=intents,
            help_command=None,
        )

        self.config_manager = config_manager
        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self):
        """Setup hook called when the bot starts."""
        from src.bot.commands import config as config_commands

        await config_commands.setup(self, self.config_manager)

        from src.scheduler import tasks

        await tasks.setup(self, self.config_manager)

        await self._sync_commands()

    async def _sync_commands(self):
        """Sync slash commands when explicitly configured."""
        if not SYNC_COMMANDS_ON_START:
            logger.info(
                "Skipping command sync. Set SYNC_COMMANDS_ON_START=true to sync global commands."
            )
            return

        logger.info("Syncing commands globally...")
        await self.tree.sync()
        logger.info("Commands synced globally (may take up to 1 hour)")

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle uncaught slash command errors with an ephemeral response."""
        logger.error("Unhandled slash command error: %s", error, exc_info=True)
        message = "❌ Command failed unexpectedly. Check logs for details."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            logger.exception("Failed to send slash command error response")

    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)
        logger.info("Connected to %s guild(s)", len(self.guilds))
        logger.info("Bot is ready!")

    async def on_guild_join(self, guild: discord.Guild):
        """Called when the bot joins a new guild."""
        logger.info("Joined new guild: %s (ID: %s)", guild.name, guild.id)

    async def on_guild_remove(self, guild: discord.Guild):
        """Called when the bot is removed from a guild."""
        logger.info("Removed from guild: %s (ID: %s)", guild.name, guild.id)

    async def close(self):
        """Cleanup resources before shutdown."""
        logger.info("Bot shutting down, cleaning up resources...")

        scraper_cog = self.get_cog("ScraperTasks")
        if scraper_cog:
            scraper_cog.scrape_task.cancel()
            logger.info("Scheduler task cancelled")

        await super().close()


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
