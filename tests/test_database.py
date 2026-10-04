"""DATABASE_URL parsing (config.py) and the SQL loader (scripts/init_db.py)."""
import re
from pathlib import Path

import pytest

from config import parse_database_url
from scripts.init_db import runnable_statements, split_statements

SQL_FILE = Path(__file__).resolve().parent.parent / "database" / "lendEase.sql"


def test_hosted_url_turns_tls_on_and_decodes_the_password():
    cfg = parse_database_url("mysql://app_user:p%40ss%3Aword@gateway.example.com:4000/lendease")
    assert cfg == {"DB_HOST": "gateway.example.com", "DB_PORT": 4000, "DB_USER": "app_user",
                   "DB_PASSWORD": "p@ss:word", "DB_NAME": "lendease", "DB_SSL": True}


def test_local_url_keeps_tls_off_and_default_port():
    cfg = parse_database_url("mysql://root:secret@localhost/lendease")
    assert cfg["DB_PORT"] == 3306 and cfg["DB_SSL"] is False


@pytest.mark.parametrize("path", ["/sys", "/mysql", "/information_schema", "/", ""])
def test_url_never_points_at_a_system_database(path):
    # TiDB Cloud's console shows "sys" in the connection string.
    assert parse_database_url(f"mysql://u.root:p@gateway.tidbcloud.com:4000{path}")["DB_NAME"] == "lendease"


@pytest.mark.parametrize("url", ["", "postgres://u:p@h/db", "not a url"])
def test_empty_or_non_mysql_urls_are_ignored(url):
    assert parse_database_url(url) == {}


def test_split_statements_skips_comments_and_keeps_quoted_semicolons():
    sql = "-- header; not a statement\nCREATE TABLE t (a INT);\nINSERT INTO t VALUES ('x;y');\n"
    assert split_statements(sql) == ["CREATE TABLE t (a INT)", "INSERT INTO t VALUES ('x;y')"]


def test_loader_skips_create_database_and_use():
    statements = runnable_statements(SQL_FILE.read_text(encoding="utf-8"))
    assert not any(re.match(r"\s*(CREATE\s+DATABASE|USE)\b", s, re.I) for s in statements)
    kinds = [s.split()[0].upper() for s in statements]
    assert kinds.count("CREATE") == 6 and kinds.count("DROP") == 6 and "INSERT" in kinds
