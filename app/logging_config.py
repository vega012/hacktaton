"""Logging legible en consola (y en `docker compose logs`)."""
import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    # Reducir ruido de librerías HTTP
    logging.getLogger("httpx").setLevel(logging.WARNING)
