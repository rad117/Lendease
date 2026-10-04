"""LendEase - Loan Comparison & Financial Analytics Platform.

Flask + MySQL (raw parameterized SQL through PyMySQL, no ORM).
Run this file to start the website:  python app.py
It opens http://127.0.0.1:5000 in the browser automatically.
"""
import csv
import io
import re
import secrets
import ssl
import threading
import webbrowser
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import urlparse

import pymysql
from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)
from pymysql.cursors import DictCursor
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config

app = Flask(__name__)
app.config.from_object(Config)

LOAN_TYPES = ["Home Loan", "Personal Loan", "Car Loan", "Education Loan", "Business Loan"]

DISCLAIMER = (
    "LendEase is a comparison and learning tool, not a lender. Figures are illustrative "
    "reference data based on publicly available information and may differ from what a "
    "bank currently offers. Always confirm rates, fees and eligibility on the bank's own website."
)


# ============================================================
# Database helpers (one MySQL connection per request)
# ============================================================

def get_db():
    if "db" not in g:
        g.db = pymysql.connect(
            host=app.config["DB_HOST"],
            port=app.config["DB_PORT"],
            user=app.config["DB_USER"],
            password=app.config["DB_PASSWORD"],
            database=app.config["DB_NAME"],
            charset="utf8mb4",
            cursorclass=DictCursor,
            connect_timeout=5,
            ssl=ssl.create_default_context() if app.config["DB_SSL"] else None,
        )
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql, params=None, one=False):
    """Run a SELECT. Returns a list of rows (dicts), or one row / None when one=True."""
    with get_db().cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone() if one else cur.fetchall()


def execute(sql, params=None, lastrowid=False):
    """Run an INSERT / UPDATE / DELETE and commit. Returns the new id or the affected row count."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            affected = cur.execute(sql, params or ())
            new_id = cur.lastrowid
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return new_id if lastrowid else affected


# ============================================================
# EMI formula and display helpers
# ============================================================

def calculate_emi(principal, annual_rate, tenure_months):
    """EMI = P*r*(1+r)^n / ((1+r)^n - 1), where r = annual_rate / 12 / 100."""
    principal = float(principal)
    annual_rate = float(annual_rate)
    n = int(tenure_months)
    if principal <= 0 or annual_rate < 0 or n <= 0:
        raise ValueError("principal and tenure must be positive; rate cannot be negative")

    r = annual_rate / 12 / 100
    if r == 0:
        emi = principal / n
    else:
        growth = (1 + r) ** n
        emi = principal * r * growth / (growth - 1)

    emi = round(emi, 2)
    total_payable = round(emi * n, 2)
    return {
        "emi": emi,
        "total_payable": total_payable,
        "total_interest": round(total_payable - principal, 2),
    }


@app.template_filter("inr")
def format_inr(value, decimals=0):
    """3000000 -> ₹30,00,000 (Indian lakh/crore grouping)."""
    amount = float(value or 0)
    sign = "-" if amount < 0 else ""
    whole, _, frac = f"{abs(amount):.{decimals}f}".partition(".")

    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])

    return f"{sign}₹{whole}" + (f".{frac}" if frac else "")


@app.template_filter("tenure")
def tenure_label(months):
    """240 -> '20 yrs', 18 -> '1 yr 6 mos'."""
    years, rem = divmod(int(months), 12)
    if years == 0:
        return f"{rem} mos"
    year_part = f"{years} yr" if years == 1 else f"{years} yrs"
    return year_part if rem == 0 else f"{year_part} {rem} mos"


# ============================================================
# Login checks and CSRF protection
# ============================================================

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify(error="Please log in first."), 401
            flash("Please log in to continue.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def csrf_token():
    """One random token per session; forms send it back so other sites can't submit them."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def check_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf_token", "")
    if not expected or not secrets.compare_digest(sent, expected):
        if request.path.startswith("/api/"):
            return jsonify(error="Invalid or missing CSRF token."), 400
        abort(400, description="Invalid or missing CSRF token. Reload the page and try again.")
    return None


@app.context_processor
def inject_globals():
    return {
        "LOAN_TYPES": LOAN_TYPES,
        "DISCLAIMER": DISCLAIMER,
        "current_user_name": session.get("user_name"),
        "is_logged_in": "user_id" in session,
        "is_admin": bool(session.get("is_admin")),
    }


# ============================================================
# Error pages
# ============================================================

def error_page(code, title, message):
    return render_template("error.html", code=code, title=title, message=message), code


@app.errorhandler(400)
def bad_request(e):
    return error_page(400, "Bad request", getattr(e, "description", "The request could not be processed."))


@app.errorhandler(403)
def forbidden(e):
    return error_page(403, "Access denied", "You don't have permission to view this page.")


@app.errorhandler(404)
def not_found(e):
    return error_page(404, "Page not found", "We couldn't find the page you were looking for.")


@app.errorhandler(pymysql.MySQLError)
def database_error(e):
    app.logger.error("Database error: %s", e)
    message = "The database isn't reachable right now. Check the database settings and that MySQL is running."
    if request.path.startswith("/api/"):
        return jsonify(error=message), 503
    return error_page(503, "Database unavailable", message)


@app.errorhandler(500)
def server_error(e):
    return error_page(500, "Something went wrong", "An unexpected error occurred. Please try again.")


# ============================================================
# Home and EMI calculator
# ============================================================

@app.route("/")
def home():
    banks = query("SELECT bank_id, name, short_name FROM banks ORDER BY name")
    type_rows = query(
        """
        SELECT loan_type, MIN(min_interest_rate) AS from_rate, COUNT(DISTINCT bank_id) AS bank_count
        FROM loan_products
        WHERE is_active = 1
        GROUP BY loan_type
        """
    )
    type_stats = {row["loan_type"]: row for row in type_rows if "loan_type" in row}
    return render_template("home.html", banks=banks, type_stats=type_stats)


@app.route("/emi-calculator")
def emi_calculator():
    return render_template("emi_calculator.html")


# ============================================================
# Register, login, logout
# ============================================================

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def start_session(user):
    session.clear()
    session["user_id"] = user["user_id"]
    session["user_name"] = user["full_name"]
    session["is_admin"] = bool(user["is_admin"])


@app.route("/auth/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        errors = []
        if not full_name:
            errors.append("Please enter your name.")
        if not EMAIL_RE.match(email):
            errors.append("Please enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        if not errors:
            try:
                user_id = execute(
                    "INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s)",
                    (full_name, email, generate_password_hash(password)),
                    lastrowid=True,
                )
            except pymysql.err.IntegrityError:
                errors.append("An account with that email already exists.")
            else:
                start_session({"user_id": user_id, "full_name": full_name, "is_admin": 0})
                flash("Welcome to LendEase! Your account is ready.", "success")
                return redirect(url_for("dashboard"))

        for message in errors:
            flash(message, "error")
        return render_template("register.html", form=request.form), 400

    return render_template("register.html", form={})


@app.route("/auth/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or request.form.get("next", "")
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = query(
            "SELECT user_id, full_name, password_hash, is_admin FROM users WHERE email = %s",
            (email,),
            one=True,
        )
        if user and check_password_hash(user["password_hash"], password):
            start_session(user)
            flash(f"Welcome back, {user['full_name']}.", "success")
            # Only follow links that stay on this site (blocks //evil.com and http://evil.com).
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("dashboard"))

        flash("Incorrect email or password.", "error")
        return render_template("login.html", next_url=next_url, email=email), 401

    return render_template("login.html", next_url=next_url, email="")


@app.route("/auth/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


# ============================================================
# Loan comparison and loan details
# ============================================================

PRODUCT_COLUMNS = """
    p.product_id, p.product_name, p.loan_type,
    p.min_interest_rate, p.max_interest_rate,
    p.min_amount, p.max_amount, p.min_tenure_months, p.max_tenure_months,
    p.processing_fee_percent, p.processing_fee_flat,
    p.eligibility_criteria, p.source_url, p.last_updated,
    b.bank_id, b.name AS bank_name, b.short_name, b.website_url
"""


def compare_products(loan_type, amount=None, tenure=None, bank_id=None, min_rate=None, max_rate=None):
    """Active products of one loan type, lowest starting rate first.

    Every value goes to MySQL through a %s placeholder; only fixed SQL text is joined together.
    """
    sql = f"""
        SELECT {PRODUCT_COLUMNS}
        FROM loan_products p
        JOIN banks b ON b.bank_id = p.bank_id
        WHERE p.is_active = 1 AND p.loan_type = %s
    """
    params = [loan_type]

    if amount is not None:
        sql += " AND p.min_amount <= %s AND p.max_amount >= %s"
        params += [amount, amount]
    if tenure is not None:
        sql += " AND p.min_tenure_months <= %s AND p.max_tenure_months >= %s"
        params += [tenure, tenure]
    if bank_id is not None:
        sql += " AND b.bank_id = %s"
        params.append(bank_id)
    if min_rate is not None:
        sql += " AND p.max_interest_rate >= %s"
        params.append(min_rate)
    if max_rate is not None:
        sql += " AND p.min_interest_rate <= %s"
        params.append(max_rate)

    sql += " ORDER BY p.min_interest_rate ASC, b.name ASC"
    return query(sql, params)


def get_product(product_id):
    return query(
        f"""
        SELECT {PRODUCT_COLUMNS}
        FROM loan_products p
        JOIN banks b ON b.bank_id = p.bank_id
        WHERE p.product_id = %s AND p.is_active = 1
        """,
        (product_id,),
        one=True,
    )


@app.route("/loans/compare")
def compare():
    banks = query("SELECT bank_id, name, short_name FROM banks ORDER BY name")
    return render_template("compare.html", banks=banks)


@app.route("/loans/<int:product_id>")
def loan_detail(product_id):
    product = get_product(product_id)
    if product is None:
        abort(404)

    saved = False
    if "user_id" in session:
        row = query(
            "SELECT saved_id FROM saved_offers WHERE user_id = %s AND product_id = %s",
            (session["user_id"], product_id),
            one=True,
        )
        saved = row is not None
    return render_template("loan_detail.html", p=product, saved=saved)


# ============================================================
# JSON API used by the compare page and the save buttons
# ============================================================

def read_number(name, cast=float, minimum=None):
    """Read an optional number from the query string. Returns (value, error message)."""
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None, None
    try:
        value = cast(raw)
    except (TypeError, ValueError):
        return None, f"{name} must be a number."
    if minimum is not None and value < minimum:
        return None, f"{name} must be at least {minimum}."
    return value, None


def to_json_row(row):
    """Decimal and date values can't go into JSON directly, so convert them."""
    out = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            out[key] = float(value)
        elif hasattr(value, "isoformat"):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


@app.route("/api/compare")
def api_compare():
    loan_type = request.args.get("loan_type", "")
    if loan_type not in LOAN_TYPES:
        return jsonify(error=f"loan_type must be one of: {', '.join(LOAN_TYPES)}"), 400

    amount, e1 = read_number("amount", float, 1)
    tenure, e2 = read_number("tenure", int, 1)
    bank_id, e3 = read_number("bank_id", int, 1)
    min_rate, e4 = read_number("min_rate", float, 0)
    max_rate, e5 = read_number("max_rate", float, 0)
    errors = [e for e in (e1, e2, e3, e4, e5) if e]
    if errors:
        return jsonify(error=" ".join(errors)), 400

    rows = compare_products(loan_type, amount, tenure, bank_id, min_rate, max_rate)

    saved_ids = []
    if "user_id" in session:
        # Remember this search for the dashboard, and tell the page which offers are already saved.
        if amount is not None and tenure is not None:
            execute(
                "INSERT INTO comparison_history (user_id, loan_type, amount, tenure_months) "
                "VALUES (%s, %s, %s, %s)",
                (session["user_id"], loan_type, amount, tenure),
            )
        saved = query("SELECT product_id FROM saved_offers WHERE user_id = %s", (session["user_id"],))
        saved_ids = [row["product_id"] for row in saved]

    return jsonify(
        count=len(rows),
        results=[to_json_row(row) for row in rows],
        saved_ids=saved_ids,
        disclaimer=DISCLAIMER,
    )


@app.route("/api/save-offer", methods=["POST"])
@login_required
def api_save_offer():
    data = request.get_json(silent=True) or {}
    try:
        product_id = int(data.get("product_id"))
    except (TypeError, ValueError):
        return jsonify(error="product_id is required."), 400

    if get_product(product_id) is None:
        return jsonify(error="That loan product does not exist."), 404

    # UNIQUE(user_id, product_id) makes saving the same offer twice harmless.
    execute(
        "INSERT INTO saved_offers (user_id, product_id) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE saved_id = saved_id",
        (session["user_id"], product_id),
    )
    return jsonify(saved=True, product_id=product_id), 201


@app.route("/api/save-offer/<int:product_id>", methods=["DELETE"])
@login_required
def api_unsave_offer(product_id):
    execute(
        "DELETE FROM saved_offers WHERE user_id = %s AND product_id = %s",
        (session["user_id"], product_id),
    )
    return jsonify(saved=False, product_id=product_id)


# ============================================================
# User dashboard: saved offers and comparison history
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]

    saved = query(
        """
        SELECT s.saved_id, s.saved_at, p.product_id, p.product_name, p.loan_type,
               p.min_interest_rate, p.max_interest_rate, p.processing_fee_percent,
               p.last_updated, b.name AS bank_name
        FROM saved_offers s
        JOIN loan_products p ON p.product_id = s.product_id
        JOIN banks b ON b.bank_id = p.bank_id
        WHERE s.user_id = %s
        ORDER BY s.saved_at DESC
        """,
        (user_id,),
    )

    # "Best rate now" is worked out when the page is viewed, so later rate changes show up here.
    history = query(
        """
        SELECT h.history_id, h.loan_type, h.amount, h.tenure_months, h.searched_at,
               (SELECT MIN(p.min_interest_rate)
                  FROM loan_products p
                 WHERE p.loan_type = h.loan_type AND p.is_active = 1
                   AND p.min_amount <= h.amount AND p.max_amount >= h.amount
                   AND p.min_tenure_months <= h.tenure_months
                   AND p.max_tenure_months >= h.tenure_months) AS best_rate_now
        FROM comparison_history h
        WHERE h.user_id = %s
        ORDER BY h.searched_at DESC
        LIMIT 20
        """,
        (user_id,),
    )
    return render_template("dashboard.html", saved=saved, history=history)


@app.route("/dashboard/rerun/<int:history_id>", methods=["POST"])
@login_required
def rerun(history_id):
    row = query(
        "SELECT loan_type, amount, tenure_months FROM comparison_history "
        "WHERE history_id = %s AND user_id = %s",
        (history_id, session["user_id"]),
        one=True,
    )
    if row is None:
        abort(404)
    return redirect(url_for("compare", loan_type=row["loan_type"],
                            amount=int(row["amount"]), tenure=row["tenure_months"]))


# ============================================================
# Admin panel: banks and loan products (CRUD)
# ============================================================

def is_http_url(value):
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def read_bank_form():
    data = {
        "name": request.form.get("name", "").strip(),
        "short_name": request.form.get("short_name", "").strip(),
        "logo_url": request.form.get("logo_url", "").strip() or None,
        "website_url": request.form.get("website_url", "").strip() or None,
    }
    errors = []
    if not data["name"]:
        errors.append("Bank name is required.")
    if not data["short_name"]:
        errors.append("Short name is required.")
    if data["website_url"] and not is_http_url(data["website_url"]):
        errors.append("Website URL must start with http:// or https://.")
    if data["logo_url"] and not (is_http_url(data["logo_url"]) or data["logo_url"].startswith("/static/")):
        errors.append("Logo URL must start with http:// or https://.")
    return data, errors


def read_product_form():
    form = request.form
    errors = []
    data = {
        "bank_id": form.get("bank_id", ""),
        "loan_type": form.get("loan_type", ""),
        "product_name": form.get("product_name", "").strip(),
        "eligibility_criteria": form.get("eligibility_criteria", "").strip() or None,
        "source_url": form.get("source_url", "").strip(),
        "is_active": 1 if form.get("is_active") else 0,
    }

    def number(name, label, cast=Decimal, minimum=0):
        try:
            value = cast(form.get(name, "").strip())
        except (InvalidOperation, ValueError):
            errors.append(f"{label} must be a number.")
            return None
        if value < minimum:
            errors.append(f"{label} must be at least {minimum}.")
        return value

    data["min_interest_rate"] = number("min_interest_rate", "Minimum interest rate")
    data["max_interest_rate"] = number("max_interest_rate", "Maximum interest rate")
    data["min_amount"] = number("min_amount", "Minimum amount", minimum=1)
    data["max_amount"] = number("max_amount", "Maximum amount", minimum=1)
    data["min_tenure_months"] = number("min_tenure_months", "Minimum tenure", int, 1)
    data["max_tenure_months"] = number("max_tenure_months", "Maximum tenure", int, 1)
    data["processing_fee_percent"] = number("processing_fee_percent", "Processing fee %")
    data["processing_fee_flat"] = number("processing_fee_flat", "Flat processing fee")

    if not data["bank_id"].isdigit():
        errors.append("Choose a bank.")
    if data["loan_type"] not in LOAN_TYPES:
        errors.append("Choose a loan type.")
    if not data["product_name"]:
        errors.append("Product name is required.")
    if not is_http_url(data["source_url"]):
        errors.append("Source URL must start with http:// or https:// (every record needs a source).")

    for low, high, label in (("min_interest_rate", "max_interest_rate", "interest rate"),
                             ("min_amount", "max_amount", "amount"),
                             ("min_tenure_months", "max_tenure_months", "tenure")):
        if data[low] is not None and data[high] is not None and data[low] > data[high]:
            errors.append(f"Minimum {label} cannot be more than the maximum.")
    return data, errors


def log_rate_change(product_id, data, note):
    """Every rate or fee change is recorded in loan_rate_history (an audit trail)."""
    execute(
        """
        INSERT INTO loan_rate_history
          (product_id, min_interest_rate, max_interest_rate, processing_fee_percent, changed_by, change_note)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (product_id, data["min_interest_rate"], data["max_interest_rate"],
         data["processing_fee_percent"], session["user_id"], note),
    )


@app.route("/admin")
@admin_required
def admin_dashboard():
    counts = query(
        """
        SELECT (SELECT COUNT(*) FROM users)          AS users,
               (SELECT COUNT(*) FROM banks)          AS banks,
               (SELECT COUNT(*) FROM loan_products)  AS products,
               (SELECT COUNT(*) FROM saved_offers)   AS saved
        """,
        one=True,
    )
    recent = query(
        """
        SELECT r.history_id, r.min_interest_rate, r.max_interest_rate, r.processing_fee_percent,
               r.change_note, r.recorded_at, p.product_name, b.name AS bank_name,
               u.full_name AS changed_by
        FROM loan_rate_history r
        JOIN loan_products p ON p.product_id = r.product_id
        JOIN banks b ON b.bank_id = p.bank_id
        LEFT JOIN users u ON u.user_id = r.changed_by
        ORDER BY r.recorded_at DESC, r.history_id DESC
        LIMIT 10
        """
    )
    return render_template("admin_dashboard.html", counts=counts, recent=recent)


@app.route("/admin/banks")
@admin_required
def admin_banks():
    banks = query(
        """
        SELECT b.bank_id, b.name, b.short_name, b.website_url, COUNT(p.product_id) AS product_count
        FROM banks b
        LEFT JOIN loan_products p ON p.bank_id = b.bank_id
        GROUP BY b.bank_id, b.name, b.short_name, b.website_url
        ORDER BY b.name
        """
    )
    return render_template("admin_banks.html", banks=banks)


@app.route("/admin/banks/new", methods=["GET", "POST"])
@admin_required
def admin_bank_new():
    if request.method == "POST":
        data, errors = read_bank_form()
        if not errors:
            try:
                execute(
                    "INSERT INTO banks (name, short_name, logo_url, website_url) VALUES (%s, %s, %s, %s)",
                    (data["name"], data["short_name"], data["logo_url"], data["website_url"]),
                )
            except pymysql.err.IntegrityError:
                errors.append("A bank with that name already exists.")
            else:
                flash("Bank added.", "success")
                return redirect(url_for("admin_banks"))
        for message in errors:
            flash(message, "error")
        return render_template("admin_bank_form.html", bank=None, form=request.form), 400
    return render_template("admin_bank_form.html", bank=None, form={})


@app.route("/admin/banks/<int:bank_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_bank_edit(bank_id):
    bank = query("SELECT * FROM banks WHERE bank_id = %s", (bank_id,), one=True)
    if bank is None:
        abort(404)
    if request.method == "POST":
        data, errors = read_bank_form()
        if not errors:
            try:
                execute(
                    "UPDATE banks SET name = %s, short_name = %s, logo_url = %s, website_url = %s "
                    "WHERE bank_id = %s",
                    (data["name"], data["short_name"], data["logo_url"], data["website_url"], bank_id),
                )
            except pymysql.err.IntegrityError:
                errors.append("A bank with that name already exists.")
            else:
                flash("Bank updated.", "success")
                return redirect(url_for("admin_banks"))
        for message in errors:
            flash(message, "error")
        return render_template("admin_bank_form.html", bank=bank, form=request.form), 400
    return render_template("admin_bank_form.html", bank=bank, form=bank)


@app.route("/admin/banks/<int:bank_id>/delete", methods=["POST"])
@admin_required
def admin_bank_delete(bank_id):
    # ON DELETE CASCADE removes the bank's loan products too.
    if not execute("DELETE FROM banks WHERE bank_id = %s", (bank_id,)):
        abort(404)
    flash("Bank and all of its loan products were deleted.", "success")
    return redirect(url_for("admin_banks"))


@app.route("/admin/products")
@admin_required
def admin_products():
    products = query(
        """
        SELECT p.product_id, p.product_name, p.loan_type, p.min_interest_rate, p.max_interest_rate,
               p.processing_fee_percent, p.last_updated, p.is_active, b.name AS bank_name
        FROM loan_products p
        JOIN banks b ON b.bank_id = p.bank_id
        ORDER BY b.name, p.loan_type
        """
    )
    return render_template("admin_products.html", products=products)


@app.route("/admin/products/new", methods=["GET", "POST"])
@admin_required
def admin_product_new():
    banks = query("SELECT bank_id, name FROM banks ORDER BY name")
    if request.method == "POST":
        data, errors = read_product_form()
        if not errors:
            product_id = execute(
                """
                INSERT INTO loan_products
                  (bank_id, loan_type, product_name, min_interest_rate, max_interest_rate,
                   min_amount, max_amount, min_tenure_months, max_tenure_months,
                   processing_fee_percent, processing_fee_flat, eligibility_criteria,
                   source_url, last_updated, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (data["bank_id"], data["loan_type"], data["product_name"],
                 data["min_interest_rate"], data["max_interest_rate"],
                 data["min_amount"], data["max_amount"],
                 data["min_tenure_months"], data["max_tenure_months"],
                 data["processing_fee_percent"], data["processing_fee_flat"],
                 data["eligibility_criteria"], data["source_url"], date.today(), data["is_active"]),
                lastrowid=True,
            )
            log_rate_change(product_id, data, "Product created")
            flash("Loan product added.", "success")
            return redirect(url_for("admin_products"))
        for message in errors:
            flash(message, "error")
        return render_template("admin_product_form.html", banks=banks, form=request.form, product=None), 400
    return render_template("admin_product_form.html", banks=banks, form={"is_active": 1}, product=None)


@app.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_product_edit(product_id):
    product = query("SELECT * FROM loan_products WHERE product_id = %s", (product_id,), one=True)
    if product is None:
        abort(404)
    banks = query("SELECT bank_id, name FROM banks ORDER BY name")

    if request.method == "POST":
        data, errors = read_product_form()
        if not errors:
            execute(
                """
                UPDATE loan_products
                   SET bank_id = %s, loan_type = %s, product_name = %s,
                       min_interest_rate = %s, max_interest_rate = %s,
                       min_amount = %s, max_amount = %s,
                       min_tenure_months = %s, max_tenure_months = %s,
                       processing_fee_percent = %s, processing_fee_flat = %s,
                       eligibility_criteria = %s, source_url = %s, last_updated = %s, is_active = %s
                 WHERE product_id = %s
                """,
                (data["bank_id"], data["loan_type"], data["product_name"],
                 data["min_interest_rate"], data["max_interest_rate"],
                 data["min_amount"], data["max_amount"],
                 data["min_tenure_months"], data["max_tenure_months"],
                 data["processing_fee_percent"], data["processing_fee_flat"],
                 data["eligibility_criteria"], data["source_url"], date.today(),
                 data["is_active"], product_id),
            )
            pricing_changed = (
                Decimal(product["min_interest_rate"]) != data["min_interest_rate"]
                or Decimal(product["max_interest_rate"]) != data["max_interest_rate"]
                or Decimal(product["processing_fee_percent"]) != data["processing_fee_percent"]
            )
            if pricing_changed:
                note = request.form.get("change_note", "").strip() or "Rate/fee updated"
                log_rate_change(product_id, data, note)
            flash("Loan product updated.", "success")
            return redirect(url_for("admin_products"))
        for message in errors:
            flash(message, "error")
        return render_template("admin_product_form.html", banks=banks, form=request.form, product=product), 400
    return render_template("admin_product_form.html", banks=banks, form=product, product=product)


@app.route("/admin/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def admin_product_delete(product_id):
    if not execute("DELETE FROM loan_products WHERE product_id = %s", (product_id,)):
        abort(404)
    flash("Loan product deleted.", "success")
    return redirect(url_for("admin_products"))


# ============================================================
# Analytics: charts drawn from GROUP BY queries, plus CSV downloads
# ============================================================

@app.route("/analytics")
def analytics():
    return render_template("analytics.html")


@app.route("/api/analytics")
def api_analytics():
    """Numbers for the charts on the Analytics page (script.js draws them)."""
    loan_type = request.args.get("loan_type", "")
    if loan_type not in LOAN_TYPES:
        return jsonify(error=f"loan_type must be one of: {', '.join(LOAN_TYPES)}"), 400

    # Every product of the chosen loan type with its bank, cheapest first
    products = query(
        """
        SELECT b.name AS bank, b.short_name, p.product_name, p.min_interest_rate, p.max_interest_rate,
               p.processing_fee_percent, p.min_tenure_months, p.max_tenure_months
        FROM loan_products p
        JOIN banks b ON b.bank_id = p.bank_id
        WHERE p.is_active = 1 AND p.loan_type = %s
        ORDER BY p.min_interest_rate, b.name
        """,
        (loan_type,),
    )

    # Average starting rate for each loan type, across all banks
    by_type = query(
        """
        SELECT loan_type, ROUND(AVG(min_interest_rate), 2) AS avg_rate, COUNT(*) AS products
        FROM loan_products
        WHERE is_active = 1
        GROUP BY loan_type
        ORDER BY avg_rate
        """
    )

    # Average starting rate for each bank, across all of its loan types
    by_bank = query(
        """
        SELECT b.name AS bank, b.short_name, ROUND(AVG(p.min_interest_rate), 2) AS avg_rate, COUNT(*) AS products
        FROM loan_products p
        JOIN banks b ON b.bank_id = p.bank_id
        WHERE p.is_active = 1
        GROUP BY b.bank_id, b.name, b.short_name
        ORDER BY avg_rate
        """
    )

    # How often each loan type has been searched (all users together) - pie chart
    searches = query(
        """
        SELECT loan_type, COUNT(*) AS total
        FROM comparison_history
        GROUP BY loan_type
        ORDER BY total DESC
        """
    )

    # Which banks' offers people save the most - pie chart
    saved = query(
        """
        SELECT b.name AS bank, COUNT(*) AS total
        FROM saved_offers s
        JOIN loan_products p ON p.product_id = s.product_id
        JOIN banks b ON b.bank_id = p.bank_id
        GROUP BY b.bank_id, b.name
        ORDER BY total DESC
        """
    )

    return jsonify(
        loan_type=loan_type,
        products=[to_json_row(row) for row in products],
        by_type=[to_json_row(row) for row in by_type],
        by_bank=[to_json_row(row) for row in by_bank],
        searches=[to_json_row(row) for row in searches],
        saved=[to_json_row(row) for row in saved],
    )


def csv_download(filename, columns, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(["" if row.get(col) is None else row[col] for col in columns])
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/analytics/export/loan_products.csv")
def export_products():
    # One row per loan product with its bank, for opening in Excel or any analysis tool.
    columns = ["bank", "bank_short_name", "loan_type", "product_name", "min_interest_rate",
               "max_interest_rate", "avg_interest_rate", "min_amount", "max_amount",
               "min_tenure_months", "max_tenure_months", "processing_fee_percent",
               "processing_fee_flat", "source_url", "last_updated"]
    rows = query(
        """
        SELECT b.name AS bank, b.short_name AS bank_short_name, p.loan_type, p.product_name,
               p.min_interest_rate, p.max_interest_rate,
               ROUND((p.min_interest_rate + p.max_interest_rate) / 2, 2) AS avg_interest_rate,
               p.min_amount, p.max_amount, p.min_tenure_months, p.max_tenure_months,
               p.processing_fee_percent, p.processing_fee_flat, p.source_url, p.last_updated
        FROM loan_products p
        JOIN banks b ON b.bank_id = p.bank_id
        WHERE p.is_active = 1
        ORDER BY b.name, p.loan_type
        """
    )
    return csv_download("lendease_loan_products.csv", columns, rows)


@app.route("/analytics/export/rate_history.csv")
def export_rate_history():
    columns = ["bank", "loan_type", "product_name", "min_interest_rate", "max_interest_rate",
               "processing_fee_percent", "change_note", "recorded_at"]
    rows = query(
        """
        SELECT b.name AS bank, p.loan_type, p.product_name, r.min_interest_rate, r.max_interest_rate,
               r.processing_fee_percent, r.change_note, r.recorded_at
        FROM loan_rate_history r
        JOIN loan_products p ON p.product_id = r.product_id
        JOIN banks b ON b.bank_id = p.bank_id
        ORDER BY r.recorded_at, r.history_id
        """
    )
    return csv_download("lendease_rate_history.csv", columns, rows)


if __name__ == "__main__":
    # Running this file starts the website and opens it in the browser.
    address = "http://127.0.0.1:5000"
    print("LendEase is running at", address, "(press Ctrl+C to stop)")
    threading.Timer(1.5, webbrowser.open, args=[address]).start()   # wait for the server to start
    app.run()
