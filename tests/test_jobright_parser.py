import pytest

from src.scraper.data_models import build_job_id, detect_seasons, normalize_location
from src.scraper.github_client import (
    _default_terms_from_source,
    parse_jobright_readme,
    parse_simplify_readme,
)

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
        "Remote in USA",
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
    assert parsed.summer[0].job_year == "2026"


def test_job_id_normalizes_cross_source_identity_fields():
    jobright_id = build_job_id(
        company_name="TESLA",
        title="Software Engineer Intern - Summer 2026",
        locations=["NYC"],
    )
    simplify_id = build_job_id(
        company_name="Tesla",
        title="Software Engineer",
        locations=["New York, NY"],
        terms=["Summer 2026"],
    )

    assert jobright_id == simplify_id

    winter_jobright_id = build_job_id(
        company_name="Cisco",
        title="AI Machine Learning Engineer Intern - Winter 2026",
        locations=["San Jose, CA"],
    )
    winter_simplify_id = build_job_id(
        company_name="Cisco",
        title="AI Machine Learning Engineer",
        locations=["San Jose, CA"],
        terms=["Winter 2026"],
    )

    assert winter_jobright_id == winter_simplify_id

    next_year_id = build_job_id(
        company_name="Cisco",
        title="AI Machine Learning Engineer",
        locations=["San Jose, CA"],
        terms=["Winter 2027"],
    )

    assert next_year_id != winter_simplify_id

    title_year_wins_id = build_job_id(
        company_name="Cisco",
        title="AI Machine Learning Engineer Intern - Winter 2027",
        locations=["San Jose, CA"],
        terms=["Winter 2026"],
    )

    assert title_year_wins_id == next_year_id


def test_default_terms_come_from_readme_title_or_source_url():
    simplify_readme = "# Summer 2027 Tech Internships by Pitt CSC & Simplify"
    jobright_readme = "# Daily Intern Jobs in Software Engineering by Jobright.ai"
    jobright_url = (
        "https://raw.githubusercontent.com/jobright-ai/"
        "2028-Software-Engineer-Internship/master/README.md"
    )

    assert _default_terms_from_source(
        simplify_readme,
        "https://github.com/SimplifyJobs/Summer2027-Internships",
        season="Summer",
    ) == ["Summer 2027"]
    assert _default_terms_from_source(jobright_readme, jobright_url) == ["2028"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("NYC", "new york ny"),
        ("New York, NY", "new york ny"),
        ("New York, New York", "new york ny"),
        ("SF", "san francisco ca"),
        ("San Francisco, CA", "san francisco ca"),
        ("San Francisco, California", "san francisco ca"),
        ("California", "ca"),
        ("National Harbor, Maryland", "national harbor md"),
        ("United States", "us"),
        ("Remote in USA", "remote us"),
        ("Remote United States", "remote us"),
    ],
)
def test_normalize_location_handles_common_source_variants(raw, expected):
    assert normalize_location(raw) == expected


def test_simplify_summer_parser_only_reads_target_sections_and_routes_summer():
    simplify_readme = """
## Software Engineering Internship Roles
<table><tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/Tesla">Tesla</a></strong></td>
<td>Software Engineer Intern</td>
<td>NYC</td>
<td><a href="https://tesla.com/apply">Apply</a></td>
<td>0d</td>
</tr>
<tr>
<td>↳</td>
<td>Backend Engineer Intern</td>
<td>Remote in USA</td>
<td><a href="https://tesla.com/backend">Apply</a></td>
<td>1d</td>
</tr>
</tbody></table>
## Product Management Internship Roles
<table><tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/Tesla">Tesla</a></strong></td>
<td>Product Manager Intern</td>
<td>NYC</td>
<td><a href="https://tesla.com/pm">Apply</a></td>
<td>0d</td>
</tr>
</tbody></table>
## Data Science, AI & Machine Learning Internship Roles
<table><tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/OpenAI">OpenAI</a></strong></td>
<td>Machine Learning Intern</td>
<td>SF</td>
<td><a href="https://openai.com/ml">Apply</a></td>
<td>0d</td>
</tr>
</tbody></table>
## Hardware Engineering Internship Roles
<table><tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/Acme">Acme</a></strong></td>
<td>Hardware Intern</td>
<td>Austin, TX</td>
<td><a href="https://acme.com/hw">Apply</a></td>
<td>0d</td>
</tr>
</tbody></table>
"""

    parsed = parse_simplify_readme(
        simplify_readme,
        source_name="Simplify Summer",
        default_seasons=["summer"],
    )

    assert sorted(_company_names(parsed.summer)) == ["OpenAI", "Tesla", "Tesla"]
    assert parsed.fall == []
    assert parsed.spring == []


def test_simplify_results_filter_by_configured_companies():
    simplify_readme = """
## Software Engineering Internship Roles
<table><tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/Tesla">Tesla</a></strong></td>
<td>Software Engineer Intern</td>
<td>NYC</td>
<td><a href="https://tesla.com/apply">Apply</a></td>
<td>0d</td>
</tr>
<tr>
<td><strong><a href="https://simplify.jobs/c/OpenAI">OpenAI</a></strong></td>
<td>Machine Learning Intern</td>
<td>SF</td>
<td><a href="https://openai.com/ml">Apply</a></td>
<td>0d</td>
</tr>
</tbody></table>
"""

    parsed = parse_simplify_readme(
        simplify_readme,
        source_name="Simplify Summer",
        default_seasons=["summer"],
    )
    filtered = parsed.filter_by_companies({" openai "})

    assert _company_names(filtered.summer) == ["OpenAI"]


def test_simplify_off_season_parser_uses_terms_for_channel_routing():
    simplify_readme = """
## Software Engineering Internship Roles
<table><tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/Nvidia">NVIDIA</a></strong></td>
<td>Software Engineer Intern</td>
<td>Santa Clara, CA</td>
<td>Fall 2026</td>
<td><a href="https://nvidia.com/fall">Apply</a></td>
<td>0d</td>
</tr>
<tr>
<td><strong><a href="https://simplify.jobs/c/Cisco">Cisco</a></strong></td>
<td>AI Machine Learning Engineer Intern</td>
<td>San Jose, CA</td>
<td>Winter 2026, Spring 2026</td>
<td><a href="https://cisco.com/winter">Apply</a></td>
<td>0d</td>
</tr>
</tbody></table>
## Quantitative Finance Internship Roles
<table><tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/Acme">Acme</a></strong></td>
<td>Quant Intern</td>
<td>NYC</td>
<td>Fall 2026</td>
<td><a href="https://acme.com/quant">Apply</a></td>
<td>0d</td>
</tr>
</tbody></table>
"""

    parsed = parse_simplify_readme(
        simplify_readme,
        source_name="Simplify Off-Season",
    )

    assert _company_names(parsed.fall) == ["NVIDIA"]
    assert _company_names(parsed.spring) == ["Cisco"]
    assert parsed.fall[0].job_year == "2026"
    assert parsed.spring[0].job_year == "2026"
    assert parsed.summer == []
