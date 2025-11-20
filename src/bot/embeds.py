"""Discord embed formatting for internship listings."""
import discord
from src.scraper.data_models import Internship


def create_internship_embed(internship: Internship) -> discord.Embed:
    """Create a rich embed for an internship listing.

    Args:
        internship: Internship model

    Returns:
        Discord Embed object
    """
    # Determine color based on type
    if internship.is_summer:
        color = discord.Color.gold()
        season_emoji = "☀️"
    else:
        color = discord.Color.blue()
        season_emoji = "❄️"

    # Create title with company and role
    title = f"{internship.company_name} - {internship.title}"

    # Create embed
    embed = discord.Embed(
        title=title,
        url=internship.url,
        color=color,
        description=f"{season_emoji} {', '.join(internship.terms)}"
    )

    # Add fields
    embed.add_field(
        name="📍 Location",
        value=internship.location_str,
        inline=True
    )

    embed.add_field(
        name="📅 Posted",
        value=internship.posted_date_str,
        inline=True
    )

    if internship.sponsorship:
        embed.add_field(
            name="🛂 Sponsorship",
            value=internship.sponsorship,
            inline=True
        )

    # Add footer
    embed.set_footer(text=f"ID: {internship.id}")

    return embed


def create_stats_embed(summer_count: int, offseason_count: int) -> discord.Embed:
    """Create an embed showing scrape statistics.

    Args:
        summer_count: Number of new summer internships
        offseason_count: Number of new off-season internships

    Returns:
        Discord Embed object
    """
    embed = discord.Embed(
        title="📊 New Internships Found",
        color=discord.Color.green()
    )

    embed.add_field(
        name="☀️ Summer",
        value=f"{summer_count} new",
        inline=True
    )

    embed.add_field(
        name="❄️ Off-Season",
        value=f"{offseason_count} new",
        inline=True
    )

    return embed


def create_config_embed(guild_config: dict, guild_name: str) -> discord.Embed:
    """Create an embed showing current configuration.

    Args:
        guild_config: Configuration dictionary for the guild
        guild_name: Name of the guild

    Returns:
        Discord Embed object
    """
    embed = discord.Embed(
        title=f"⚙️ Configuration for {guild_name}",
        color=discord.Color.blurple()
    )

    summer_channel = guild_config.get("summer_channel")
    offseason_channel = guild_config.get("offseason_channel")

    embed.add_field(
        name="☀️ Summer Channel",
        value=f"<#{summer_channel}>" if summer_channel else "Not configured",
        inline=False
    )

    embed.add_field(
        name="❄️ Off-Season Channel",
        value=f"<#{offseason_channel}>" if offseason_channel else "Not configured",
        inline=False
    )

    if not summer_channel and not offseason_channel:
        embed.description = "No channels configured yet. Use `/set_summer_channel` or `/set_offseason_channel` to get started!"

    return embed
