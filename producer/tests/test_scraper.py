import pytest
from unittest.mock import patch

from src.scraper import (
    PositionScraper,
    normalize_title,
    strip_view_position_suffix,
    ScraperError,
)


SAMPLE_HTML = """
<html>
<body>
  <ul>
    <li><a href="/career/backend-engineer">
      <div>Backend Engineer</div>
      <div>View Position</div>
    </a></li>
    <li><a href="/career/senior-frontend">
      <div>Senior Frontend Developer</div>
      <div>View Position</div>
    </a></li>
    <li><a href="/career/office-manager">
      <div>Office Manager</div>
      <div>View Position</div>
    </a></li>
  </ul>
</body>
</html>
"""

EMPTY_HTML = "<html><body><p>No positions available</p></body></html>"


def make_scraper(**kwargs):
    defaults = {"url": "https://example.com/careers", "timeout": 30, "retries": 3}
    return PositionScraper(**{**defaults, **kwargs})


class TestNormalizeTitle:
    def test_strips_whitespace(self):
        assert normalize_title("  Backend Engineer  ") == "Backend Engineer"

    def test_collapses_multiple_spaces(self):
        assert normalize_title("Backend   Engineer") == "Backend Engineer"

    def test_handles_tabs_and_newlines(self):
        assert normalize_title("Backend\n\tEngineer") == "Backend Engineer"

    def test_empty_string(self):
        assert normalize_title("") == ""


class TestStripViewPositionSuffix:
    def test_strips_trailing_cta(self):
        assert strip_view_position_suffix("Backend Engineer View Position") == "Backend Engineer"

    def test_keeps_title_when_no_cta(self):
        assert strip_view_position_suffix("Backend Engineer") == "Backend Engineer"


class TestParsePositions:
    def test_extracts_positions(self):
        scraper = make_scraper()
        positions = scraper._parse_positions(SAMPLE_HTML)
        assert len(positions) == 3
        assert "Backend Engineer" in positions
        assert "Senior Frontend Developer" in positions
        assert "Office Manager" in positions

    def test_excludes_view_position_text(self):
        scraper = make_scraper()
        positions = scraper._parse_positions(SAMPLE_HTML)
        assert "View Position" not in positions

    def test_prefers_link_text_span_when_present(self):
        html = """
        <html><body>
          <a href="/career/account-manager-2/">
            <div class="d-flex align-items-center justify-content-between fade-in">
              <span class="link-text">Account Manager</span>
              <div class="btn btn-outline-secondary btn-rounded">
                <span class="btn-label-wrap">
                  <span class="btn-label" data-text="View Position">View Position</span>
                </span>
              </div>
            </div>
          </a>
        </body></html>
        """
        scraper = make_scraper()
        positions = scraper._parse_positions(html)
        assert positions == ["Account Manager"]

    def test_handles_combined_title_and_cta_text(self):
        html = """
        <html><body>
          <a href="/career/backend-engineer">Backend Engineer View Position</a>
        </body></html>
        """
        scraper = make_scraper()
        positions = scraper._parse_positions(html)
        assert positions == ["Backend Engineer"]

    def test_empty_html_returns_empty_list(self):
        scraper = make_scraper()
        positions = scraper._parse_positions(EMPTY_HTML)
        assert positions == []


class TestScrapePositions:
    def test_returns_sorted_positions(self):
        scraper = make_scraper()
        with patch.object(scraper, "_fetch_page", return_value=SAMPLE_HTML):
            positions = scraper.scrape()

        assert positions == [
            "Backend Engineer",
            "Office Manager",
            "Senior Frontend Developer",
        ]

    def test_raises_on_empty_results(self):
        scraper = make_scraper()
        with patch.object(scraper, "_fetch_page", return_value=EMPTY_HTML):
            with pytest.raises(ScraperError, match="No positions found"):
                scraper.scrape()

    def test_raises_on_fetch_failure(self):
        scraper = make_scraper()
        with patch.object(scraper, "_fetch_page", side_effect=Exception("Network error")):
            with pytest.raises(ScraperError, match="Failed to fetch"):
                scraper.scrape()
