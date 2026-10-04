"""Create the demo accounts. Safe to run repeatedly.

    python scripts/seed_admin.py

Run it after loading database/lendEase.sql (or use scripts/init_db.py, which does both). Password
hashes are generated here (not stored in the SQL file) so they always match your Werkzeug version.
"""
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymysql  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from config import Config  # noqa: E402

ACCOUNTS = [
    ("LendEase Admin", "admin@lendease.com", "Admin@123", 1),
    ("Demo User", "demo@lendease.com", "Demo@123", 0),
]


def connect(database=Config.DB_NAME):
    """Pass database=None to connect to the server without selecting a database."""
    return pymysql.connect(
        host=Config.DB_HOST, port=Config.DB_PORT, user=Config.DB_USER,
        password=Config.DB_PASSWORD, database=database, charset="utf8mb4",
        connect_timeout=10,
        ssl=ssl.create_default_context() if Config.DB_SSL else None,
    )


def seed(conn):
    """Insert/refresh the demo accounts plus a few saved offers and searches for the demo user."""
    with conn.cursor() as cur:
        for name, email, password, is_admin in ACCOUNTS:
            cur.execute(
                "INSERT INTO users (full_name, email, password_hash, is_admin) VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE full_name = VALUES(full_name), "
                "password_hash = VALUES(password_hash), is_admin = VALUES(is_admin)",
                (name, email, generate_password_hash(password), is_admin),
            )

        cur.execute("SELECT user_id FROM users WHERE email = %s", ("demo@lendease.com",))
        demo_id = cur.fetchone()[0]

        # Sample activity for the demo user, so the dashboard and the Analytics pie charts
        # have something to show. Safe to re-run: saved offers are unique per user and product,
        # and the searches are only added while the demo user has fewer than 10.
        cur.execute(
            "INSERT INTO saved_offers (user_id, product_id, notes) "
            "SELECT %s, p.product_id, 'Sample saved offer' "
            "FROM loan_products p JOIN banks b ON b.bank_id = p.bank_id "
            "WHERE (b.short_name = 'SBI'   AND p.loan_type IN ('Home Loan', 'Car Loan', 'Education Loan')) "
            "   OR (b.short_name = 'PNB'   AND p.loan_type IN ('Home Loan', 'Personal Loan')) "
            "   OR (b.short_name = 'HDFC'  AND p.loan_type IN ('Personal Loan', 'Car Loan')) "
            "   OR (b.short_name = 'ICICI' AND p.loan_type = 'Home Loan') "
            "   OR (b.short_name = 'Kotak' AND p.loan_type = 'Business Loan') "
            "ON DUPLICATE KEY UPDATE saved_id = saved_id",
            (demo_id,),
        )
        cur.execute("SELECT COUNT(*) FROM comparison_history WHERE user_id = %s", (demo_id,))
        if cur.fetchone()[0] < 10:
            cur.executemany(
                "INSERT INTO comparison_history (user_id, loan_type, amount, tenure_months) VALUES (%s, %s, %s, %s)",
                [(demo_id, "Home Loan", 3000000, 240), (demo_id, "Home Loan", 5000000, 300),
                 (demo_id, "Home Loan", 2500000, 180), (demo_id, "Home Loan", 4000000, 240),
                 (demo_id, "Home Loan", 6000000, 360), (demo_id, "Personal Loan", 500000, 36),
                 (demo_id, "Personal Loan", 300000, 24), (demo_id, "Personal Loan", 800000, 48),
                 (demo_id, "Car Loan", 900000, 60), (demo_id, "Car Loan", 1200000, 84),
                 (demo_id, "Car Loan", 700000, 48), (demo_id, "Education Loan", 1500000, 120),
                 (demo_id, "Education Loan", 2000000, 144), (demo_id, "Business Loan", 2500000, 60)],
            )
    conn.commit()


def main():
    conn = connect()
    try:
        seed(conn)
    finally:
        conn.close()

    print("Seeded accounts:")
    for name, email, password, is_admin in ACCOUNTS:
        print(f"  {'admin' if is_admin else 'user '}  {email}  /  {password}")


if __name__ == "__main__":
    main()
