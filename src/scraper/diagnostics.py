"""Small, in-memory summaries; no persistent scrape history or retry policy."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.scraper.data_models import SEASONS


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SourceStats:
    parsed: bool = False
    rows: int = 0
    malformed: int = 0
    no_season: int = 0
    location: int = 0
    old: int = 0
    duplicate_rows: int = 0
    company_filtered: int = 0
    cross_source_duplicates: int = 0
    eligible: int = 0


@dataclass
class ScrapeStats:
    started_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None
    outcome: str = "running"
    note: str = ""
    sources: dict[str, SourceStats] = field(default_factory=dict)
    posted_by_season: dict[str, int] = field(default_factory=lambda: dict.fromkeys(SEASONS, 0))
    total_new: int = 0
    recorded: int = 0
    unrecorded: int = 0
    already_posted: int = 0
    unconfigured: int = 0
    errors: int = 0

    @property
    def total_posted(self) -> int:
        return sum(self.posted_by_season.values())

    @property
    def duration_seconds(self) -> float:
        return max(0, ((self.finished_at or utcnow()) - self.started_at).total_seconds())


@dataclass
class ScrapeMonitor:
    active_runs: list[ScrapeStats] = field(default_factory=list)
    last_result: ScrapeStats | None = None
    last_success_at: datetime | None = None

    def begin(self) -> ScrapeStats:
        stats = ScrapeStats()
        self.active_runs.append(stats)
        return stats

    def finish(self, stats: ScrapeStats) -> None:
        stats.finished_at = utcnow()
        self.active_runs = [run for run in self.active_runs if run is not stats]
        self.last_result = stats
        if stats.outcome == "success":
            self.last_success_at = stats.finished_at
