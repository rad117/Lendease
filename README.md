# LendEase: Loan Comparison & Financial Analytics Platform

LendEase lets users compare loan products from six major Indian banks (SBI, HDFC, ICICI, Axis, Kotak Mahindra, PNB), estimate EMIs, save offers, and explore the data on a built-in analytics page.

> **LendEase is not a lender.** All rates, fees and limits are illustrative reference data modelled on publicly advertised ranges. Each record carries a source URL and a last-updated date, and nothing is presented as a live or personalised offer. Always confirm terms on the bank's own website.

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | HTML, CSS, JavaScript (no frameworks) |
| Backend | Python, Flask |
| Database | MySQL, using raw parameterized SQL through PyMySQL (no ORM) |
| Analytics | Graphs and pie charts on the Analytics page, built from SQL `GROUP BY` queries and drawn with Chart.js |

## Features

- Compare loans by type, amount, tenure, bank and rate, with estimated EMI for each product
- EMI calculator
- Loan detail pages showing the source URL and last-updated date
- Register / log in, save offers, comparison history with "Run again"
- Admin panel: add, edit and delete banks and loan products; every rate change is logged to `loan_rate_history`
- Analytics page: bar charts, line graphs and pie charts comparing rates, monthly EMI, fees and what users search for and save, with filters for loan type, amount and tenure, plus CSV downloads

## Project structure

```
Lendease/
├── app.py                 the whole backend: database helpers, EMI formula, login, all routes
├── config.py              settings read from .env
├── requirements.txt
├── database/
│   └── lendEase.sql       tables, sample data and example queries
├── templates/             HTML pages (base.html is the shared layout)
├── static/
│   ├── style.css          all styles
│   └── script.js          all JavaScript (EMI calculator, compare page, save buttons)
├── scripts/               seed_admin.py (demo logins), init_db.py (load a hosted database)
└── tests/                 pytest tests
```

`app.py` is organised top to bottom in sections: database helpers, EMI formula, login checks, then the routes for each page (home, auth, compare, API, dashboard, admin, analytics).

## Setup

You need Python 3.10+ and MySQL 8.

```bash
# 1. Install dependencies
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 2. Settings
copy .env.example .env            # macOS/Linux: cp .env.example .env
#    then edit .env: set DB_PASSWORD and a long random SECRET_KEY

# 3. Create the database, tables and sample data
mysql -u root -p < database/lendEase.sql

# 4. Create the demo logins
python scripts/seed_admin.py

# 5. Run
python app.py                      # starts the site and opens http://127.0.0.1:5000 in the browser
```

Demo logins:

| Role | Email | Password |
|---|---|---|
| Admin | admin@lendease.com | Admin@123 |
| User | demo@lendease.com | Demo@123 |

## Database

Six tables: `users`, `banks`, `loan_products`, `loan_rate_history`, `saved_offers`, `comparison_history`.

- Foreign keys link products to banks, and saved offers / history to users (deleting a bank deletes its products).
- `saved_offers` has `UNIQUE(user_id, product_id)` so the same offer can't be saved twice.
- `loan_products` has CHECK constraints so the minimum rate, amount and tenure can't be above the maximum.

The bottom of `database/lendEase.sql` has example queries (JOIN, GROUP BY, INSERT, UPDATE, DELETE).

## Analytics

The Analytics page (`/analytics`) shows graphs and pie charts for a chosen loan type, amount and tenure:

| Chart | Type | Where the numbers come from |
|---|---|---|
| Lowest and highest interest rate by bank | grouped bar | `loan_products JOIN banks`, filtered by loan type |
| Monthly EMI by bank | bar | the EMI formula applied to each bank's starting rate |
| Where your money goes (principal vs interest) | doughnut | the EMI formula at the lowest rate |
| Monthly EMI by tenure | line | the EMI formula for each tenure |
| Total interest by tenure | line | the EMI formula for each tenure |
| Processing fee by bank | bar | `processing_fee_percent` per product |
| Average starting rate by loan type | bar | `AVG(min_interest_rate) ... GROUP BY loan_type` |
| Average starting rate by bank | bar | `AVG(min_interest_rate) ... GROUP BY bank` |
| Most searched loan types | pie | `COUNT(*) FROM comparison_history GROUP BY loan_type` |
| Saved offers by bank | pie | `COUNT(*) FROM saved_offers JOIN ... GROUP BY bank` |

The page asks `/api/analytics` for the data (see `api_analytics()` in `app.py`) and `script.js` draws the charts with [Chart.js](https://www.chartjs.org/), loaded from a CDN on this page only. The data can also be downloaded as CSV from the same page.

## Hosting (Vercel + hosted MySQL)

The live site runs on Vercel with a hosted MySQL (TiDB Cloud). Vercel finds the Flask app in `app.py` automatically.

1. Put the database's connection URL in `.env` as `DATABASE_URL=mysql://user:password@host:4000/dbname`.
2. Load the tables and demo data: `python scripts/init_db.py --yes` (this drops and recreates the LendEase tables).
3. Add the same `DATABASE_URL` and a `SECRET_KEY` in the Vercel project's environment variables.
4. Deploy: `vercel deploy --prod`.

`scripts/connect_database.ps1` does steps 1 to 4 in one go.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use a fake database, so they run without MySQL.
