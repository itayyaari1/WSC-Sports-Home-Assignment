import hashlib
import json
from pathlib import Path

from shared.logger import get_logger

logger = get_logger(__name__)

CacheData = dict  # {"positions_enrichment": dict[str, dict]}


def hash_requirements_block(req_block_html: str) -> str:
    """Return a SHA-256 digest of a requirements block HTML string."""
    return hashlib.sha256(req_block_html.encode()).hexdigest()


def get_cached_enrichment(req_block_html: str, cache: CacheData) -> dict | None:
    """Look up enrichment fields by requirements block HTML hash.

    Returns the cached enrichment dict if found, or None on a miss.
    """
    req_hash = hash_requirements_block(req_block_html)
    return (cache.get("positions_enrichment") or {}).get(req_hash)


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


def save_cache(path: str, cache_data: CacheData) -> None:
    """Write the cache JSON to disk."""
    cache_path = Path(path)
    try:
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        logger.info(
            "Cache saved to %s (%d enrichments)",
            path,
            len(cache_data.get("positions_enrichment", {})),
        )
    except OSError as e:
        logger.error("Failed to write cache file %s: %s", path, e)
