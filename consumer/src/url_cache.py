import hashlib
import json
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from shared.logger import get_logger

logger = get_logger(__name__)

CacheData = dict  # {"page_hash": str, "title_mapping": dict[str, str]}


def _normalize_title(title: str) -> str:
    """Strip whitespace and normalize unicode characters."""
    title = title.strip()
    title = unicodedata.normalize("NFKD", title)
    return " ".join(title.split())


def _base_url(url: str) -> str:
    """Return scheme + netloc for resolving relative hrefs."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _compute_jobs_section_hash(html: str) -> str:
    """Return a SHA-256 digest of the jobs listing section only.

    Targets <div id="response_jobs"> which contains exactly the career
    position links and nothing dynamic (no auth tokens, no timestamps).
    Falls back to an empty string if the element is not found.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs_div = soup.find(id="response_jobs")
    if jobs_div is None:
        logger.warning("Could not find #response_jobs in page HTML; hash will be empty")
        return ""
    return hashlib.sha256(str(jobs_div).encode()).hexdigest()


def fetch_careers_page(url: str) -> str:
    """GET the careers page and return the HTML."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    logger.debug("Fetched careers page.")
    return response.text


def extract_position_urls(html: str, careers_url: str) -> dict[str, str]:
    """Parse HTML and return {title: absolute_url} for all career positions."""
    soup = BeautifulSoup(html, "html.parser")
    base = _base_url(careers_url)

    mapping: dict[str, str] = {}

    career_links = soup.find_all("a", href=lambda h: h and "/career/" in h.lower())
    for link in career_links:
        title_span = link.select_one("span.link-text")
        if title_span:
            raw_title = title_span.get_text(" ", strip=True)
        else:
            raw_title = link.get_text(" ", strip=True)

        title = _normalize_title(raw_title)
        cta = "view position"
        if title.lower().endswith(cta):
            title = title[: -len(cta)].rstrip()

        if not title or title.lower() == "view position":
            continue

        href = link.get("href", "")
        url = urljoin(base, href) if not href.startswith("http") else href
        mapping[title] = url

    logger.debug("Extracted %d position URLs from HTML", len(mapping))
    return mapping


def load_cache(path: str) -> CacheData | None:
    """Load the cache JSON from disk. Returns None if the file does not exist."""
    cache_path = Path(path)
    if not cache_path.exists():
        logger.debug("Cache file not found at %s", path)
        return None
    try:
        with cache_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        logger.debug("Loaded cache from %s", path)
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read cache file %s: %s", path, e)
        return None


def save_cache(path: str, page_hash: str, title_mapping: dict[str, str]) -> None:
    """Write the cache JSON to disk."""
    cache_path = Path(path)
    data: CacheData = {
        "page_hash": page_hash,
        "title_mapping": title_mapping,
    }
    try:
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Cache saved to %s (%d positions)", path, len(title_mapping))
    except OSError as e:
        logger.error("Failed to write cache file %s: %s", path, e)


def check_and_refresh_cache(careers_url: str, cache_path: str) -> CacheData:
    """Check whether the cache is up to date and rebuild it if necessary.

    Always returns the current (possibly freshly built) cache dict.
    Errors during fetch/parse are logged and do not propagate — the caller
    receives whatever cache is available (or an empty one).
    """
    cache = load_cache(cache_path)

    try:
        html = fetch_careers_page(careers_url)
    except Exception as e:
        logger.error("Could not fetch careers page for cache check: %s", e)
        return cache or {"page_hash": "", "title_mapping": {}}

    page_hash = _compute_jobs_section_hash(html)
    cached_hash = (cache or {}).get("page_hash", "")
    if cache is not None and cached_hash == page_hash:
        logger.info("Cache is up to date (jobs section hash unchanged)")
        return cache

    logger.info(
        "Cache %s. Rebuilding (jobs section changed)",
        "missing" if cache is None else "outdated",
    )

    try:
        title_mapping = extract_position_urls(html, careers_url)
    except Exception as e:
        logger.error("Failed to extract position URLs: %s", e)
        return cache or {"page_hash": "", "title_mapping": {}}

    save_cache(cache_path, page_hash, title_mapping)
    return {"page_hash": page_hash, "title_mapping": title_mapping}
