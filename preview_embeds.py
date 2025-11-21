#!/usr/bin/env python3
"""Preview script to show how embeds will look."""
from src.scraper.data_models import Internship
from src.bot.embeds import create_internship_embed, create_stats_embed, create_config_embed
import discord

# Sample internships
summer_internship = Internship(
    id="summer-2026-google-swe",
    company_name="Google",
    title="Software Engineering Intern",
    locations=["Mountain View, CA", "New York, NY", "Seattle, WA"],
    terms=["Summer 2026"],
    sponsorship="Offers Sponsorship",
    active=True,
    is_visible=True,
    url="https://careers.google.com/apply",
    date_posted=1700000000,
    date_updated=1700000000,
    source="SimplifyJobs",
    company_url="https://google.com"
)

offseason_internship = Internship(
    id="fall-2025-meta-pm",
    company_name="Meta",
    title="Product Manager Intern",
    locations=["Menlo Park, CA"],
    terms=["Fall 2025"],
    sponsorship="Does not offer sponsorship",
    active=True,
    is_visible=True,
    url="https://metacareers.com/apply",
    date_posted=1699000000,
    date_updated=1699000000,
    source="SimplifyJobs",
    company_url="https://meta.com"
)

remote_internship = Internship(
    id="summer-2026-stripe-backend",
    company_name="Stripe",
    title="Backend Engineering Intern",
    locations=["Remote"],
    terms=["Summer 2026", "Summer 2027"],
    sponsorship="",  # No sponsorship info
    active=True,
    is_visible=True,
    url="https://stripe.com/jobs/apply",
    date_posted=1732000000,
    date_updated=1732000000,
    source="SimplifyJobs",
    company_url="https://stripe.com"
)


def print_embed(embed: discord.Embed, title: str):
    """Print embed details in a readable format."""
    print(f"\n{'='*70}")
    print(f"{title}")
    print(f"{'='*70}")
    print(f"Color: {embed.color}")
    print(f"\nTitle: {embed.title}")
    if embed.url:
        print(f"URL: {embed.url}")
    if embed.description:
        print(f"Description: {embed.description}")

    print(f"\nFields ({len(embed.fields)}):")
    for field in embed.fields:
        inline_str = " (inline)" if field.inline else ""
        print(f"  • {field.name}{inline_str}")
        print(f"    {field.value}")

    if embed.footer:
        print(f"\nFooter: {embed.footer.text}")
    print()


def main():
    """Generate and display all embed types."""
    print("\n" + "🎨 DISCORD EMBED PREVIEW ".center(70, "="))

    # 1. Summer Internship Embed
    summer_embed = create_internship_embed(summer_internship)
    print_embed(summer_embed, "1️⃣  SUMMER INTERNSHIP EMBED")

    # 2. Off-Season Internship Embed
    offseason_embed = create_internship_embed(offseason_internship)
    print_embed(offseason_embed, "2️⃣  OFF-SEASON INTERNSHIP EMBED")

    # 3. Remote Internship Embed (no sponsorship info)
    remote_embed = create_internship_embed(remote_internship)
    print_embed(remote_embed, "3️⃣  REMOTE INTERNSHIP EMBED (No Sponsorship Info)")

    # 4. Stats Embed
    stats_embed = create_stats_embed(summer_count=12, offseason_count=5)
    print_embed(stats_embed, "4️⃣  STATS EMBED")

    # 5. Config Embed
    guild_config = {
        "summer_channel": 1234567890,
        "offseason_channel": 9876543210
    }
    config_embed = create_config_embed(
        guild_config=guild_config,
        guild_name="Tech Internships Hub",
        scrape_interval=6.0,
        start_timestamp=1700000000
    )
    print_embed(config_embed, "5️⃣  CONFIGURATION EMBED")

    # 6. Config Embed with no channels configured
    empty_config = {}
    empty_embed = create_config_embed(
        guild_config=empty_config,
        guild_name="New Server",
        scrape_interval=6.0,
        start_timestamp=1700000000
    )
    print_embed(empty_embed, "6️⃣  CONFIGURATION EMBED (Not Configured)")

    # 7. Config Embed with custom interval (30 minutes)
    custom_config = {
        "summer_channel": 1234567890,
        "offseason_channel": None
    }
    custom_embed = create_config_embed(
        guild_config=custom_config,
        guild_name="My Server",
        scrape_interval=0.5,  # 30 minutes
        start_timestamp=1732000000
    )
    print_embed(custom_embed, "7️⃣  CONFIGURATION EMBED (30 min interval)")

    print("\n" + "="*70)
    print("✅ Preview complete!")
    print("\nNOTE: In Discord, these embeds will have:")
    print("  • Rich colors (gold for summer, blue for off-season)")
    print("  • Clickable channel mentions (e.g., #summer-internships)")
    print("  • Clickable title URLs")
    print("  • Better spacing and visual formatting")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
