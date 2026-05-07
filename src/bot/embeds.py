"""Discord embed formatting for internship listings."""

from datetime import datetime

import discord

from src.scraper.data_models import Internship

EMBED_TITLE_LIMIT = 256
EMBED_FIELD_LIMIT = 1024


def _truncate(value: str, limit: int) -> str:
    """Trim a string to a Discord embed limit."""
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1]}…"


def create_internship_embed(internship: Internship) -> discord.Embed:
    """Create a rich embed for an internship listing.

    Args:
        internship: Internship model

    Returns:
        Discord Embed object
    """
    if internship.is_summer:
        color = discord.Color.gold()
        season_emoji = "☀️"
    else:
        color = discord.Color.blue()
        season_emoji = "❄️"

    title = _truncate(
        f"{internship.company_name} - {internship.title}", EMBED_TITLE_LIMIT
    )

    embed = discord.Embed(
        title=title,
        url=internship.url,
        color=color,
        description=_truncate(
            f"{season_emoji} {', '.join(internship.terms)}", EMBED_FIELD_LIMIT
        ),
    )

    embed.add_field(
        name="📍 Location",
        value=_truncate(internship.location_str, EMBED_FIELD_LIMIT),
        inline=True,
    )

    embed.add_field(
        name="📅 Posted", value=internship.posted_date_str, inline=True
    )

    if internship.sponsorship:
        embed.add_field(
            name="🛂 Sponsorship",
            value=_truncate(internship.sponsorship, EMBED_FIELD_LIMIT),
            inline=True,
        )

    embed.set_footer(text=f"ID: {internship.id}")

    return embed


def create_config_embed(
    guild_config: dict,
    guild_name: str,
    scrape_interval: float | None = None,
    start_timestamp: int | None = None,
) -> discord.Embed:
    """Create an embed showing current configuration.

    Args:
        guild_config: Configuration dictionary for the guild
        guild_name: Name of the guild
        scrape_interval: Current scrape interval in hours (optional)
        start_timestamp: Start timestamp for filtering (defaults to 3 days ago)

    Returns:
        Discord Embed object
    """
    embed = discord.Embed(
        title=f"⚙️ Configuration for {guild_name}",
        color=discord.Color.blurple(),
    )

    summer_channel = guild_config.get("summer_channel")
    offseason_channel = guild_config.get("offseason_channel")

    embed.add_field(
        name="☀️ Summer Channel",
        value=f"<#{summer_channel}>" if summer_channel else "Not configured",
        inline=False,
    )

    embed.add_field(
        name="❄️ Off-Season Channel",
        value=f"<#{offseason_channel}>" if offseason_channel else "Not configured",
        inline=False,
    )

    if scrape_interval is not None:
        # Format interval nicely
        if scrape_interval < 1:
            interval_str = f"{scrape_interval * 60:.0f} minutes"
        elif scrape_interval == 1:
            interval_str = "1 hour"
        else:
            # Show as integer if it's a whole number
            if scrape_interval == int(scrape_interval):
                interval_str = f"{int(scrape_interval)} hours"
            else:
                interval_str = f"{scrape_interval} hours"

        embed.add_field(
            name="⏰ Scrape Interval", value=interval_str, inline=False
        )

    if start_timestamp is not None:
        date_str = datetime.fromtimestamp(start_timestamp).strftime("%B %d, %Y")
        embed.add_field(
            name="📅 Scraping From",
            value=f"Internships posted after {date_str}",
            inline=False,
        )

    if not summer_channel and not offseason_channel:
        embed.description = "No channels configured yet. Use `/set_summer_channel` or `/set_offseason_channel` to get started!"

    return embed
