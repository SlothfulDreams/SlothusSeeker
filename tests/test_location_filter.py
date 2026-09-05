"""US-only policy shared by Jobright and both Simplify feeds."""

import pytest

from src.scraper.data_models import Internship, locations_are_us_only
from src.scraper.github_client import parse_jobright_readme, parse_simplify_readme


LOCATION_CASES = [
    ("New York, NY", True),
    ("San Francisco, California", True),
    ("Austin, TX, United States", True),
    ("Town and Country, MO, United States", True),
    ("Los Angeles, United States", True),
    ("Colorado, United States", True),
    ("Atlanta, GA", True),
    ("Washington, DC", True),
    ("Maryland", True),
    ("United States", True),
    ("United States of America", True),
    ("US", True),
    ("USA", True),
    ("U.S.", True),
    ("U.S.A.", True),
    ("NYC", True),
    ("SF", True),
    ("LA", True),
    ("South SF", True),
    ("Remote in USA", True),
    ("Remote United States", True),
    ("Remote - US", True),
    ("US (Remote)", True),
    ("Remote (US)", True),
    ("  remote in united states  ", True),
    ("Toronto, ON, Canada", False),
    ("Vancouver, British Columbia, Canada", False),
    ("London, UK", False),
    ("Cambridge, United Kingdom", False),
    ("Sydney, NSW, Australia", False),
    ("Bengaluru, India", False),
    ("Berlin, Germany", False),
    ("Remote in Canada", False),
    ("Remote in UK", False),
    ("US / Canada", False),
    ("San Francisco, CA; Toronto, ON, Canada", False),
    ("San Francisco, CA\nLondon, UK", False),
    ("San Francisco, CA; New York, NY", True),
    ("San Francisco, CA, Canada", False),
    ("London, Ontario, CA", False),
    ("Remote", False),
    ("Hybrid", False),
    ("Worldwide", False),
    ("North America", False),
    ("Georgia", False),
    ("CA", False),
    ("Austin", False),
    ("", False),
]


@pytest.mark.parametrize(("location", "expected"), LOCATION_CASES)
def test_us_only_location_policy(location, expected):
    assert locations_are_us_only([location]) is expected


@pytest.mark.parametrize(
    ("locations", "expected"),
    [
        ([], False),
        (["NYC", "SF"], True),
        (["NYC", "Toronto, ON, Canada"], False),
        (["NYC", "Remote"], False),
        (["NYC", ""], False),
    ],
)
def test_posting_eligibility_requires_all_locations_to_be_us(locations, expected):
    listing = Internship(
        id="test-id",
        company_name="Example",
        title="Summer Intern",
        url="https://example.com/job",
        locations=locations,
    )
    assert listing.should_be_posted() is expected


def _parse_source(source, location):
    location = location.replace("\n", "<br>")
    if source == "Jobright":
        return parse_jobright_readme(
            "| Company | Job Title | Location | Work Model | Date Posted |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| Example | [Spring Summer Fall Intern](https://example.com/job) "
            f"| {location} | Remote | May 12 |"
        )
    return parse_simplify_readme(
        "## Software Engineering Internship Roles\n"
        "<table><tr><td>Example</td><td>Software Intern</td>"
        f"<td>{location}</td><td>Spring Summer Fall 2026</td>"
        '<td><a href="https://example.com/job">Apply</a></td>'
        "<td>0d</td></tr></table>",
        source_name=source,
        default_seasons=["summer"] if source == "Simplify Summer" else None,
    )


@pytest.mark.parametrize("source", ["Jobright", "Simplify Summer", "Simplify Off-Season"])
@pytest.mark.parametrize(
    ("location", "expected"),
    [
        *LOCATION_CASES,
        ("NYC<br>SF", True),
        ("NYC<br/>Toronto, ON, Canada", False),
        ("Toronto, ON, Canada<br />NYC", False),
    ],
)
def test_all_feeds_enforce_us_only_in_every_season(source, location, expected):
    parsed = _parse_source(source, location)
    seasons = ["summer"] if source == "Simplify Summer" else ["spring", "summer", "fall"]
    for season in seasons:
        listings = getattr(parsed, season)
        assert len(listings) == int(expected)
        if expected:
            assert listings[0].source == source


def test_jobright_keeps_country_separate_from_work_model_and_date():
    parsed = _parse_source("Jobright", "Remote in USA")
    listing = parsed.summer[0]
    assert listing.locations == ["Remote in USA"]
    assert listing.work_model == "Remote"
    assert listing.date_posted_label == "May 12"


def test_jobright_missing_work_model_does_not_put_date_in_location():
    parsed = parse_jobright_readme(
        "| Example | [Summer Intern](https://example.com/job) | New York, NY | | May 12 |"
    )
    assert parsed.summer[0].locations == ["New York, NY"]
    assert parsed.summer[0].date_posted_label == "May 12"


@pytest.mark.parametrize("source", ["Jobright", "Simplify Summer", "Simplify Off-Season"])
def test_filtering_foreign_row_preserves_company_for_continuation_row(source):
    if source == "Jobright":
        parsed = parse_jobright_readme(
            "| Example | [Summer Intern](https://example.com/foreign) | Canada | Remote | May 12 |\n"
            "| ↳ | [Summer Intern](https://example.com/us) | NYC | Hybrid | May 12 |"
        )
    else:
        parsed = parse_simplify_readme(
            "## Software Engineering Internship Roles\n"
            "<table><tr><td>Example</td><td>Summer Intern</td><td>Canada</td>"
            '<td><a href="https://example.com/foreign">Apply</a></td><td>0d</td></tr>'
            "<tr><td>↳</td><td>Summer Intern</td><td>NYC</td>"
            '<td><a href="https://example.com/us">Apply</a></td><td>0d</td></tr></table>',
            source_name=source,
        )
    assert len(parsed.summer) == 1
    assert parsed.summer[0].company_name == "Example"
    assert parsed.summer[0].url == "https://example.com/us"
