"""Discord embed formatting for internship listings."""

from datetime import datetime

import discord

from src.scraper.data_models import Internship, SEASON_DISPLAY_NAMES, SEASONS

EMBED_TITLE_LIMIT = 256
EMBED_DESCRIPTION_LIMIT = 4096
EMBED_FIELD_LIMIT = 1024
COMPANY_NAME_LIMIT = 80
SEASON_CHANNEL_LABELS = {
    "spring": "🌱 Spring/Winter Channel",
    "summer": "☀️ Summer Channel",
    "fall": "🍂 Fall Channel",
}


def _truncate(value: str, limit: int) -> str:
    """Trim a string to a Discord embed limit."""
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1]}…"


def _format_company_line(index: int, company: dict) -> str:
    company_id = company.get("id", "?")
    company_name = _truncate(
        str(company.get("company_name", "unknown")),
        COMPANY_NAME_LIMIT,
    )
    return f"`{index:02}`  `#{company_id}`  **{company_name}**"


def _format_interval(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} minutes"

    hours = minutes / 60
    if hours == 1:
        return "1 hour"
    if hours == int(hours):
        return f"{int(hours)} hours"
    return f"{hours} hours"


def _format_season_description(internship: Internship, season_emoji: str) -> str:
    season_names = ", ".join(
        SEASON_DISPLAY_NAMES[season] for season in internship.seasons
    )
    return _truncate(f"{season_emoji} {season_names}", EMBED_FIELD_LIMIT)


def create_internship_embed(internship: Internship) -> discord.Embed:
    """Create a rich embed for an internship listing.

    Args:
        internship: Internship model

    Returns:
        Discord Embed object
    """
    if internship.primary_season == "summer":
        color = discord.Color.gold()
        season_emoji = "☀️"
    elif internship.primary_season == "fall":
        color = discord.Color.orange()
        season_emoji = "🍂"
    else:
        color = discord.Color.green()
        season_emoji = "🌱"

    title = _truncate(
        f"{internship.company_name} - {internship.title}", EMBED_TITLE_LIMIT
    )

    embed = discord.Embed(
        title=title,
        url=internship.url,
        color=color,
        description=_format_season_description(internship, season_emoji),
    )

    embed.add_field(
        name="📍 Location",
        value=_truncate(internship.location_str, EMBED_FIELD_LIMIT),
        inline=True,
    )

    embed.add_field(
        name="📅 Posted", value=internship.posted_date_str, inline=True
    )

    if internship.work_model:
        embed.add_field(
            name="🏢 Work Model",
            value=_truncate(internship.work_model, EMBED_FIELD_LIMIT),
            inline=True,
        )

    embed.set_footer(text=f"ID: {internship.id}")

    return embed


def create_config_embed(
    guild_config: dict,
    guild_name: str,
    scrape_interval_minutes: int | None = None,
    start_timestamp: int | None = None,
) -> discord.Embed:
    """Create an embed showing current configuration.

    Args:
        guild_config: Configuration dictionary for the guild
        guild_name: Name of the guild
        scrape_interval_minutes: Current scrape interval in minutes (optional)
        start_timestamp: Start timestamp for filtering (defaults to 3 days ago)

    Returns:
        Discord Embed object
    """
    embed = discord.Embed(
        title=f"⚙️ Configuration for {guild_name}",
        color=discord.Color.blurple(),
    )

    configured = False
    for season in SEASONS:
        channel_id = guild_config.get(f"{season}_channel_id")
        if channel_id:
            configured = True
        embed.add_field(
            name=SEASON_CHANNEL_LABELS[season],
            value=f"<#{channel_id}>" if channel_id else "Not configured",
            inline=False,
        )

    sudo_id = guild_config.get("sudo_id")
    embed.add_field(
        name="📣 Sudo Channel",
        value=f"<#{sudo_id}>" if sudo_id else "Not configured",
        inline=False,
    )

    if scrape_interval_minutes is not None:
        embed.add_field(
            name="⏰ Scrape Interval",
            value=_format_interval(scrape_interval_minutes),
            inline=False,
        )

    if start_timestamp is not None:
        date_str = datetime.fromtimestamp(start_timestamp).strftime("%B %d, %Y")
        embed.add_field(
            name="📅 Scraping From",
            value=f"Internships posted after {date_str}",
            inline=False,
        )

    if not configured:
        embed.description = (
            "No season channels configured yet. "
            "Use `/config set-season-channel` to get started!"
        )

    return embed


def create_company_list_embed(
    companies: list[dict],
    page: int,
    per_page: int,
) -> discord.Embed:
    """Create a paginated embed for allow-listed companies."""
    total_companies = len(companies)
    total_pages = max(1, (total_companies + per_page - 1) // per_page)
    start_index = page * per_page
    page_companies = companies[start_index : start_index + per_page]

    if page_companies:
        description = "\n".join(
            _format_company_line(start_index + index, company)
            for index, company in enumerate(page_companies, start=1)
        )
    else:
        description = "No companies configured yet."

    embed = discord.Embed(
        title="Company Watchlist",
        description=_truncate(description, EMBED_DESCRIPTION_LIMIT),
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Entries", value=str(total_companies), inline=True)
    embed.add_field(name="Page", value=f"{page + 1}/{total_pages}", inline=True)
    embed.set_footer(text="Use /companies delete company_id:<ID> to remove an entry")

    return embed
