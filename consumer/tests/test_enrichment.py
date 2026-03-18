import pandas as pd
import pytest

from src.enrichment import (
    classify_category,
    detect_seniority,
    calculate_complexity,
    enrich_positions,
)


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
        ("Generative AI Evangelist", "Product"),
        ("After Effects Specialist", "Design"),
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


class TestDetectSeniority:
    @pytest.mark.parametrize("title,expected", [
        ("Senior Frontend Developer", "Senior"),
        ("Junior UX Designer", "Junior"),
        ("ML Engineering Team Lead", "Lead"),
        ("Director of Global Marketing", "Lead"),
        ("Backend Engineer", "Mid"),
        ("Client Solutions & Delivery Team Lead", "Lead"),
        ("Data Engineer", "Mid"),
    ])
    def test_seniority_detection(self, title, expected):
        assert detect_seniority(title) == expected


class TestCalculateComplexity:
    def test_senior_engineering_scores_high(self):
        score = calculate_complexity("Senior Backend Engineer", "Engineering", "Senior")
        assert 60 <= score <= 85

    def test_junior_operations_scores_low(self):
        score = calculate_complexity("Junior Admin", "Operations", "Junior")
        assert 20 <= score <= 45

    def test_lead_with_architect_scores_highest(self):
        score = calculate_complexity("Lead Software Architect", "Engineering", "Lead")
        assert score >= 80

    def test_score_capped_at_100(self):
        score = calculate_complexity(
            "Principal Lead Fullstack Architect Engineer Senior",
            "Engineering",
            "Lead",
        )
        assert score <= 100

    def test_score_minimum_is_positive(self):
        score = calculate_complexity("X", "Other", "Junior")
        assert score > 0


class TestEnrichPositions:
    def test_enriches_dataframe(self):
        df = pd.DataFrame({
            "Index": [1, 2, 3],
            "Position_Title": [
                "Senior Backend Engineer",
                "Junior UX Designer",
                "Office Manager",
            ],
        })
        enriched = enrich_positions(df)

        assert "category" in enriched.columns
        assert "seniority_level" in enriched.columns
        assert "complexity_score" in enriched.columns
        assert "enriched_at" in enriched.columns

        assert enriched.iloc[0]["category"] == "Engineering"
        assert enriched.iloc[0]["seniority_level"] == "Senior"
        assert enriched.iloc[1]["category"] == "Design"
        assert enriched.iloc[1]["seniority_level"] == "Junior"
        assert enriched.iloc[2]["category"] == "Operations"

    def test_handles_empty_dataframe(self):
        df = pd.DataFrame(columns=["Index", "Position_Title"])
        enriched = enrich_positions(df)
        assert len(enriched) == 0
        assert "category" in enriched.columns

    def test_complexity_scores_are_valid_range(self):
        df = pd.DataFrame({
            "Index": [1],
            "Position_Title": ["Backend Engineer"],
        })
        enriched = enrich_positions(df)
        score = enriched.iloc[0]["complexity_score"]
        assert 0 <= score <= 100
