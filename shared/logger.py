import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """Configure root logging (idempotent) and return a named logger."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    return logging.getLogger(name)
