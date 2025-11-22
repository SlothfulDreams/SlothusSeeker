"""Discord slash commands for bot configuration."""

import discord
from discord import app_commands
from discord.ext import commands

from src.bot.embeds import create_config_embed
from src.config.config_manager import ConfigManager


class ConfigCommands(commands.Cog):
    """Cog for configuration commands."""

    def __init__(self, bot: commands.Bot, config_manager: ConfigManager):
        self.bot = bot
        self.config_manager = config_manager

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
        # Validate bot permissions
        permissions = channel.permissions_for(interaction.guild.me)
        if not permissions.send_messages or not permissions.embed_links:
            await interaction.response.send_message(
                "❌ I don't have permission to send messages or embeds in that channel!\n"
                "Please grant me `Send Messages` and `Embed Links` permissions.",
                ephemeral=True,
            )
            return

        # Validate channel is in the same guild
        if channel.guild.id != interaction.guild_id:
            await interaction.response.send_message(
                "❌ Channel must be in this server!", ephemeral=True
            )
            return

        self.config_manager.set_channel(
            guild_id=interaction.guild_id, channel_type="summer", channel_id=channel.id
        )

        await interaction.response.send_message(
            f"✅ Summer internships will be posted to {channel.mention}", ephemeral=True
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
        # Validate bot permissions
        permissions = channel.permissions_for(interaction.guild.me)
        if not permissions.send_messages or not permissions.embed_links:
            await interaction.response.send_message(
                "❌ I don't have permission to send messages or embeds in that channel!\n"
                "Please grant me `Send Messages` and `Embed Links` permissions.",
                ephemeral=True,
            )
            return

        # Validate channel is in the same guild
        if channel.guild.id != interaction.guild_id:
            await interaction.response.send_message(
                "❌ Channel must be in this server!", ephemeral=True
            )
            return

        self.config_manager.set_channel(
            guild_id=interaction.guild_id,
            channel_type="offseason",
            channel_id=channel.id,
        )

        await interaction.response.send_message(
            f"✅ Off-season internships (Fall/Winter/Spring) will be posted to {channel.mention}",
            ephemeral=True,
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
            # Trigger the scrape task
            # The actual scraping is handled by the scheduler
            from src.scheduler.tasks import scrape_and_post

            await scrape_and_post(self.bot, self.config_manager)

            await interaction.followup.send(
                "✅ Manual scrape completed! Check the configured channels for new postings.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error during scrape: {str(e)}", ephemeral=True
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
            from src.scraper.github_client import GitHubClient

            # Create client and fetch listings
            github_client = GitHubClient()

            # Get start timestamp for filtering
            start_timestamp = self.config_manager.get_scrape_start_timestamp()

            # Fetch all listings
            all_listings = await github_client.fetch_listings(start_timestamp)

            # Get the first 5 from each category
            summer_internships = all_listings.summer[:5]
            offseason_internships = all_listings.offseason[:5]

            # Build response message
            message_parts = []
            message_parts.append("🔍 **Test Scrape Results**\n")
            message_parts.append(
                f"📊 Total found: {len(all_listings.summer)} summer, {len(all_listings.offseason)} off-season\n"
            )

            if summer_internships:
                message_parts.append("\n**☀️ Summer Internships (5 most recent):**")
                for i, internship in enumerate(summer_internships, 1):
                    message_parts.append(
                        f"{i}. **{internship.company_name}** - {internship.title}\n"
                        f"   📍 {internship.location_str}\n"
                        f"   📅 Posted: {internship.posted_date_str}\n"
                        f"   🔗 {internship.url}\n"
                    )
            else:
                message_parts.append("\n**☀️ Summer Internships:** None found")

            if offseason_internships:
                message_parts.append("\n**🍂 Off-Season Internships (5 most recent):**")
                for i, internship in enumerate(offseason_internships, 1):
                    message_parts.append(
                        f"{i}. **{internship.company_name}** - {internship.title}\n"
                        f"   📍 {internship.location_str}\n"
                        f"   📅 Posted: {internship.posted_date_str}\n"
                        f"   🔗 {internship.url}\n"
                    )
            else:
                message_parts.append("\n**🍂 Off-Season Internships:** None found")

            message = "\n".join(message_parts)

            # Discord has a 2000 character limit, so truncate if needed
            if len(message) > 2000:
                message = message[:1997] + "..."

            await interaction.followup.send(message, ephemeral=True)

            # Close the client session
            await github_client.close()

        except Exception as e:
            await interaction.followup.send(
                f"❌ Error during test scrape: {str(e)}", ephemeral=True
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
            import time
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
