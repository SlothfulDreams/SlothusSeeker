import pytest

from src.scraper.data_models import detect_seasons
from src.scraper.github_client import parse_jobright_readme

SEASON_CASES = [
    ("Software Engineer Intern - 2026 Fall", ["fall"]),
    ("Software Engineer Intern - Winter 2026", ["spring"]),
    ("Spring and Summer 2026 SWE Intern", ["spring", "summer"]),
    ("Seasonal Programming Intern", []),
]
TESLA_FALL_TITLE = (
    "[Internship, Software Engineer, Service Engineering (Fall 2026)]"
    "(https://jobright.ai/jobs/1)"
)
TESLA_FALL_TITLE_UPPER = (
    "[INTERNSHIP, SOFTWARE ENGINEER, SERVICE ENGINEERING (FALL 2026)]"
    "(https://jobright.ai/jobs/1)"
)

README_SAMPLE_ROWS = [
    (
        "[Tesla](https://www.tesla.com)",
        TESLA_FALL_TITLE,
        "Palo Alto, CA",
        "On Site",
        "May 11",
    ),
    (
        "[pSemi, A Murata Company](https://www.psemi.com)",
        "[Intern, Software Development & Automation - Summer 2026](https://jobright.ai/jobs/2)",
        "San Diego, CA",
        "Hybrid",
        "May 12",
    ),
    (
        "[Generic Co](https://example.com)",
        "[Software Engineer Intern](https://jobright.ai/jobs/3)",
        "Remote",
        "Remote",
        "May 12",
    ),
    (
        "↳",
        "[Backend Development Engineer Intern - 2026 Fall](https://jobright.ai/jobs/4)",
        "San Jose, CA",
        "On Site",
        "May 12",
    ),
    (
        "[Snowflake](https://www.snowflake.com)",
        "[Software Engineer Intern - Winter 2026](https://jobright.ai/jobs/5)",
        "Remote",
        "Remote",
        "May 12",
    ),
    (
        "[Tesla](https://www.tesla.com)",
        TESLA_FALL_TITLE,
        "Palo Alto, CA",
        "On Site",
        "May 11",
    ),
    (
        "[TESLA](https://www.tesla.com)",
        TESLA_FALL_TITLE_UPPER,
        "Palo Alto, CA",
        "On Site",
        "May 11",
    ),
]
README_SAMPLE = "\n".join(
    [
        "## Daily Job List",
        "| Company | Job Title | Location | Work Model | Date Posted |",
        "| --- | --- | --- | --- | --- |",
        *[f"| {' | '.join(row)} |" for row in README_SAMPLE_ROWS],
    ]
)


def _company_names(jobs):
    return [job.company_name for job in jobs]


@pytest.mark.parametrize(
    ("title", "expected"),
    SEASON_CASES,
    ids=["fall", "winter-as-spring", "multi-season", "no-season"],
)
def test_detect_seasons_uses_case_insensitive_word_matches(title, expected):
    assert detect_seasons(title) == expected


def test_jobright_parser_routes_filters_and_dedupes_case_insensitively():
    parsed = parse_jobright_readme(README_SAMPLE)
    filtered = parsed.filter_by_companies(
        {" PSEMI,   A MURATA COMPANY ", "tesla", "snowflake"}
    )

    assert _company_names(parsed.fall) == ["Generic Co", "Tesla"]
    assert _company_names(parsed.spring) == ["Snowflake"]
    assert _company_names(parsed.summer) == ["pSemi, A Murata Company"]
    assert _company_names(filtered.fall) == ["Tesla"]
    assert _company_names(filtered.spring) == ["Snowflake"]
    assert _company_names(filtered.summer) == ["pSemi, A Murata Company"]
