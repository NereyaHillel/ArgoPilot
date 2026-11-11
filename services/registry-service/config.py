import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

SERVICE_DIR = Path(__file__).resolve().parent
ENV_FILE = SERVICE_DIR / ".env"
DEFAULT_SQLITE_URL = f"sqlite:///{SERVICE_DIR / 'registry.db'}"
SUPPORTED_SCHEMES = {"sqlite", "postgresql", "postgres"}


def database_url(env_file: Path = ENV_FILE) -> str:
    # A real environment variable wins over .env; os.environ is never modified.
    url = os.environ.get("DATABASE_URL") or dotenv_values(env_file).get("DATABASE_URL")
    if not url:
        return DEFAULT_SQLITE_URL
    scheme = urlsplit(url).scheme
    if scheme not in SUPPORTED_SCHEMES:
        raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme!r}")
    return url
