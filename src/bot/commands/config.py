"""Discord slash commands for bot configuration."""

from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from src.bot.embeds import create_config_embed, create_status_embed
from src.bot.views import CompanyListView
from src.config.config_manager import ConfigManager
from src.config.settings import COMPANIES_PER_PAGE
from src.scheduler.tasks import ScrapeStats, get_scraper_cog, scrape_and_post
from src.scraper.data_models import (
    SEASON_DISPLAY_NAMES,
    SEASONS,
    normalize_company_name,
)
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

SEASON_CHOICES = [
    app_commands.Choice(name=SEASON_DISPLAY_NAMES[season], value=season)
    for season in SEASONS
]


class ConfigCommands(commands.Cog):
    """Cog for configuration and company allow-list commands."""

    config_group = app_commands.Group(
        name="config", description="Manage season posting channels"
    )
    companies_group = app_commands.Group(
        name="companies", description="Manage company notification allow-list"
    )

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

    async def _require_guild(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is not None and interaction.guild_id is not None:
            return True

        await interaction.response.send_message(
            "❌ This command can only be used inside a server.", ephemeral=True
        )
        return False

    def _format_scrape_summary(self, heading: str, stats: ScrapeStats) -> str:
        """Create a concise scrape summary for slash command followups."""
        if stats.outcome == "skipped":
            return f"⏭️ **Scrape skipped**\n{stats.note}"
        if stats.outcome == "partial":
            heading = "⚠️ **Scrape completed with errors**"
        lines = [heading, "", "📊 **Results:**"]
        for season in SEASONS:
            label = SEASON_DISPLAY_NAMES[season]
            posted = stats.posted_by_season[season]
            lines.append(f"• {label} internships posted: {posted}")
        lines.append(f"• Total new listings: {stats.total_new}")

        if stats.errors > 0:
            lines.extend(
                [
                    "",
                    f"⚠️ {stats.errors} error(s) occurred while posting. Check logs.",
                ]
            )

        if stats.total_new == 0:
            lines.extend(["", "💡 No new matching internships found."])

        return "\n".join(lines)

    async def _send_operation_error(
        self, interaction: discord.Interaction, action: str, error: Exception
    ) -> None:
        """Log an operation failure and send a safe ephemeral response."""
        logger.error("Error while %s: %s", action, error, exc_info=True)
        message = f"❌ Error while {action}. Check logs for details."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
            return

        await interaction.response.send_message(message, ephemeral=True)

    @config_group.command(
        name="set-season-channel",
        description="Set the channel for a season's internship postings",
    )
    @app_commands.describe(
        season="The season to configure",
        channel="The channel to post matching internships",
    )
    @app_commands.choices(season=SEASON_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def set_season_channel(
        self,
        interaction: discord.Interaction,
        season: app_commands.Choice[str],
        channel: discord.TextChannel,
    ):
        """Set a season internships channel."""
        if not await self._validate_channel(interaction, channel):
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await self.config_manager.set_channel(
                guild_id=interaction.guild_id,
                server_name=interaction.guild.name,
                channel_type=season.value,
                channel_id=channel.id,
            )
            await interaction.followup.send(
                f"✅ {season.name} internships will be posted to {channel.mention}",
                ephemeral=True,
            )
        except Exception as e:
            await self._send_operation_error(
                interaction,
                "setting the season channel",
                e,
            )

    @config_group.command(
        name="set-sudo-channel",
        description="Set the sudo channel for this server",
    )
    @app_commands.describe(channel="The sudo channel")
    @app_commands.default_permissions(administrator=True)
    async def set_sudo_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Set the sudo channel."""
        if not await self._validate_channel(interaction, channel):
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await self.config_manager.set_sudo_channel(
                guild_id=interaction.guild_id,
                server_name=interaction.guild.name,
                channel_id=channel.id,
            )
            await interaction.followup.send(
                f"✅ Sudo channel set to {channel.mention}",
                ephemeral=True,
            )
        except Exception as e:
            await self._send_operation_error(
                interaction,
                "setting the sudo channel",
                e,
            )

    @config_group.command(name="view", description="View the current bot configuration")
    async def view_config(self, interaction: discord.Interaction):
        """View current configuration."""
        if not await self._require_guild(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        try:
            guild_config = await self.config_manager.get_guild_config(
                interaction.guild_id
            )
            scrape_interval_minutes = self.config_manager.get_scrape_interval_minutes()
            start_timestamp = self.config_manager.get_scrape_start_timestamp()
            embed = create_config_embed(
                guild_config,
                interaction.guild.name,
                scrape_interval_minutes,
                start_timestamp,
            )

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await self._send_operation_error(interaction, "loading configuration", e)

    @app_commands.command(name="status", description="Show scraper health and latest session results")
    async def status(self, interaction: discord.Interaction):
        """Read session diagnostics without fetching listings or changing settings."""
        if not await self._require_guild(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            scraper = get_scraper_cog(self.bot)
            scheduler_state = "Unavailable"
            next_iteration = None
            if scraper:
                loop = scraper.scrape_task
                if loop.failed():
                    scheduler_state = "Stopped (failed)"
                elif loop.is_running():
                    scheduler_state = "Running"
                    next_iteration = loop.next_iteration
                else:
                    scheduler_state = "Stopped"
            embed = create_status_embed(
                self.bot.scrape_monitor,
                scheduler_state=scheduler_state,
                next_iteration=next_iteration,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await self._send_operation_error(interaction, "loading scraper status", e)

    @config_group.command(
        name="scrape-now",
        description="Manually trigger an internship scrape",
    )
    @app_commands.default_permissions(administrator=True)
    async def scrape_now(self, interaction: discord.Interaction):
        """Manually trigger a scrape."""
        await interaction.response.defer(ephemeral=True)

        try:
            stats = await scrape_and_post(self.bot, self.config_manager)
            response = self._format_scrape_summary("✅ **Scrape Complete**", stats)

            await interaction.followup.send(response, ephemeral=True)

        except Exception as e:
            await self._send_operation_error(interaction, "running the scrape", e)

    @config_group.command(
        name="set-scrape-interval",
        description="Set how often the bot scrapes for new internships",
    )
    @app_commands.describe(minutes="Minutes between scrapes (10-10080)")
    @app_commands.default_permissions(administrator=True)
    async def set_scrape_interval(
        self,
        interaction: discord.Interaction,
        minutes: app_commands.Range[int, 10, 10080],
    ):
        """Set the scrape interval."""
        try:
            self.config_manager.set_scrape_interval_minutes(minutes)

            scraper_cog = get_scraper_cog(self.bot)
            if scraper_cog:
                await scraper_cog.restart_scraper(minutes)

            await interaction.response.send_message(
                f"✅ Scrape interval updated to {minutes} minutes. "
                "The scheduler has been restarted.",
                ephemeral=True,
            )
        except Exception as e:
            await self._send_operation_error(interaction, "updating the interval", e)

    @config_group.command(
        name="set-start-date",
        description="Set the earliest date to scrape internships from",
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
            start_date = datetime.now() - timedelta(days=days_back)
            start_timestamp = int(start_date.timestamp())
            self.config_manager.set_scrape_start_timestamp(start_timestamp)
            date_str = start_date.strftime("%B %d, %Y")

            await interaction.response.send_message(
                f"✅ Start date set to {date_str} ({days_back} days ago).\n"
                f"The bot will only scrape internships posted after this date.",
                ephemeral=True,
            )
        except Exception as e:
            await self._send_operation_error(interaction, "updating the start date", e)

    @companies_group.command(
        name="add",
        description="Add a company to the notification allow-list",
    )
    @app_commands.describe(company_name="Company name to match, case-insensitive")
    @app_commands.default_permissions(administrator=True)
    async def add_company(self, interaction: discord.Interaction, company_name: str):
        """Add a company to the allow-list."""
        await interaction.response.defer(ephemeral=True)
        try:
            normalized = normalize_company_name(company_name)
            company = await self.config_manager.add_company(normalized)
            company_id = company.get("id", "existing")
            await interaction.followup.send(
                f"✅ Added `{normalized}` to Companies with ID `{company_id}`.",
                ephemeral=True,
            )
        except Exception as e:
            await self._send_operation_error(interaction, "adding the company", e)

    @companies_group.command(
        name="list",
        description="List companies in the notification allow-list",
    )
    @app_commands.default_permissions(administrator=True)
    async def list_companies(self, interaction: discord.Interaction):
        """List all allow-listed companies."""
        await interaction.response.defer(ephemeral=True)
        try:
            companies = await self.config_manager.list_companies()
            view = CompanyListView(companies, owner_id=interaction.user.id)
            await interaction.followup.send(
                embed=view.embed(),
                view=view if len(companies) > COMPANIES_PER_PAGE else None,
                ephemeral=True,
            )
        except Exception as e:
            await self._send_operation_error(interaction, "listing companies", e)

    @companies_group.command(
        name="delete",
        description="Delete a company from the notification allow-list by ID",
    )
    @app_commands.describe(company_id="The company ID from /companies list")
    @app_commands.default_permissions(administrator=True)
    async def delete_company(self, interaction: discord.Interaction, company_id: int):
        """Delete an allow-listed company by ID."""
        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await self.config_manager.delete_company(company_id)
            if deleted:
                await interaction.followup.send(
                    f"✅ Deleted company ID `{company_id}`.", ephemeral=True
                )
                return

            await interaction.followup.send(
                f"⚠️ No company found with ID `{company_id}`.",
                ephemeral=True,
            )
        except Exception as e:
            await self._send_operation_error(interaction, "deleting the company", e)


async def setup(bot: commands.Bot, config_manager: ConfigManager):
    """Add the cog to the bot."""
    await bot.add_cog(ConfigCommands(bot, config_manager))
