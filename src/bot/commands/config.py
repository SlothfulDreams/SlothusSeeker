"""Discord slash commands for bot configuration."""
import discord
from discord import app_commands
from discord.ext import commands
from src.config.config_manager import ConfigManager
from src.bot.embeds import create_config_embed


class ConfigCommands(commands.Cog):
    """Cog for configuration commands."""

    def __init__(self, bot: commands.Bot, config_manager: ConfigManager):
        self.bot = bot
        self.config_manager = config_manager

    @app_commands.command(
        name="set_summer_channel",
        description="Set the channel for summer internship postings"
    )
    @app_commands.describe(channel="The channel to post summer internships")
    @app_commands.default_permissions(administrator=True)
    async def set_summer_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        """Set the summer internships channel."""
        self.config_manager.set_channel(
            guild_id=interaction.guild_id,
            channel_type="summer",
            channel_id=channel.id
        )

        await interaction.response.send_message(
            f"✅ Summer internships will be posted to {channel.mention}",
            ephemeral=True
        )

    @app_commands.command(
        name="set_offseason_channel",
        description="Set the channel for off-season (Fall/Winter/Spring) internship postings"
    )
    @app_commands.describe(channel="The channel to post off-season internships")
    @app_commands.default_permissions(administrator=True)
    async def set_offseason_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        """Set the off-season internships channel."""
        self.config_manager.set_channel(
            guild_id=interaction.guild_id,
            channel_type="offseason",
            channel_id=channel.id
        )

        await interaction.response.send_message(
            f"✅ Off-season internships (Fall/Winter/Spring) will be posted to {channel.mention}",
            ephemeral=True
        )

    @app_commands.command(
        name="view_config",
        description="View the current bot configuration"
    )
    async def view_config(self, interaction: discord.Interaction):
        """View current configuration."""
        guild_config = self.config_manager.get_guild_config(interaction.guild_id)
        embed = create_config_embed(guild_config, interaction.guild.name)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="scrape_now",
        description="Manually trigger an internship scrape (Admin only)"
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
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error during scrape: {str(e)}",
                ephemeral=True
            )


async def setup(bot: commands.Bot, config_manager: ConfigManager):
    """Add the cog to the bot."""
    await bot.add_cog(ConfigCommands(bot, config_manager))
