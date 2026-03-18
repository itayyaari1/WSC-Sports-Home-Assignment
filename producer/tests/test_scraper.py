import pytest
from unittest.mock import patch

from src.scraper import (
    parse_positions,
    normalize_title,
    strip_view_position_suffix,
    scrape_positions,
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
        positions = parse_positions(SAMPLE_HTML)
        assert len(positions) == 3
        assert "Backend Engineer" in positions
        assert "Senior Frontend Developer" in positions
        assert "Office Manager" in positions

    def test_excludes_view_position_text(self):
        positions = parse_positions(SAMPLE_HTML)
        assert "View Position" not in positions

    def test_handles_combined_title_and_cta_text(self):
        html = """
        <html><body>
          <a href="/career/backend-engineer">Backend Engineer View Position</a>
        </body></html>
        """
        positions = parse_positions(html)
        assert positions == ["Backend Engineer"]

    def test_empty_html_returns_empty_list(self):
        positions = parse_positions(EMPTY_HTML)
        assert positions == []


class TestScrapePositions:
    @patch("src.scraper.fetch_page")
    def test_returns_sorted_positions(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_HTML
        positions = scrape_positions()

        assert positions == [
            "Backend Engineer",
            "Office Manager",
            "Senior Frontend Developer",
        ]

    @patch("src.scraper.fetch_page")
    def test_raises_on_empty_results(self, mock_fetch):
        mock_fetch.return_value = EMPTY_HTML
        with pytest.raises(ScraperError, match="No positions found"):
            scrape_positions()

    @patch("src.scraper.fetch_page", side_effect=Exception("Network error"))
    def test_raises_on_fetch_failure(self, mock_fetch):
        with pytest.raises(ScraperError, match="Failed to fetch"):
            scrape_positions()
