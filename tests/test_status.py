from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.bot.bot import InternshipBot
from src.bot.commands.config import ConfigCommands
from src.bot.embeds import create_status_embed
from src.scraper.diagnostics import ScrapeMonitor, SourceStats


def fields(embed):
    return {field.name: field.value for field in embed.fields}


def interaction(guild=True):
    return SimpleNamespace(
        guild=SimpleNamespace(name="Private") if guild else None,
        guild_id=123 if guild else None,
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock(), is_done=lambda: True),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def test_startup_and_unavailable_scheduler_are_explicit():
    embed = create_status_embed(ScrapeMonitor(), scheduler_state="Unavailable")
    assert embed.description == "No completed scrape this session."
    assert fields(embed)["Activity"] == "Idle"
    assert fields(embed)["Last successful scrape"] == "None this session"
    assert "Not scheduled" in fields(embed)["Scheduler"]
    assert "reset" in embed.footer.text


@pytest.mark.parametrize("outcome", ["success", "partial", "failed", "skipped", "interrupted"])
def test_latest_outcome_and_row_delivery_units(outcome):
    monitor = ScrapeMonitor()
    stats = monitor.begin()
    stats.outcome = outcome
    stats.note = "Safe summary"
    stats.sources = {"Jobright": SourceStats(parsed=True, rows=10, eligible=2, location=3, company_filtered=4, duplicate_rows=1, cross_source_duplicates=2)}
    stats.posted_by_season["summer"] = 2
    stats.posted_by_season["spring"] = 1
    stats.recorded = 2
    stats.unrecorded = 1
    stats.already_posted = 3
    stats.unconfigured = 1
    monitor.finish(stats)
    embed = create_status_embed(monitor, scheduler_state="Running", next_iteration=datetime.now(timezone.utc))
    values = fields(embed)
    assert outcome.title() in values["Latest completed scrape"]
    assert "Rows: 10 · Eligible: 2" in values["Jobright — source rows"]
    assert "Cross-source duplicate season entries: 2" in values["Jobright — source rows"]
    assert "Sent: 3 · Recorded: 2" in values["Season/channel deliveries (not source rows)"]
    assert "Sent but recording failed: 1" in values["Season/channel deliveries (not source rows)"]
    assert len(embed) < 6000
    assert all(len(field.value) <= 1024 for field in embed.fields)


def test_running_activity_does_not_overwrite_last_completed_result():
    monitor = ScrapeMonitor()
    completed = monitor.begin()
    completed.outcome = "success"
    monitor.finish(completed)
    monitor.begin()
    embed = create_status_embed(monitor, scheduler_state="Running")
    assert "1 scrape(s) running" in fields(embed)["Activity"]
    assert "Success" in fields(embed)["Latest completed scrape"]
    assert "None this session" != fields(embed)["Last successful scrape"]


def test_unparsed_source_and_long_note_are_safe_to_render():
    monitor = ScrapeMonitor()
    stats = monitor.begin()
    stats.sources["Jobright"] = SourceStats()
    stats.outcome = "failed"
    stats.note = "x" * 2000
    monitor.finish(stats)
    embed = create_status_embed(monitor, scheduler_state="Stopped (failed)")
    assert fields(embed)["Jobright — source rows"] == "Not parsed."
    assert len(fields(embed)["Latest completed scrape"]) == 1024


@pytest.mark.parametrize("state", ["running", "stopped", "failed", "unavailable"])
async def test_status_command_is_ephemeral_and_does_not_access_database(state):
    loop = SimpleNamespace(
        failed=lambda: state == "failed",
        is_running=lambda: state == "running",
        next_iteration=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    bot = SimpleNamespace(
        scrape_monitor=ScrapeMonitor(),
        get_cog=lambda _name: None if state == "unavailable" else SimpleNamespace(scrape_task=loop),
    )
    manager = Mock()
    cog = ConfigCommands(bot, manager)
    request = interaction()
    await cog.status.callback(cog, request)
    request.response.defer.assert_awaited_once_with(ephemeral=True)
    assert manager.mock_calls == []
    kwargs = request.followup.send.call_args.kwargs
    assert kwargs["ephemeral"] is True
    scheduler = fields(kwargs["embed"])["Scheduler"]
    assert {"running": "Running", "stopped": "Stopped", "failed": "Stopped (failed)", "unavailable": "Unavailable"}[state] in scheduler
    if state != "running":
        assert "Not scheduled" in scheduler


async def test_status_command_handles_dm_context():
    cog = ConfigCommands(SimpleNamespace(), Mock())
    request = interaction(guild=False)
    await cog.status.callback(cog, request)
    request.response.send_message.assert_awaited_once()
    assert request.response.send_message.call_args.kwargs["ephemeral"] is True
    request.response.defer.assert_not_awaited()


async def test_status_error_response_does_not_expose_exception():
    bot = SimpleNamespace(get_cog=Mock(side_effect=RuntimeError("secret details")))
    cog = ConfigCommands(bot, Mock())
    request = interaction()
    await cog.status.callback(cog, request)
    message = request.followup.send.call_args.args[0]
    assert "secret details" not in message
    assert "loading scraper status" in message


async def test_command_is_registered_without_sync_or_network():
    bot = InternshipBot(SimpleNamespace())
    try:
        await bot.add_cog(ConfigCommands(bot, bot.config_manager))
        assert bot.tree.get_command("status") is not None
        assert bot.scrape_monitor.last_result is None
    finally:
        await bot.close()


async def test_manual_scrape_uses_shared_monitor_for_skipped_runs():
    bot = SimpleNamespace(scrape_monitor=ScrapeMonitor())
    manager = SimpleNamespace(has_any_configured_channel=AsyncMock(return_value=False))
    cog = ConfigCommands(bot, manager)
    request = interaction()
    await cog.scrape_now.callback(cog, request)
    assert bot.scrape_monitor.last_result.outcome == "skipped"
    assert "Scrape skipped" in request.followup.send.call_args.args[0]
    assert request.followup.send.call_args.kwargs["ephemeral"] is True
