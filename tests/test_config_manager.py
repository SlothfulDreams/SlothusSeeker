from types import SimpleNamespace

import pytest

from src.config import config_manager


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.filters = {}
        self.cursor = 0
        self.payload = None

    def select(self, columns):
        self.columns = columns.split(",")
        return self

    def order(self, column):
        assert column == "id"
        return self

    def limit(self, count):
        self.count = count
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def gt(self, key, value):
        assert key == "id"
        self.cursor = value
        return self

    def upsert(self, rows, on_conflict):
        self.payload = rows
        self.conflict_keys = on_conflict.split(",")
        return self

    def execute(self):
        self.client.calls.append(self)
        if len(self.client.calls) == self.client.fail_on_call:
            raise RuntimeError("database unavailable")
        if self.payload is not None:
            stored = self.client.rows[self.table]
            for row in self.payload:
                existing = next((item for item in stored if all(item[key] == row[key] for key in self.conflict_keys)), None)
                if existing is not None:
                    existing.update(row)
                else:
                    stored.append({"id": max((item["id"] for item in stored), default=0) + 1, **row})
            return SimpleNamespace(data=self.payload)
        rows = sorted(self.client.rows[self.table], key=lambda row: row["id"])
        matches = [
            row for row in rows
            if row["id"] > self.cursor
            and all(row[key] == value for key, value in self.filters.items())
        ]
        return SimpleNamespace(data=[
            {key: row[key] for key in self.columns}
            for row in matches[:min(self.count, self.client.cap)]
        ])


class FakeClient:
    def __init__(self, rows, cap=1000, fail_on_call=None):
        self.rows = rows
        self.cap = cap
        self.fail_on_call = fail_on_call
        self.calls = []

    def table(self, table):
        return FakeQuery(self, table)


def make_manager(monkeypatch, tmp_path, client):
    monkeypatch.setattr(config_manager, "CONFIG_FILE", tmp_path / "config.json")
    return config_manager.ConfigManager(supabase_client=client)


@pytest.mark.parametrize("count,cap", [(0, 500), (1, 500), (1501, 1000), (1000, 500), (17, 3)])
async def test_history_reads_all_pages_with_server_caps(monkeypatch, tmp_path, count, cap):
    rows = [
        {"id": index * 2, "job_id": f"job-{index}", "guild_id": "g1", "season": "summer"}
        for index in range(1, count + 1)
    ]
    rows += [{"id": 10001, "job_id": "foreign", "guild_id": "g2", "season": "summer"}]
    rows += [{"id": 10002, "job_id": "fall", "guild_id": "g1", "season": "fall"}]
    client = FakeClient({"posted_jobs": rows[::-1]}, cap=cap)
    manager = make_manager(monkeypatch, tmp_path, client)

    ids = await manager.get_posted_job_ids("g1", "summer")

    assert ids == {f"job-{index}" for index in range(1, count + 1)}
    assert client.calls[-1].cursor == count * 2
    assert all(call.filters == {"guild_id": "g1", "season": "summer"} for call in client.calls)


async def test_company_reads_include_all_pages(monkeypatch, tmp_path):
    rows = [{"id": index, "company_name": f" COMPANY {index} "} for index in range(1, 8)]
    manager = make_manager(monkeypatch, tmp_path, FakeClient({"companies": rows[::-1]}, cap=2))
    assert await manager.list_companies() == rows
    assert await manager.get_company_names() == {f"company {index}" for index in range(1, 8)}


async def test_compatible_history_reads_all_pages_and_scopes_rows(monkeypatch, tmp_path):
    rows = [
        {"id": index, "job_id": f"job-{index}", "guild_id": guild, "season": season,
         "url": f"https://example.com/{index}", "company_name": "Example", "title": "Intern", "job_year": "2026"}
        for index, guild, season in [(1, "g1", "summer"), (2, "g1", "summer"), (3, "g2", "summer"), (4, "g1", "fall")]
    ]
    manager = make_manager(monkeypatch, tmp_path, FakeClient({"posted_jobs": rows}, cap=1))
    history = await manager.get_posted_history("g1", "summer")
    assert history.ids == {"job-1", "job-2"}
    assert len(history.url_keys) == 2


@pytest.mark.parametrize("table", ["posted_jobs", "companies"])
async def test_page_failure_never_returns_partial_results(monkeypatch, tmp_path, table):
    rows = [
        {"id": 1, "job_id": "job", "guild_id": "g1", "season": "summer", "company_name": "Example"}
    ]
    client = FakeClient({table: rows}, cap=1, fail_on_call=2)
    manager = make_manager(monkeypatch, tmp_path, client)
    with pytest.raises(RuntimeError, match="database unavailable"):
        if table == "companies":
            await manager.get_company_names()
        else:
            await manager.get_posted_job_ids("g1", "summer")


async def test_end_to_end_legacy_history_merge_checkpoint_and_status(monkeypatch, tmp_path):
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock

    from src.bot.embeds import create_status_embed
    from src.scheduler import tasks
    from src.scraper.data_models import _normalize_location_v1, build_job_id
    from src.scraper.diagnostics import ScrapeMonitor
    from src.scraper.github_client import GitHubClient

    legacy_id = build_job_id(
        "Example", "Summer Software Intern 2027", ["New York, NY, United States"],
        location_normalizer=_normalize_location_v1,
    )
    rows = [{
        "id": 1, "job_id": legacy_id, "url": "https://older-source.com/job",
        "company_name": "Example", "title": "Summer Software Intern 2027", "job_year": "2027",
        "guild_id": "g1", "season": "summer",
    }]
    client = FakeClient({"posted_jobs": rows, "companies": [{"id": 1, "company_name": "example"}]}, cap=1)
    manager = make_manager(monkeypatch, tmp_path, client)
    manager.set_scrape_start_timestamp(1)
    monkeypatch.setattr(manager, "has_any_configured_channel", AsyncMock(return_value=True))

    async def destinations(season):
        return [{"guild_id": "g1", "channel_id": 123}] if season == "summer" else []

    monkeypatch.setattr(manager, "get_channel_destinations", destinations)

    async def fetch_url(self, url, _marker):
        if url == self.url:
            date = datetime.now(timezone.utc).strftime("%b %d")
            return (
                f"| Example | [Summer Software Intern 2027](https://jobright.ai/old) | NYC | Hybrid | {date} |\n"
                f"| Example | [Summer Data Engineer Intern 2027](https://jobright.ai/new) | San Francisco, CA, United States | Hybrid | {date} |"
            )
        roles = ["Software", "Data Engineer"] if url == self.simplify_summer_url else ["Data Engineer"]
        season = "Summer" if url == self.simplify_summer_url else "Fall"
        text = "## Software Engineering Internship Roles\n<table>"
        for role in roles:
            location = "New York, NY" if role == "Software" else "SF"
            text += (
                f"<tr><td>Example</td><td>{role} Intern 2027</td><td>{location}</td><td>{season} 2027</td>"
                f'<td><a href="https://example.com/{role.replace(" ", "-")}">Apply</a></td><td>0d</td></tr>'
            )
        return text + "</table>"

    monkeypatch.setattr(GitHubClient, "_fetch_url", fetch_url)
    events = []

    class Channel(tasks.discord.abc.Messageable):
        async def send(self, **kwargs):
            events.append(kwargs)

    bot = SimpleNamespace(scrape_monitor=ScrapeMonitor(), get_channel=lambda _id: Channel())
    monkeypatch.setattr(tasks.asyncio, "sleep", AsyncMock())
    result = await tasks.scrape_and_post(bot, manager)
    assert result.outcome == "success"
    assert result.already_posted == 1
    assert result.unconfigured == 1
    assert result.total_new == result.total_posted == result.recorded == 1
    assert result.sources["Simplify Summer"].cross_source_duplicates == 2
    assert len(rows) == 2  # Legacy history retained, only the new delivery written.
    assert rows[0]["job_id"] == legacy_id
    assert rows[1]["job_id"] == build_job_id("Example", "Summer Data Engineer Intern 2027", ["SF"])
    assert len(events) == 1
    assert "Source: Jobright" in events[0]["embed"].footer.text
    embed = create_status_embed(bot.scrape_monitor, scheduler_state="Running")
    assert "Sent: 1 · Recorded: 1" in next(field.value for field in embed.fields if field.name.startswith("Season/channel"))

    again = await tasks.scrape_and_post(bot, manager)
    assert again.total_posted == again.total_new == 0
    assert again.already_posted == 2
    assert len(events) == 1
    assert len(rows) == 2
