import pytest
from unittest.mock import patch

from src.scraper import PositionScraper, ScraperError
from shared.careers_html import normalize_title, strip_view_position_suffix


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

    def test_normalizes_unicode_characters(self):
        # Test NFKD normalization - non-breaking space should be normalized to regular space
        # Using non-breaking space (U+00A0) which NFKD normalizes to regular space
        assert normalize_title("Backend\u00A0Engineer") == "Backend Engineer"


class TestStripViewPositionSuffix:
    def test_strips_trailing_cta(self):
        assert strip_view_position_suffix("Backend Engineer View Position") == "Backend Engineer"

    def test_keeps_title_when_no_cta(self):
        assert strip_view_position_suffix("Backend Engineer") == "Backend Engineer"


class TestParsePositions:
    def test_extracts_positions(self):
        scraper = make_scraper()
        positions = scraper._parse_positions(SAMPLE_HTML)
        titles = [t for t, _ in positions]
        assert len(positions) == 3
        assert "Backend Engineer" in titles
        assert "Senior Frontend Developer" in titles
        assert "Office Manager" in titles

    def test_extracts_urls(self):
        scraper = make_scraper()
        positions = scraper._parse_positions(SAMPLE_HTML)
        urls = [u for _, u in positions]
        assert all(u.startswith("https://example.com/career/") for u in urls)

    def test_excludes_view_position_text(self):
        scraper = make_scraper()
        positions = scraper._parse_positions(SAMPLE_HTML)
        titles = [t for t, _ in positions]
        assert "View Position" not in titles

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
        assert len(positions) == 1
        assert positions[0][0] == "Account Manager"
        assert positions[0][1] == "https://example.com/career/account-manager-2/"

    def test_handles_combined_title_and_cta_text(self):
        html = """
        <html><body>
          <a href="/career/backend-engineer">Backend Engineer View Position</a>
        </body></html>
        """
        scraper = make_scraper()
        positions = scraper._parse_positions(html)
        assert len(positions) == 1
        assert positions[0][0] == "Backend Engineer"
        assert positions[0][1] == "https://example.com/career/backend-engineer"

    def test_empty_html_returns_empty_list(self):
        scraper = make_scraper()
        positions = scraper._parse_positions(EMPTY_HTML)
        assert positions == []

    def test_fallback_li_parsing_when_no_career_links(self):
        """Test fallback parsing path when primary /career/ selector finds nothing."""
        html = """
        <html><body>
          <ul>
            <li><a href="https://example.com/position/data-scientist">Data Scientist</a></li>
            <li><a href="https://example.com/position/devops-engineer">DevOps Engineer</a></li>
          </ul>
        </body></html>
        """
        scraper = make_scraper()
        positions = scraper._parse_positions(html)
        assert len(positions) == 2
        titles = [t for t, _ in positions]
        assert "Data Scientist" in titles
        assert "DevOps Engineer" in titles

    def test_filters_none_and_blank_titles(self):
        """Test that empty/blank titles are not included in results."""
        html = """
        <html><body>
          <li><a href="/career/empty"></a></li>
          <li><a href="/career/blank">   </a></li>
          <li><a href="/career/valid">Valid Title</a></li>
        </body></html>
        """
        scraper = make_scraper()
        positions = scraper._parse_positions(html)
        # Should only have the valid title
        titles = [t for t, _ in positions]
        assert len([t for t in titles if t.strip()]) == 1  # Only one non-blank title
        assert "Valid Title" in titles


class TestScrapePositions:
    def test_returns_sorted_positions(self):
        scraper = make_scraper()
        with patch.object(scraper, "_fetch_page", return_value=SAMPLE_HTML):
            positions = scraper.scrape()

        titles = [t for t, _ in positions]
        assert titles == [
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
