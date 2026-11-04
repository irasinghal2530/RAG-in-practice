"""Download source documents into config.RAW_DIR/<category>/."""

from studyrag import config


def download_all(only: list[str] | None = None) -> None:
    """Download every source (or only these categories) into config.RAW_DIR."""
    raise NotImplementedError
