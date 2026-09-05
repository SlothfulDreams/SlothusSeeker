from datetime import datetime, timedelta, timezone

import pytest

from src.scraper.github_client import (
    GitHubClient, _parse_age_label, _parse_date_label, parse_jobright_readme,
)


def utc(year, month, day, hour=0):
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


@pytest.mark.parametrize("label,reference,expected", [
    ("Dec 31", utc(2027, 1, 2), utc(2026, 12, 31)),
    ("Jan 2", utc(2027, 1, 2), utc(2027, 1, 2)),
    ("January 1", utc(2027, 1, 2), utc(2027, 1, 1)),
    ("Jan 1", utc(2026, 12, 31), utc(2026, 1, 1)),
    ("Sept 1", utc(2026, 9, 2), utc(2026, 9, 1)),
    ("SEPT 1", utc(2026, 9, 2), utc(2026, 9, 1)),
    ("September 1", utc(2026, 9, 2), utc(2026, 9, 1)),
    ("Feb 29", utc(2024, 3, 1), utc(2024, 2, 29)),
    ("Feb 29", utc(2025, 3, 1), utc(2024, 2, 29)),
    ("Feb 29", utc(2104, 2, 28), utc(2096, 2, 29)),
])
def test_posting_date_uses_most_recent_valid_year(label, reference, expected):
    assert _parse_date_label(label, reference) == int(expected.timestamp())


@pytest.mark.parametrize("label", ["", "unknown", "Feb 30", "Apr 31", "Jan 0", "Jan 32"])
def test_invalid_date_stays_unspecified(label):
    assert _parse_date_label(label, utc(2026, 5, 12)) == 0


@pytest.mark.parametrize("label,delta", [
    ("0d", timedelta()), ("1d", timedelta(days=1)),
    ("2h", timedelta(hours=2)), ("1mo", timedelta(days=30)),
])
def test_relative_ages_share_reference_time(label, delta):
    reference = utc(2027, 1, 1, 1)
    assert _parse_age_label(label, reference) == int((reference - delta).timestamp())


def test_jobright_date_cutoff_and_internship_year_are_independent():
    readme = "\n".join(
        f"| Example | [Summer Intern 2028](https://example.com/{index}) | NYC | Hybrid | {date} |"
        for index, date in enumerate(["Dec 30", "Dec 31", "Jan 1"])
    )
    parsed = parse_jobright_readme(
        readme, start_timestamp=int(utc(2026, 12, 31).timestamp()), reference_time=utc(2027, 1, 2),
    )
    # Same identity dedupes to the first eligible row, whose date is the cutoff.
    assert len(parsed.summer) == 1
    assert parsed.summer[0].date_posted == int(utc(2026, 12, 31).timestamp())
    assert parsed.summer[0].job_year == "2028"


async def test_all_feeds_use_the_same_reference_clock(monkeypatch):
    client = GitHubClient()

    async def fetch(url, marker):
        if url == client.url:
            return "| JobrightCo | [Summer Intern 2027](https://example.com/jr) | NYC | Hybrid | Dec 31 |"
        season = "Summer" if url == client.simplify_summer_url else "Fall"
        return (
            "## Software Engineering Internship Roles\n<table><tr><td>Example</td>"
            f"<td>{season} Intern</td><td>SF</td><td>{season} 2027</td>"
            f'<td><a href="https://example.com/{season}">Apply</a></td><td>1d</td></tr></table>'
        )

    monkeypatch.setattr(client, "_fetch_url", fetch)
    parsed = await client.fetch_listings(reference_time=utc(2027, 1, 1))
    assert len(parsed.summer) == 2
    assert len(parsed.fall) == 1
    for listing in parsed.summer + parsed.fall:
        assert listing.date_posted == int(utc(2026, 12, 31).timestamp())


def test_timezone_is_normalized_and_naive_test_reference_means_utc():
    assert _parse_date_label("Dec 31", datetime(2027, 1, 1)) == int(utc(2026, 12, 31).timestamp())
    reference = datetime(2027, 1, 1, 1, tzinfo=timezone(timedelta(hours=2)))
    assert _parse_date_label("Dec 31", reference) == int(utc(2026, 12, 31).timestamp())
