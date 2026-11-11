import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

SERVICE_DIR = Path(__file__).resolve().parent
ENV_FILE = SERVICE_DIR / ".env"
DEFAULT_SQLITE_URL = f"sqlite:///{SERVICE_DIR / 'registry.db'}"
SUPPORTED_SCHEMES = {"sqlite", "postgresql", "postgres"}


def database_url(env_file: Path = ENV_FILE) -> str:
    # A real environment variable wins over .env, even when empty; os.environ is never modified.
    url = os.environ.get("DATABASE_URL")
    if url is None:
        url = dotenv_values(env_file).get("DATABASE_URL")
    if url is None:
        return DEFAULT_SQLITE_URL
    if not url:
        raise ValueError("empty DATABASE_URL; unset it to use registry.db")
    # Messages name only the scheme, since the URL may hold a password.
    scheme = urlsplit(url).scheme
    if not scheme:
        raise ValueError("DATABASE_URL has no scheme; expected sqlite:/// or postgresql://")
    if scheme not in SUPPORTED_SCHEMES:
        raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme!r}")
    return url
