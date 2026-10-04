"""Application configuration, read from environment variables (.env in development)."""
import os
from urllib.parse import parse_qs, unquote, urlparse

from dotenv import load_dotenv

load_dotenv()

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
SSL_OFF_VALUES = {"0", "false", "no", "disabled", "disable"}
SYSTEM_SCHEMAS = {"", "sys", "mysql", "information_schema", "performance_schema"}


def parse_database_url(url):
    """Turn mysql://user:pass@host:port/dbname?ssl-mode=REQUIRED into DB_* settings.

    Hosted MySQL providers hand out a single connection URL. Returns {} for an empty or
    non-MySQL URL so callers can fall back to the individual DB_* variables.
    """
    if not url:
        return {}
    parsed = urlparse(url)
    if parsed.scheme not in ("mysql", "mysql+pymysql", "mariadb"):
        return {}

    host = parsed.hostname or "localhost"
    query = {k.lower(): v[-1] for k, v in parse_qs(parsed.query).items()}
    explicit_ssl = query.get("ssl-mode") or query.get("ssl")
    if explicit_ssl is not None:
        use_ssl = explicit_ssl.lower() not in SSL_OFF_VALUES
    else:
        use_ssl = host not in LOCAL_HOSTS  # hosted databases require TLS

    # Provider consoles often show a system schema (TiDB Cloud shows "sys") or no database at
    # all in the URL. App tables must not live there, so use our own database instead.
    name = unquote(parsed.path.lstrip("/"))
    if name.lower() in SYSTEM_SCHEMAS:
        name = "lendease"

    return {
        "DB_HOST": host,
        "DB_PORT": parsed.port or 3306,
        "DB_USER": unquote(parsed.username or ""),
        "DB_PASSWORD": unquote(parsed.password or ""),
        "DB_NAME": name,
        "DB_SSL": use_ssl,
    }


_url = parse_database_url(os.environ.get("DATABASE_URL", ""))


def _setting(name, default):
    """An explicit DB_* variable wins over DATABASE_URL, which wins over the default."""
    return os.environ.get(name) or _url.get(name, default)


class Config:
    # The fallback keeps `python app.py` working on a fresh clone, but it is NOT
    # safe for anything public: set SECRET_KEY in .env before deploying.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key-change-me")

    DB_HOST = _setting("DB_HOST", "localhost")
    DB_PORT = int(_setting("DB_PORT", 3306))
    DB_USER = _setting("DB_USER", "root")
    DB_PASSWORD = _setting("DB_PASSWORD", "")
    DB_NAME = _setting("DB_NAME", "lendease")
    # Hosted MySQL providers (Aiven, TiDB Cloud, ...) require TLS: set DB_SSL=1,
    # or use a DATABASE_URL (TLS is then on automatically for non-local hosts).
    DB_SSL = (
        os.environ["DB_SSL"].lower() in ("1", "true", "yes")
        if "DB_SSL" in os.environ
        else bool(_url.get("DB_SSL", False))
    )

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
