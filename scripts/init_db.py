"""Create the LendEase tables and sample data in the database named by your settings.

    python scripts/init_db.py --yes

Works on hosted MySQL (TiDB Cloud, Aiven, ...): it reads DATABASE_URL / DB_* from .env, skips the
CREATE DATABASE / USE lines in database/lendEase.sql (hosted providers pre-create the database),
loads the schema and sample data, then seeds the demo accounts.

WARNING: lendEase.sql drops and recreates every LendEase table, so existing rows are lost.
That is why --yes is required.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402

from config import Config  # noqa: E402
from scripts.seed_admin import connect, seed  # noqa: E402

SKIP = re.compile(r"^\s*(CREATE\s+DATABASE|USE)\b", re.IGNORECASE)


def split_statements(sql):
    """Split a SQL script into statements: drops comment-only lines, respects quoted strings."""
    lines = [ln for ln in sql.splitlines() if not ln.lstrip().startswith("--")]
    text = "\n".join(lines)

    statements, current, quote = [], [], None
    for ch in text:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
            current.append(ch)
        elif ch == ";":
            statements.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    statements.append("".join(current).strip())
    return [s for s in statements if s]


def runnable_statements(sql):
    return [s for s in split_statements(sql) if not SKIP.match(s)]


def main(argv):
    target = f"{Config.DB_USER}@{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}"
    if "--yes" not in argv:
        print(f"This will DROP and recreate all LendEase tables in {target}.")
        print("Re-run with --yes to continue.")
        return 1

    if not re.fullmatch(r"[A-Za-z0-9_]+", Config.DB_NAME):
        print(f"Database name {Config.DB_NAME!r} must contain only letters, digits and underscores.")
        return 1

    statements = runnable_statements((ROOT / "database" / "lendEase.sql").read_text(encoding="utf-8"))
    print(f"Connecting to {target} (TLS: {'on' if Config.DB_SSL else 'off'})")
    conn = connect(database=None)
    try:
        with conn.cursor() as cur:
            try:
                # Name is validated above; identifiers cannot be bound as %s parameters.
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{Config.DB_NAME}` CHARACTER SET utf8mb4")
            except pymysql.MySQLError as e:
                # Some hosts forbid CREATE DATABASE and pre-create it instead: carry on and USE it.
                print(f"Note: could not create database {Config.DB_NAME} ({e.args[0]}); assuming it exists.")
        conn.select_db(Config.DB_NAME)
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
        conn.commit()
        print(f"Loaded schema and sample data ({len(statements)} statements).")
        seed(conn)
    finally:
        conn.close()
    print("Done. Demo logins: admin@lendease.com / Admin@123, demo@lendease.com / Demo@123")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
