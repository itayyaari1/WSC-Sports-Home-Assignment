import unicodedata

import requests
from bs4 import BeautifulSoup


def normalize_title(title: str) -> str:
    """Strip whitespace and normalize unicode characters."""
    title = title.strip()
    title = unicodedata.normalize("NFKD", title)
    title = " ".join(title.split())
    return title


def strip_view_position_suffix(text: str) -> str:
    """Remove trailing CTA text while preserving the original title."""
    cta_suffix = "view position"
    normalized = normalize_title(text)
    if normalized.lower().endswith(cta_suffix):
        normalized = normalized[: -len(cta_suffix)].rstrip()
    return normalized


def extract_title_from_link(link) -> str:
    """Extract a clean position title from a BeautifulSoup anchor element.

    Prefers the structured span.link-text child; falls back to full link text
    with the CTA suffix stripped.
    """
    title_span = link.select_one("span.link-text")
    if title_span:
        return normalize_title(title_span.get_text(" ", strip=True))
    return strip_view_position_suffix(link.get_text(" ", strip=True))


def fetch_careers_page(url: str, timeout: int = 30) -> str:
    """GET the careers page and return its HTML."""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text
