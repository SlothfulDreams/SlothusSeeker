import asyncio

import pytest

from src.config.config_manager import PostedJobHistory
from src.scheduler import tasks
from src.scraper.data_models import Internship, ScrapedData
from src.scraper.diagnostics import ScrapeMonitor


class Channel(tasks.discord.abc.Messageable):
    def __init__(self, events, fail_url=None):
        self.events = events
        self.fail_url = fail_url

    async def send(self, **kwargs):
        url = kwargs["embed"].url
        if url == self.fail_url:
            raise RuntimeError("send failed")
        self.events.append(("send", url))


class Manager:
    def __init__(self, events, fail_record=False):
        self.events = events
        self.fail_record = fail_record
        self.ids = set()

    async def record_posted_jobs(self, guild_id, season, channel_id, internships):
        assert len(internships) == 1
        job = internships[0]
        if self.fail_record:
            raise RuntimeError("database unavailable")
        self.ids.add(job.id)
        self.events.append(("record", job.id))

    async def has_any_configured_channel(self):
        return True

    async def get_posted_history(self, guild_id, season):
        return PostedJobHistory([{"job_id": job_id} for job_id in self.ids])

    async def get_channel_destinations(self, season):
        return [{"guild_id": "guild", "channel_id": 123}] if season == "summer" else []


class Bot:
    def __init__(self, channel):
        self.channel = channel
        self.scrape_monitor = ScrapeMonitor()

    def get_channel(self, channel_id):
        return self.channel


def listings():
    return [Internship(
        id=f"job-{index}", company_name="Example", title="Summer Intern",
        locations=["NYC"], url=f"https://example.com/{index}",
    ) for index in (1, 2)]


async def test_each_send_is_recorded_before_delay_and_next_message(monkeypatch):
    events = []

    async def sleep(_seconds):
        events.append(("sleep", None))

    monkeypatch.setattr(tasks.asyncio, "sleep", sleep)
    jobs = listings()
    posted, errors = await tasks._post_internships(
        Bot(Channel(events)), "summer", 123, jobs,
        config_manager=Manager(events), guild_id="guild",
    )
    assert posted == jobs
    assert errors == 0
    assert events == [
        ("send", jobs[0].url), ("record", jobs[0].id), ("sleep", None),
        ("send", jobs[1].url), ("record", jobs[1].id), ("sleep", None),
    ]


async def test_failed_send_is_not_recorded_and_next_job_can_post(monkeypatch):
    async def sleep(_seconds):
        pass

    monkeypatch.setattr(tasks.asyncio, "sleep", sleep)
    events, jobs = [], listings()
    manager = Manager(events)
    posted, errors = await tasks._post_internships(
        Bot(Channel(events, fail_url=jobs[0].url)), "summer", 123, jobs,
        config_manager=manager, guild_id="guild",
    )
    assert posted == [jobs[1]]
    assert errors == 1
    assert manager.ids == {jobs[1].id}


async def test_record_failure_stops_batch_without_resending_or_delaying(monkeypatch):
    async def sleep(_seconds):
        pytest.fail("must not continue after an unrecorded delivery")

    monkeypatch.setattr(tasks.asyncio, "sleep", sleep)
    events, jobs = [], listings()
    with pytest.raises(tasks.DeliveryRecordingError, match="Remaining batch stopped"):
        await tasks._post_internships(
            Bot(Channel(events)), "summer", 123, jobs,
            config_manager=Manager(events, fail_record=True), guild_id="guild",
        )
    assert events == [("send", jobs[0].url)]


async def test_interrupted_batch_skips_checkpointed_delivery_on_next_scrape(monkeypatch):
    events, jobs = [], listings()
    manager, bot = Manager(events), Bot(Channel(events))
    data = ScrapedData(summer=jobs)

    async def fetch(_manager, _stats):
        return data

    async def interrupt(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(tasks, "_fetch_allowlisted_listings", fetch)
    monkeypatch.setattr(tasks.asyncio, "sleep", interrupt)
    with pytest.raises(asyncio.CancelledError):
        await tasks.scrape_and_post(bot, manager)
    assert manager.ids == {jobs[0].id}
    assert bot.scrape_monitor.last_result.outcome == "interrupted"
    assert bot.scrape_monitor.last_result.recorded == 1
    assert bot.scrape_monitor.last_result.total_posted == 1
    assert bot.scrape_monitor.active_runs == []

    async def sleep(_seconds):
        pass

    monkeypatch.setattr(tasks.asyncio, "sleep", sleep)
    result = await tasks.scrape_and_post(bot, manager)
    assert result.total_posted == 1
    assert result.already_posted == 1
    assert result.outcome == "success"
    assert bot.scrape_monitor.last_success_at == result.finished_at
    assert [event for event in events if event[0] == "send"] == [
        ("send", job.url) for job in jobs
    ]
    assert manager.ids == {job.id for job in jobs}
