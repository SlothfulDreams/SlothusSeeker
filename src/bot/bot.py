"""Main Discord bot implementation."""
import discord
from discord.ext import commands
from src.config.settings import DISCORD_BOT_TOKEN
from src.config.config_manager import ConfigManager


class InternshipBot(commands.Bot):
    """Discord bot for scraping and posting internship listings."""

    def __init__(self, config_manager: ConfigManager):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",  # Fallback prefix, mainly using slash commands
            intents=intents,
            help_command=None
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
        print("[Bot] Syncing commands...")
        await self.tree.sync()
        print("[Bot] Commands synced!")

    async def on_ready(self):
        """Called when the bot is ready."""
        print(f"[Bot] Logged in as {self.user} (ID: {self.user.id})")
        print(f"[Bot] Connected to {len(self.guilds)} guild(s)")
        print("[Bot] Bot is ready!")

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
