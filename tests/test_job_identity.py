import pytest

from src.config.config_manager import PostedJobHistory
from src.scraper.data_models import (
    Internship, ScrapedData, _normalize_location_v1, build_job_id,
    build_legacy_job_ids, normalize_location,
)
from src.scraper.github_client import _merge_scraped_data, parse_jobright_readme, parse_simplify_readme


@pytest.mark.parametrize("location", [
    "San Jose, CA", "San Jose, California", "San Jose, CA, United States",
    "San Jose, California, USA", "San Jose, CA, U.S.", "San Jose, CA, U.S.A.",
])
def test_equivalent_locations_have_same_identity(location):
    assert normalize_location(location) == "san jose ca"
    assert build_job_id("Example", "Summer Intern 2026", [location]) == build_job_id(
        "Example", "Summer Intern 2026", ["San Jose, CA"]
    )


@pytest.mark.parametrize("location", ["Remote in USA", "Remote United States", "US (Remote)", "Remote - U.S.A."])
def test_remote_country_aliases(location):
    assert normalize_location(location) == "remote us"


def test_identity_preserves_distinct_locations_remote_and_years():
    ids = {
        build_job_id("Example", f"Summer Intern {year}", [location])
        for year in (2026, 2027)
        for location in ("San Jose, CA", "San Diego, CA", "Remote in USA", "United States")
    }
    assert len(ids) == 8
    assert build_job_id("Example", "Intern", ["NYC", "SF"]) == build_job_id(
        "Example", "Intern", ["SF", "New York, NY", "NYC"]
    )


def test_v1_hash_remains_unchanged():
    assert build_job_id(
        "Example", "Summer 2026 Software Intern", ["San Jose, CA, United States"],
        location_normalizer=_normalize_location_v1,
    ).startswith("33a7415cf4f21689")


def make_listing(location="San Jose, CA", url="https://example.com/new"):
    return Internship(
        id=build_job_id("Example", "Summer Intern 2026", [location]),
        company_name="Example", title="Summer Intern 2026", job_year="2026",
        locations=[location], url=url,
        legacy_ids=build_legacy_job_ids("Example", "Summer Intern 2026", [location]),
    )


@pytest.mark.parametrize("old_location,new_location", [
    ("San Jose, CA", "San Jose, California, United States"),
    ("San Jose, California, USA", "San Jose, CA"),
])
def test_old_ids_still_match_without_rewriting_history(old_location, new_location):
    old_id = build_job_id("Example", "Summer Intern 2026", [old_location], location_normalizer=_normalize_location_v1)
    history = PostedJobHistory([{"job_id": old_id}])
    assert history.contains(make_listing(new_location))
    assert history.ids == {old_id}


def test_merge_keeps_legacy_ids_and_all_source_urls():
    first = make_listing(url="https://jobright.ai/job")
    second = make_listing("San Jose, CA, United States", "https://example.com/apply")
    second.legacy_ids.add("older-source-id")
    target, source = ScrapedData(), ScrapedData()
    target.add(first)
    source.add(second)
    _merge_scraped_data(target, source)
    assert len(target.summer) == 1
    merged = target.summer[0]
    assert merged.url == first.url
    assert "older-source-id" in merged.legacy_ids
    assert second.url in merged.source_urls
    assert PostedJobHistory([{"job_id": "older-source-id"}]).contains(merged)
    assert PostedJobHistory([{
        "job_id": "unknown-id", "url": second.url, "company_name": "Example",
        "title": "Summer Intern 2026", "job_year": "2026",
    }]).contains(merged)


@pytest.mark.parametrize("field,value", [
    ("url", "https://different.com/job"), ("company_name", "Different"),
    ("title", "Summer Hardware Intern 2026"), ("job_year", "2027"),
])
def test_url_fallback_requires_matching_identity_fields(field, value):
    listing = make_listing()
    row = {"job_id": "unrelated-id", "url": listing.url, "company_name": "Example", "title": listing.title, "job_year": "2026"}
    row[field] = value
    assert not PostedJobHistory([row]).contains(listing)


def test_source_parsers_generate_compatible_ids():
    jobright = parse_jobright_readme(
        "| Example | [Summer Software Intern 2026](https://jobright.ai/job) | San Jose, CA, United States | On Site | May 12 |"
    )
    simplify = parse_simplify_readme(
        "## Software Engineering Internship Roles\n<table><tr><td>Example</td>"
        "<td>Software Intern</td><td>San Jose, California</td>"
        '<td><a href="https://example.com/apply">Apply</a></td><td>0d</td></tr></table>',
        source_name="Simplify Summer", default_seasons=["summer"], default_terms=["Summer 2026"],
    )
    assert jobright.summer[0].id == simplify.summer[0].id
    assert jobright.summer[0].legacy_ids
    assert simplify.summer[0].legacy_ids
    _merge_scraped_data(jobright, simplify)
    assert len(jobright.summer) == 1
