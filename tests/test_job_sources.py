"""Tests for job-ad source parsers and the fetch dispatcher's routing logic."""

from pathlib import Path

import pytest

from coverletterer.job_sources import detect_site, generic, indeed, seek
from coverletterer.job_sources.base import JobParseError

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_seek_parse_extracts_job_fields():
    posting = seek.parse(_read("seek_job.html"))
    assert posting.site == "seek"
    assert "Senior Platform Engineer" in posting.title
    assert posting.company == "iterate"
    assert len(posting.description) > 500


def test_indeed_parse_extracts_job_fields():
    posting = indeed.parse(_read("indeed_job.html"))
    assert posting.site == "indeed"
    assert posting.title == "Senior DevOps Engineer"
    assert posting.company == "PaperCut Software"
    assert len(posting.description) > 500


def test_seek_parse_raises_on_unrelated_html():
    with pytest.raises(JobParseError):
        seek.parse("<html><body><p>nothing here</p></body></html>")


def test_indeed_parse_raises_on_unrelated_html():
    with pytest.raises(JobParseError):
        indeed.parse("<html><body><p>nothing here</p></body></html>")


def test_generic_extract_text_strips_chrome():
    html = """
    <html><body>
      <nav>Site nav</nav>
      <script>var x = 1;</script>
      <main><h1>My Resume</h1><p>Experienced engineer.</p></main>
      <footer>Copyright</footer>
    </body></html>
    """
    text = generic.extract_text(html)
    assert "My Resume" in text
    assert "Experienced engineer." in text
    assert "Site nav" not in text
    assert "Copyright" not in text


def test_generic_parse_raises_on_empty_page():
    with pytest.raises(JobParseError):
        generic.parse("<html><body></body></html>")


@pytest.mark.parametrize(
    "url,expected_site",
    [
        ("https://au.seek.com/job/93856863", "seek"),
        ("https://seek.com/job/123", "seek"),
        ("https://au.indeed.com/viewjob?jk=abc", "indeed"),
        ("https://example.com/careers/some-role", "other"),
    ],
)
def test_detect_site_routes_by_domain(url, expected_site):
    assert detect_site(url) == expected_site
