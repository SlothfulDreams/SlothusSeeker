from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.config.config_manager import PostedJobHistory
from src.scheduler import tasks
from src.scraper.data_models import Internship, ScrapedData
from src.scraper.diagnostics import ScrapeMonitor, SourceStats
from src.scraper.github_client import GitHubClient, parse_jobright_readme, parse_simplify_readme

REFERENCE = datetime(2026, 5, 12, tzinfo=timezone.utc)
CUTOFF = int(datetime(2026, 5, 10, tzinfo=timezone.utc).timestamp())


@pytest.mark.parametrize("source", ["Jobright", "Simplify Off-Season"])
def test_source_rows_have_exclusive_filter_outcomes(source):
    rows = [
        ("Example", "Spring Summer Intern 2026", "NYC", "May 12", "0d", "https://example.com/good"),
        ("Example", "Spring Summer Intern 2026", "NYC", "May 12", "0d", "https://example.com/duplicate"),
        ("Example", "Summer Software Intern 2026", "NYC", "May 12", "0d", "https://example.com/second"),
        ("Other", "Summer Intern 2026", "NYC", "May 12", "0d", "https://example.com/company"),
        ("Example", "Summer Intern 2026", "Remote in Canada", "May 12", "0d", "https://example.com/location"),
        ("Example", "Software Intern", "NYC", "May 12", "0d", "https://example.com/season"),
        ("Example", "Summer Intern 2026", "NYC", "May 1", "30d", "https://example.com/date"),
        ("Example", "Summer Intern 2026", "NYC", "May 12", "0d", ""),
    ]
    diagnostics = SourceStats()
    if source == "Jobright":
        text = "| Company | Job Title | Location | Work Model | Date Posted |\n| --- | --- | --- | --- | --- |\n"
        text += "\n".join(
            f"| {company} | [{title}]({url}) | {location} | Hybrid | {date} |"
            for company, title, location, date, age, url in rows
        )
        text += "\n| broken | row |"
        data = parse_jobright_readme(text, CUTOFF, reference_time=REFERENCE, diagnostics=diagnostics, company_names={" example "})
    else:
        text = "## Software Engineering Internship Roles\n<table>"
        text += "".join(
            f'<tr><td>{company}</td><td>{title}</td><td>{location}</td><td><a href="{url}">Apply</a></td><td>{age}</td></tr>'
            for company, title, location, date, age, url in rows
        )
        text += "<tr><td>broken</td><td>row</td></tr></table>"
        data = parse_simplify_readme(text, source_name=source, start_timestamp=CUTOFF, reference_time=REFERENCE, diagnostics=diagnostics, company_names={" example "})
    assert diagnostics.parsed
    assert diagnostics.rows == 9
    assert diagnostics.malformed == 2
    assert diagnostics.no_season == 1
    assert diagnostics.location == 1
    assert diagnostics.old == 1
    assert diagnostics.company_filtered == 1
    assert diagnostics.duplicate_rows == 1
    assert diagnostics.eligible == 2
    assert data.total_count() == 3  # One row targets two seasons, not two source rows.
    assert "https://example.com/duplicate" in data.spring[0].source_urls


async def test_merged_season_duplicates_are_separate_from_source_row_counts(monkeypatch):
    client, sources = GitHubClient(), {}

    async def fetch(url, marker):
        if url == client.url:
            return "\n".join(
                f"| {company} | [Spring Summer Fall Software Intern 2026](https://jobright.ai/{company}) | NYC | Hybrid | May 12 |"
                for company in ("Example", "Other")
            )
        return "## Software Engineering Internship Roles\n<table>" + "".join(
            f'<tr><td>{company}</td><td>Software Intern 2026</td><td>New York, NY, United States</td><td>Spring Fall 2026</td><td><a href="https://example.com/{company}">Apply</a></td><td>0d</td></tr>'
            for company in ("Example", "Other")
        ) + "</table>"

    monkeypatch.setattr(client, "_fetch_url", fetch)
    data = await client.fetch_listings(reference_time=REFERENCE, company_names={"Example"}, diagnostics=sources)
    assert data.total_count() == 3
    for source in sources.values():
        assert source.rows == 2
        assert source.company_filtered == 1
        assert source.eligible == 1
    assert sources["Jobright"].cross_source_duplicates == 0
    assert sources["Simplify Summer"].cross_source_duplicates == 1
    assert sources["Simplify Off-Season"].cross_source_duplicates == 2


def bot_and_manager():
    bot = SimpleNamespace(scrape_monitor=ScrapeMonitor(), get_channel=lambda _id: None)
    manager = SimpleNamespace(
        has_any_configured_channel=AsyncMock(return_value=True),
        get_company_names=AsyncMock(return_value={"Example"}),
        get_scrape_start_timestamp=lambda: CUTOFF,
        get_channel_destinations=AsyncMock(return_value=[]),
        get_posted_history=AsyncMock(return_value=PostedJobHistory([])),
        record_posted_jobs=AsyncMock(),
    )
    return bot, manager


@pytest.mark.parametrize("missing", ["channels", "companies"])
async def test_skipped_runs_are_recorded_without_fetching(monkeypatch, missing):
    bot, manager = bot_and_manager()
    if missing == "channels":
        manager.has_any_configured_channel.return_value = False
    else:
        manager.get_company_names.return_value = set()
    monkeypatch.setattr(tasks, "GitHubClient", lambda: pytest.fail("must not fetch"))
    stats = await tasks.scrape_and_post(bot, manager)
    assert stats.outcome == "skipped"
    assert missing in stats.note
    assert stats.finished_at is not None
    assert bot.scrape_monitor.last_result is stats
    assert bot.scrape_monitor.last_success_at is None
    assert bot.scrape_monitor.active_runs == []


async def test_failure_retains_last_success_and_safe_error_summary(monkeypatch):
    bot, manager = bot_and_manager()
    monkeypatch.setattr(tasks, "_fetch_allowlisted_listings", AsyncMock(return_value=ScrapedData()))
    success = await tasks.scrape_and_post(bot, manager)
    assert success.outcome == "success"
    monkeypatch.setattr(tasks, "_fetch_allowlisted_listings", AsyncMock(side_effect=RuntimeError("private API details")))
    with pytest.raises(RuntimeError):
        await tasks.scrape_and_post(bot, manager)
    result = bot.scrape_monitor.last_result
    assert result.outcome == "failed"
    assert result.errors == 1
    assert "private API details" not in result.note
    assert bot.scrape_monitor.last_success_at == success.finished_at
    assert bot.scrape_monitor.active_runs == []


async def test_active_run_and_scheduled_run_share_monitor(monkeypatch):
    bot, manager = bot_and_manager()

    async def fetch(_manager, stats):
        assert bot.scrape_monitor.active_runs == [stats]
        assert stats.outcome == "running"
        return ScrapedData()

    monkeypatch.setattr(tasks, "_fetch_allowlisted_listings", fetch)
    cog = SimpleNamespace(bot=bot, config_manager=manager)
    await tasks.ScraperTasks.scrape_task.coro(cog)
    assert bot.scrape_monitor.last_result.outcome == "success"
    assert bot.scrape_monitor.active_runs == []
    assert ScrapeMonitor().last_result is None  # New process/session starts empty.


def sample_job():
    return Internship(id="job", company_name="Example", title="Summer Intern", url="https://example.com/job", locations=["NYC"])


async def test_missing_destination_and_missing_channel_are_reported(monkeypatch):
    bot, manager = bot_and_manager()
    data = ScrapedData(summer=[sample_job()], fall=[sample_job()])
    monkeypatch.setattr(tasks, "_fetch_allowlisted_listings", AsyncMock(return_value=data))

    async def destinations(season):
        return [{"guild_id": "guild", "channel_id": 123}] if season == "summer" else []

    manager.get_channel_destinations.side_effect = destinations
    stats = await tasks.scrape_and_post(bot, manager)
    assert stats.outcome == "partial"
    assert stats.errors == 1
    assert stats.unconfigured == 1
    assert stats.total_new == 1
    assert stats.total_posted == 0


async def test_unrecorded_delivery_is_visible_in_failed_run(monkeypatch):
    bot, manager = bot_and_manager()
    channel = AsyncMock(spec=tasks.discord.abc.Messageable)
    bot.get_channel = lambda _id: channel
    manager.get_channel_destinations.return_value = [{"guild_id": "guild", "channel_id": 123}]
    manager.record_posted_jobs.side_effect = RuntimeError("database unavailable")
    monkeypatch.setattr(tasks, "_fetch_allowlisted_listings", AsyncMock(return_value=ScrapedData(summer=[sample_job()])))
    with pytest.raises(tasks.DeliveryRecordingError):
        await tasks.scrape_and_post(bot, manager)
    stats = bot.scrape_monitor.last_result
    assert stats.total_posted == 1
    assert stats.recorded == 0
    assert stats.unrecorded == 1
    assert stats.errors == 1
    assert stats.outcome == "failed"
    assert "could not be recorded" in stats.note
    channel.send.assert_awaited_once()


async def test_fetch_failure_does_not_claim_sources_were_parsed(monkeypatch):
    client, sources = GitHubClient(), {}
    monkeypatch.setattr(client, "_fetch_url", AsyncMock(side_effect=RuntimeError("unavailable")))
    with pytest.raises(RuntimeError):
        await client.fetch_listings(diagnostics=sources)
    assert len(sources) == 3
    assert all(not source.parsed for source in sources.values())
