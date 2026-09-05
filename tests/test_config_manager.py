from types import SimpleNamespace

import pytest

from src.config import config_manager


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.filters = {}
        self.cursor = 0

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

    def execute(self):
        self.client.calls.append(self)
        if len(self.client.calls) == self.client.fail_on_call:
            raise RuntimeError("database unavailable")
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
