"""Discord slash commands for bot configuration."""

import discord
from discord import app_commands
from discord.ext import commands

from src.bot.embeds import create_config_embed, create_internship_embed
from src.config.config_manager import ConfigManager
from src.scheduler.tasks import ScrapeStats, scrape_and_post
from src.scraper.github_client import GitHubClient
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class ConfigCommands(commands.Cog):
    """Cog for configuration commands."""

    def __init__(self, bot: commands.Bot, config_manager: ConfigManager):
        self.bot = bot
        self.config_manager = config_manager

    async def _validate_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> bool:
        """Validate bot permission and channel guild context."""
        if interaction.guild is None or interaction.guild.me is None:
            await interaction.response.send_message(
                "❌ This command can only be used inside a server.", ephemeral=True
            )
            return False

        if channel.guild.id != interaction.guild_id:
            await interaction.response.send_message(
                "❌ Channel must be in this server!", ephemeral=True
            )
            return False

        permissions = channel.permissions_for(interaction.guild.me)
        if not permissions.send_messages or not permissions.embed_links:
            await interaction.response.send_message(
                "❌ I don't have permission to send messages or embeds in that channel!\n"
                "Please grant me `Send Messages` and `Embed Links` permissions.",
                ephemeral=True,
            )
            return False

        return True

    async def _set_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        channel_type: str,
        success_message: str,
        other_channel_key: str,
    ) -> None:
        """Store a configured channel and run the first scrape when ready."""
        if not await self._validate_channel(interaction, channel):
            return

        self.config_manager.set_channel(
            guild_id=interaction.guild_id,
            channel_type=channel_type,
            channel_id=channel.id,
        )

        await interaction.response.send_message(success_message, ephemeral=True)

        guild_config = self.config_manager.get_guild_config(interaction.guild_id)
        if not guild_config.get(other_channel_key):
            return

        await interaction.followup.send(
            "🔄 Both channels configured! Triggering initial scrape...",
            ephemeral=True,
        )

        stats = await scrape_and_post(self.bot, self.config_manager)
        await interaction.followup.send(
            self._format_scrape_summary("✅ Initial scrape completed", stats),
            ephemeral=True,
        )

    def _format_scrape_summary(self, heading: str, stats: ScrapeStats) -> str:
        """Create a concise scrape summary for slash command followups."""
        response = f"{heading}\n\n"
        response += "📊 **Results:**\n"
        response += f"• Summer internships posted: {stats.summer_posted}\n"
        response += f"• Off-season internships posted: {stats.offseason_posted}\n"
        response += f"• Total new listings: {stats.total_new}\n"

        if stats.errors > 0:
            response += (
                f"\n⚠️ {stats.errors} error(s) occurred while posting. Check logs."
            )

        if stats.total_new == 0:
            response += "\n\n💡 No new internships found."

        return response

    @app_commands.command(
        name="set_summer_channel",
        description="Set the channel for summer internship postings",
    )
    @app_commands.describe(channel="The channel to post summer internships")
    @app_commands.default_permissions(administrator=True)
    async def set_summer_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Set the summer internships channel."""
        await self._set_channel(
            interaction=interaction,
            channel=channel,
            channel_type="summer",
            success_message=f"✅ Summer internships will be posted to {channel.mention}",
            other_channel_key="offseason_channel",
        )

    @app_commands.command(
        name="set_offseason_channel",
        description="Set the channel for off-season (Fall/Winter/Spring) internship postings",
    )
    @app_commands.describe(channel="The channel to post off-season internships")
    @app_commands.default_permissions(administrator=True)
    async def set_offseason_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Set the off-season internships channel."""
        await self._set_channel(
            interaction=interaction,
            channel=channel,
            channel_type="offseason",
            success_message=(
                "✅ Off-season internships (Fall/Winter/Spring) will be posted "
                f"to {channel.mention}"
            ),
            other_channel_key="summer_channel",
        )

    @app_commands.command(
        name="view_config", description="View the current bot configuration"
    )
    async def view_config(self, interaction: discord.Interaction):
        """View current configuration."""
        guild_config = self.config_manager.get_guild_config(interaction.guild_id)
        scrape_interval = self.config_manager.get_scrape_interval()
        start_timestamp = self.config_manager.get_scrape_start_timestamp()
        embed = create_config_embed(
            guild_config, interaction.guild.name, scrape_interval, start_timestamp
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="scrape_now",
        description="Manually trigger an internship scrape (Admin only)",
    )
    @app_commands.default_permissions(administrator=True)
    async def scrape_now(self, interaction: discord.Interaction):
        """Manually trigger a scrape."""
        await interaction.response.defer(ephemeral=True)

        try:
            # Check if channels are configured
            summer_channels = self.config_manager.get_all_channels("summer")
            offseason_channels = self.config_manager.get_all_channels("offseason")

            if not summer_channels or not offseason_channels:
                await interaction.followup.send(
                    "⚠️ No channels configured! Use `/set_summer_channel` and `/set_offseason_channel` first.",
                    ephemeral=True,
                )
                return

            stats = await scrape_and_post(self.bot, self.config_manager)
            response = self._format_scrape_summary("✅ **Scrape Complete**", stats)

            await interaction.followup.send(response, ephemeral=True)

        except Exception as e:
            logger.error(f"Error during manual scrape: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Error during scrape. Check logs for details.", ephemeral=True
            )

    @app_commands.command(
        name="test_scrape",
        description="Test scrape - fetch 5 most recent internships (only visible to you)",
    )
    @app_commands.default_permissions(administrator=True)
    async def test_scrape(self, interaction: discord.Interaction):
        """Test scrape that shows the 5 most recent internships."""
        await interaction.response.defer(ephemeral=True)

        try:
            start_timestamp = self.config_manager.get_scrape_start_timestamp()

            async with GitHubClient() as github_client:
                all_listings = await github_client.fetch_listings(start_timestamp)

            # Get the first 5 from each category
            summer_internships = all_listings.summer[:5]
            offseason_internships = all_listings.offseason[:5]

            # Build header message
            header = (
                f"🔍 **Test Scrape Results**\n"
                f"📊 Total found: {len(all_listings.summer)} summer, {len(all_listings.offseason)} off-season\n"
                f"Showing 5 most recent from each category:"
            )

            # Build embeds list (Discord allows up to 10 embeds per message)
            embeds = []

            # Add summer internship embeds
            for internship in summer_internships:
                embeds.append(create_internship_embed(internship))

            # Add off-season internship embeds
            for internship in offseason_internships:
                embeds.append(create_internship_embed(internship))

            # Send header message first
            await interaction.followup.send(header, ephemeral=True)

            # Send embeds if we have any
            if embeds:
                await interaction.followup.send(embeds=embeds, ephemeral=True)
            else:
                await interaction.followup.send(
                    "No internships found matching your criteria.", ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error during test scrape: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Error during test scrape. Check logs for details.", ephemeral=True
            )

    @app_commands.command(
        name="set_scrape_interval",
        description="Set how often the bot scrapes for new internships (Admin only)",
    )
    @app_commands.describe(hours="Hours between scrapes (0.5-168)")
    @app_commands.default_permissions(administrator=True)
    async def set_scrape_interval(
        self,
        interaction: discord.Interaction,
        hours: app_commands.Range[float, 0.5, 168.0],
    ):
        """Set the scrape interval."""
        try:
            # Update the interval
            self.config_manager.set_scrape_interval(hours)

            # Restart the scraper task with new interval
            from src.scheduler.tasks import get_scraper_cog

            scraper_cog = get_scraper_cog(self.bot)
            if scraper_cog:
                await scraper_cog.restart_scraper(hours)

            await interaction.response.send_message(
                f"✅ Scrape interval updated to {hours} hours. The scheduler has been restarted.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error updating interval: {str(e)}", ephemeral=True
            )

    @app_commands.command(
        name="set_start_date",
        description="Set the earliest date to scrape internships from (Admin only)",
    )
    @app_commands.describe(days_back="How many days back to scrape (1-365)")
    @app_commands.default_permissions(administrator=True)
    async def set_start_date(
        self,
        interaction: discord.Interaction,
        days_back: app_commands.Range[int, 1, 365],
    ):
        """Set the start date for scraping internships."""
        try:
            from datetime import datetime, timedelta

            # Calculate timestamp
            start_date = datetime.now() - timedelta(days=days_back)
            start_timestamp = int(start_date.timestamp())

            # Update the config
            self.config_manager.set_scrape_start_timestamp(start_timestamp)

            # Format date for display
            date_str = start_date.strftime("%B %d, %Y")

            await interaction.response.send_message(
                f"✅ Start date set to {date_str} ({days_back} days ago).\n"
                f"The bot will only scrape internships posted after this date.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error updating start date: {str(e)}", ephemeral=True
            )


async def setup(bot: commands.Bot, config_manager: ConfigManager):
    """Add the cog to the bot."""
    await bot.add_cog(ConfigCommands(bot, config_manager))
