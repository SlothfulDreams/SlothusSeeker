import pytest

from src.config.config_manager import PostedJobHistory, _posted_job_row
from src.scheduler import tasks
from src.scraper.data_models import Internship, ScrapedData

GUILD_ID = "guild-1"
CHANNEL_ID = 123


def _internship(job_id: str, title: str) -> Internship:
    return Internship(
        id=job_id,
        company_name="Tesla",
        title=title,
        url=f"https://jobright.ai/jobs/{job_id}",
        job_year="2026",
    )


class FakeConfigManager:
    def __init__(self, posted_ids=None):
        self.posted_ids = posted_ids or {}
        self.recorded_jobs = []

    async def get_channel_destinations(self, season):
        if season == "summer":
            return [{"guild_id": GUILD_ID, "channel_id": CHANNEL_ID}]
        return []

    async def get_posted_history(self, guild_id, season):
        return PostedJobHistory([
            {"job_id": job_id}
            for job_id in self.posted_ids.get((guild_id, season), set())
        ])

    async def record_posted_jobs(self, guild_id, season, channel_id, internships):
        self.recorded_jobs.append(
            {
                "guild_id": guild_id,
                "season": season,
                "channel_id": channel_id,
                "job_ids": [internship.id for internship in internships],
            }
        )


class FakeChannel(tasks.discord.abc.Messageable):
    def __init__(self):
        self.sent_messages = []

    async def send(self, **kwargs):
        self.sent_messages.append(kwargs)


class FakeBot:
    def __init__(self, channel):
        self.channel = channel

    def get_channel(self, _channel_id):
        return self.channel


def _scraped_data(*internships: Internship) -> ScrapedData:
    data = ScrapedData()
    for internship in internships:
        data.add(internship)
    return data


def _stub_scrape_source(monkeypatch, listings: ScrapedData) -> None:
    async def fake_fetch_allowlisted_listings(_config_manager):
        return listings

    async def fake_post_internships(_bot, _season, _channel_id, internships):
        return list(internships), 0

    monkeypatch.setattr(
        tasks,
        "_fetch_allowlisted_listings",
        fake_fetch_allowlisted_listings,
    )
    monkeypatch.setattr(tasks, "_post_internships", fake_post_internships)


@pytest.mark.asyncio
async def test_scrape_records_only_posted_configured_destinations(monkeypatch):
    _stub_scrape_source(
        monkeypatch,
        _scraped_data(
            _internship("summer-1", "Summer 2026 Intern"),
            _internship("fall-1", "Fall 2026 Intern"),
        ),
    )

    config_manager = FakeConfigManager()
    stats = await tasks.scrape_and_post(object(), config_manager)

    assert stats.posted_by_season["summer"] == 1
    assert stats.posted_by_season["fall"] == 0
    assert config_manager.recorded_jobs == [
        {
            "guild_id": GUILD_ID,
            "season": "summer",
            "channel_id": CHANNEL_ID,
            "job_ids": ["summer-1"],
        }
    ]


@pytest.mark.asyncio
async def test_scrape_skips_jobs_already_recorded_in_supabase(monkeypatch):
    _stub_scrape_source(
        monkeypatch,
        _scraped_data(_internship("summer-1", "Summer 2026 Intern")),
    )

    config_manager = FakeConfigManager(
        posted_ids={(GUILD_ID, "summer"): {"summer-1"}}
    )
    stats = await tasks.scrape_and_post(object(), config_manager)

    assert stats.total_new == 0
    assert stats.posted_by_season["summer"] == 0
    assert config_manager.recorded_jobs == []


@pytest.mark.asyncio
async def test_post_internships_mentions_everyone(monkeypatch):
    channel = FakeChannel()
    internship = _internship("summer-1", "Summer 2026 Intern")

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(tasks.asyncio, "sleep", fake_sleep)
    posted, errors = await tasks._post_internships(
        FakeBot(channel),
        "summer",
        CHANNEL_ID,
        [internship],
    )

    assert posted == [internship]
    assert errors == 0
    assert channel.sent_messages[0]["content"] == "@everyone"
    assert channel.sent_messages[0]["allowed_mentions"].everyone is True


def test_posted_job_row_includes_job_year():
    row = _posted_job_row(GUILD_ID, "summer", CHANNEL_ID, _internship("job-1", "Title"))

    assert row["job_year"] == "2026"
