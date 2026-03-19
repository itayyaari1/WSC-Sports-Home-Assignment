from unittest.mock import patch

import pytest

from src.enrichment import (
    classify_category,
    classify_seniority_level,
    calculate_complexity_score,
    enrich_positions,
)
from src.models import BasePosition


class TestClassifyCategory:
    @pytest.mark.parametrize("title,expected", [
        ("Backend Engineer", "Engineering"),
        ("Senior Frontend Developer", "Engineering"),
        ("ML Engineering Team Lead", "Engineering"),
        ("Algorithm Developer GenAI", "Engineering"),
        ("C++ Graphics Engineer", "Engineering"),
        ("Cloud FinOps Engineer", "Engineering"),
        ("NLP Algorithm Developer", "Engineering"),
        ("Data Engineer", "Engineering"),
        ("Director of Product", "Product"),
        ("Generative AI Evangelist", "Engineering"),  # "ai" keyword fires before "evangelist"
        ("After Effects Specialist", "Other"),         # "effects" is not a Design keyword
        ("Office Manager", "Operations"),
        ("Financial Controller", "Operations"),
        ("Legal Counsel", "Operations"),
        ("BizDev Manager, New Media", "Operations"),
        ("Account Manager", "Operations"),
        ("Strategic Partnerships Lead", "Operations"),
    ])
    def test_category_classification(self, title, expected):
        assert classify_category(title) == expected

    def test_unknown_falls_back_to_other(self):
        assert classify_category("Mystery Role") == "Other"


class TestClassifySeniorityLevel:
    @pytest.mark.parametrize("years,expected", [
        (7, "Lead"),
        (4, "Senior"),
        (1, "Mid"),
        (0, "Mid"),   # no req_block → defaults to Mid
    ])
    def test_seniority_by_years(self, years, expected):
        assert classify_seniority_level(None, years) == expected


class TestCalculateComplexityScore:
    def test_senior_engineering_scores_high(self):
        # 5 years + 8 skills + Senior → 25 + 32 + 15 = 72
        score = calculate_complexity_score(years=5, skills=8, seniority_level="Senior")
        assert 60 <= score <= 100

    def test_junior_operations_scores_low(self):
        # 1 year + 3 skills + Junior → 5 + 12 + 5 = 22
        score = calculate_complexity_score(years=1, skills=3, seniority_level="Junior")
        assert 0 <= score <= 45

    def test_lead_architect_scores_highest(self):
        # 8+ years + 10+ skills + Lead → 40 + 40 + 20 = 100
        score = calculate_complexity_score(years=8, skills=10, seniority_level="Lead")
        assert score == 100

    def test_score_capped_at_100(self):
        score = calculate_complexity_score(years=999, skills=999, seniority_level="Lead")
        assert score <= 100

    def test_score_minimum_is_non_negative(self):
        score = calculate_complexity_score(years=0, skills=0, seniority_level="Junior")
        assert score >= 0


class TestEnrichPositions:
    def test_returns_empty_list_for_empty_input(self):
        result = enrich_positions([])
        assert result == []

    @patch("src.enrichment.fetch_position_html", return_value=None)
    @patch("src.enrichment.load_cache", return_value={"title_mapping": {}})
    def test_enriches_list_of_base_positions(self, _mock_cache, _mock_fetch):
        positions = [
            BasePosition(index=1, title="Senior Backend Engineer"),
            BasePosition(index=2, title="Junior UX Designer"),
            BasePosition(index=3, title="Office Manager"),
        ]
        enriched = enrich_positions(positions)

        assert len(enriched) == 3
        assert enriched[0].category == "Engineering"
        assert enriched[1].category == "Design"
        assert enriched[2].category == "Operations"

    @patch("src.enrichment.fetch_position_html", return_value=None)
    @patch("src.enrichment.load_cache", return_value={"title_mapping": {}})
    def test_complexity_scores_are_valid_range(self, _mock_cache, _mock_fetch):
        positions = [BasePosition(index=1, title="Backend Engineer")]
        enriched = enrich_positions(positions)
        assert 0 <= enriched[0].complexity_score <= 100
