-- =====================================================================
-- LendEase: Loan Comparison & Financial Analytics Platform
-- MySQL 8.0.16+ (CHECK constraints are enforced from 8.0.16)
--
-- DATA DISCLAIMER: every interest rate, fee, amount and tenure below is
-- ILLUSTRATIVE REFERENCE DATA modelled on ranges publicly advertised by
-- Indian banks. It is demo data for a college project, not a live or
-- personalised offer. source_url points at each bank's public website;
-- replace it with the exact rate page when you refresh the data.
--
-- Usage:  mysql -u root -p < database/lendEase.sql
-- =====================================================================

CREATE DATABASE IF NOT EXISTS lendease CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE lendease;

-- Drop in reverse dependency order so the script can be re-run safely.
DROP TABLE IF EXISTS comparison_history;
DROP TABLE IF EXISTS saved_offers;
DROP TABLE IF EXISTS loan_rate_history;
DROP TABLE IF EXISTS loan_products;
DROP TABLE IF EXISTS banks;
DROP TABLE IF EXISTS users;

-- ---------------------------------------------------------------- users
CREATE TABLE users (
    user_id        INT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name      VARCHAR(100) NOT NULL,
    email          VARCHAR(150) NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    is_admin       TINYINT(1)   NOT NULL DEFAULT 0,
    created_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- banks
CREATE TABLE banks (
    bank_id      INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name         VARCHAR(100) NOT NULL,
    short_name   VARCHAR(20)  NOT NULL,
    logo_url     VARCHAR(255) NULL,
    website_url  VARCHAR(255) NULL,
    created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_id),
    UNIQUE KEY uq_banks_name (name)
) ENGINE=InnoDB;

-- -------------------------------------------------------- loan_products
CREATE TABLE loan_products (
    product_id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
    bank_id                 INT UNSIGNED NOT NULL,
    loan_type               ENUM('Home Loan','Personal Loan','Car Loan','Education Loan','Business Loan') NOT NULL,
    product_name            VARCHAR(120) NOT NULL,
    min_interest_rate       DECIMAL(5,2)  NOT NULL,
    max_interest_rate       DECIMAL(5,2)  NOT NULL,
    min_amount              DECIMAL(12,2) NOT NULL,
    max_amount              DECIMAL(12,2) NOT NULL,
    min_tenure_months       SMALLINT UNSIGNED NOT NULL,
    max_tenure_months       SMALLINT UNSIGNED NOT NULL,
    processing_fee_percent  DECIMAL(4,2)  NOT NULL DEFAULT 0.00,
    processing_fee_flat     DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    eligibility_criteria    TEXT NULL,
    source_url              VARCHAR(255) NOT NULL,
    last_updated            DATE NOT NULL,
    is_active               TINYINT(1) NOT NULL DEFAULT 1,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id),
    KEY idx_products_loan_type (loan_type),
    KEY idx_products_bank (bank_id),
    CONSTRAINT fk_products_bank FOREIGN KEY (bank_id) REFERENCES banks (bank_id) ON DELETE CASCADE,
    CONSTRAINT chk_rate   CHECK (min_interest_rate <= max_interest_rate),
    CONSTRAINT chk_amount CHECK (min_amount <= max_amount),
    CONSTRAINT chk_tenure CHECK (min_tenure_months <= max_tenure_months)
) ENGINE=InnoDB;

-- ----------------------------------------------------- loan_rate_history
-- Audit trail: one row per recorded rate/fee change.
CREATE TABLE loan_rate_history (
    history_id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_id              INT UNSIGNED NOT NULL,
    min_interest_rate       DECIMAL(5,2) NOT NULL,
    max_interest_rate       DECIMAL(5,2) NOT NULL,
    processing_fee_percent  DECIMAL(4,2) NOT NULL,
    changed_by              INT UNSIGNED NULL,
    change_note             VARCHAR(255) NULL,
    recorded_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (history_id),
    KEY idx_rate_history_product (product_id),
    CONSTRAINT fk_rate_history_product FOREIGN KEY (product_id) REFERENCES loan_products (product_id) ON DELETE CASCADE,
    CONSTRAINT fk_rate_history_user    FOREIGN KEY (changed_by) REFERENCES users (user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------- saved_offers
CREATE TABLE saved_offers (
    saved_id    INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id     INT UNSIGNED NOT NULL,
    product_id  INT UNSIGNED NOT NULL,
    notes       VARCHAR(255) NULL,
    saved_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (saved_id),
    UNIQUE KEY uq_saved_user_product (user_id, product_id),
    CONSTRAINT fk_saved_user    FOREIGN KEY (user_id)    REFERENCES users (user_id)          ON DELETE CASCADE,
    CONSTRAINT fk_saved_product FOREIGN KEY (product_id) REFERENCES loan_products (product_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------- comparison_history
-- Stores only the search inputs; results are recomputed from live loan_products when viewed.
CREATE TABLE comparison_history (
    history_id     INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id        INT UNSIGNED NOT NULL,
    loan_type      ENUM('Home Loan','Personal Loan','Car Loan','Education Loan','Business Loan') NOT NULL,
    amount         DECIMAL(12,2) NOT NULL,
    tenure_months  SMALLINT UNSIGNED NOT NULL,
    searched_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (history_id),
    KEY idx_comparison_user (user_id, searched_at),
    CONSTRAINT fk_comparison_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =====================================================================
-- SAMPLE DATA (illustrative reference data, not live rates)
-- Users are created by scripts/seed_admin.py so password hashes match your
-- installed Werkzeug version.
-- =====================================================================

INSERT INTO banks (bank_id, name, short_name, website_url) VALUES
    (1, 'State Bank of India', 'SBI', 'https://sbi.co.in'),
    (2, 'HDFC Bank', 'HDFC', 'https://www.hdfcbank.com'),
    (3, 'ICICI Bank', 'ICICI', 'https://www.icicibank.com'),
    (4, 'Axis Bank', 'Axis', 'https://www.axisbank.com'),
    (5, 'Kotak Mahindra Bank', 'Kotak', 'https://www.kotak.com'),
    (6, 'Punjab National Bank', 'PNB', 'https://www.pnbindia.in');

INSERT INTO loan_products
    (bank_id, loan_type, product_name, min_interest_rate, max_interest_rate, min_amount, max_amount,
     min_tenure_months, max_tenure_months, processing_fee_percent, processing_fee_flat,
     eligibility_criteria, source_url, last_updated)
VALUES
    (1, 'Home Loan', 'SBI Home Loan', 8.50, 9.65, 500000, 100000000, 60, 360, 0.35, 0.00, 'Salaried or self-employed, age 21-65 at maturity, steady income, good credit history.', 'https://sbi.co.in', '2026-09-30'),
    (1, 'Personal Loan', 'SBI Personal Loan', 11.45, 14.30, 50000, 4000000, 12, 72, 1.50, 0.00, 'Salaried or self-employed, age 21-60, minimum monthly income and credit score apply.', 'https://sbi.co.in', '2026-09-30'),
    (1, 'Car Loan', 'SBI Car Loan', 8.75, 9.70, 100000, 20000000, 12, 84, 0.25, 0.00, 'Salaried or self-employed, age 21-65, minimum annual income, valid KYC.', 'https://sbi.co.in', '2026-09-30'),
    (1, 'Education Loan', 'SBI Education Loan', 8.15, 10.50, 100000, 15000000, 12, 180, 0.00, 0.00, 'Admission to a recognised course in India or abroad; co-applicant (parent/guardian) usually required.', 'https://sbi.co.in', '2026-09-30'),
    (1, 'Business Loan', 'SBI Business Loan', 10.50, 14.00, 100000, 50000000, 12, 120, 1.00, 0.00, 'Business vintage of 2+ years, turnover and ITR/financial statements required.', 'https://sbi.co.in', '2026-09-30'),
    (2, 'Home Loan', 'HDFC Home Loan', 8.75, 9.65, 500000, 100000000, 60, 360, 0.50, 0.00, 'Salaried or self-employed, age 21-65 at maturity, steady income, good credit history.', 'https://www.hdfcbank.com', '2026-09-30'),
    (2, 'Personal Loan', 'HDFC Personal Loan', 10.85, 24.00, 50000, 4000000, 12, 72, 2.50, 0.00, 'Salaried or self-employed, age 21-60, minimum monthly income and credit score apply.', 'https://www.hdfcbank.com', '2026-09-30'),
    (2, 'Car Loan', 'HDFC Car Loan', 9.20, 12.50, 100000, 20000000, 12, 84, 0.80, 0.00, 'Salaried or self-employed, age 21-65, minimum annual income, valid KYC.', 'https://www.hdfcbank.com', '2026-09-30'),
    (2, 'Education Loan', 'HDFC Education Loan', 9.55, 13.25, 100000, 15000000, 12, 180, 1.00, 0.00, 'Admission to a recognised course in India or abroad; co-applicant (parent/guardian) usually required.', 'https://www.hdfcbank.com', '2026-09-30'),
    (2, 'Business Loan', 'HDFC Business Loan', 11.50, 17.00, 100000, 50000000, 12, 120, 2.00, 0.00, 'Business vintage of 2+ years, turnover and ITR/financial statements required.', 'https://www.hdfcbank.com', '2026-09-30'),
    (3, 'Home Loan', 'ICICI Home Loan', 8.75, 9.80, 500000, 100000000, 60, 360, 0.50, 0.00, 'Salaried or self-employed, age 21-65 at maturity, steady income, good credit history.', 'https://www.icicibank.com', '2026-09-30'),
    (3, 'Personal Loan', 'ICICI Personal Loan', 10.80, 16.50, 50000, 4000000, 12, 72, 2.25, 0.00, 'Salaried or self-employed, age 21-60, minimum monthly income and credit score apply.', 'https://www.icicibank.com', '2026-09-30'),
    (3, 'Car Loan', 'ICICI Car Loan', 9.10, 11.80, 100000, 20000000, 12, 84, 1.00, 0.00, 'Salaried or self-employed, age 21-65, minimum annual income, valid KYC.', 'https://www.icicibank.com', '2026-09-30'),
    (3, 'Education Loan', 'ICICI Education Loan', 9.50, 12.75, 100000, 15000000, 12, 180, 1.00, 0.00, 'Admission to a recognised course in India or abroad; co-applicant (parent/guardian) usually required.', 'https://www.icicibank.com', '2026-09-30'),
    (3, 'Business Loan', 'ICICI Business Loan', 11.00, 16.50, 100000, 50000000, 12, 120, 2.00, 0.00, 'Business vintage of 2+ years, turnover and ITR/financial statements required.', 'https://www.icicibank.com', '2026-09-30'),
    (4, 'Home Loan', 'Axis Home Loan', 8.75, 9.65, 500000, 100000000, 60, 360, 1.00, 0.00, 'Salaried or self-employed, age 21-65 at maturity, steady income, good credit history.', 'https://www.axisbank.com', '2026-09-30'),
    (4, 'Personal Loan', 'Axis Personal Loan', 10.49, 22.00, 50000, 4000000, 12, 72, 2.00, 0.00, 'Salaried or self-employed, age 21-60, minimum monthly income and credit score apply.', 'https://www.axisbank.com', '2026-09-30'),
    (4, 'Car Loan', 'Axis Car Loan', 9.30, 13.00, 100000, 20000000, 12, 84, 1.00, 0.00, 'Salaried or self-employed, age 21-65, minimum annual income, valid KYC.', 'https://www.axisbank.com', '2026-09-30'),
    (4, 'Education Loan', 'Axis Education Loan', 9.70, 13.50, 100000, 15000000, 12, 180, 1.00, 0.00, 'Admission to a recognised course in India or abroad; co-applicant (parent/guardian) usually required.', 'https://www.axisbank.com', '2026-09-30'),
    (4, 'Business Loan', 'Axis Business Loan', 11.25, 17.00, 100000, 50000000, 12, 120, 2.00, 0.00, 'Business vintage of 2+ years, turnover and ITR/financial statements required.', 'https://www.axisbank.com', '2026-09-30'),
    (5, 'Home Loan', 'Kotak Home Loan', 8.75, 9.50, 500000, 100000000, 60, 360, 0.50, 0.00, 'Salaried or self-employed, age 21-65 at maturity, steady income, good credit history.', 'https://www.kotak.com', '2026-09-30'),
    (5, 'Personal Loan', 'Kotak Personal Loan', 10.99, 24.00, 50000, 4000000, 12, 72, 2.00, 0.00, 'Salaried or self-employed, age 21-60, minimum monthly income and credit score apply.', 'https://www.kotak.com', '2026-09-30'),
    (5, 'Car Loan', 'Kotak Car Loan', 8.90, 11.50, 100000, 20000000, 12, 84, 0.50, 0.00, 'Salaried or self-employed, age 21-65, minimum annual income, valid KYC.', 'https://www.kotak.com', '2026-09-30'),
    (5, 'Education Loan', 'Kotak Education Loan', 9.40, 12.00, 100000, 15000000, 12, 180, 0.50, 0.00, 'Admission to a recognised course in India or abroad; co-applicant (parent/guardian) usually required.', 'https://www.kotak.com', '2026-09-30'),
    (5, 'Business Loan', 'Kotak Business Loan', 11.00, 18.00, 100000, 50000000, 12, 120, 1.75, 0.00, 'Business vintage of 2+ years, turnover and ITR/financial statements required.', 'https://www.kotak.com', '2026-09-30'),
    (6, 'Home Loan', 'PNB Home Loan', 8.45, 10.25, 500000, 100000000, 60, 360, 0.35, 0.00, 'Salaried or self-employed, age 21-65 at maturity, steady income, good credit history.', 'https://www.pnbindia.in', '2026-09-30'),
    (6, 'Personal Loan', 'PNB Personal Loan', 10.40, 17.95, 50000, 4000000, 12, 72, 1.00, 0.00, 'Salaried or self-employed, age 21-60, minimum monthly income and credit score apply.', 'https://www.pnbindia.in', '2026-09-30'),
    (6, 'Car Loan', 'PNB Car Loan', 8.80, 10.50, 100000, 20000000, 12, 84, 0.25, 0.00, 'Salaried or self-employed, age 21-65, minimum annual income, valid KYC.', 'https://www.pnbindia.in', '2026-09-30'),
    (6, 'Education Loan', 'PNB Education Loan', 8.25, 10.65, 100000, 15000000, 12, 180, 0.00, 0.00, 'Admission to a recognised course in India or abroad; co-applicant (parent/guardian) usually required.', 'https://www.pnbindia.in', '2026-09-30'),
    (6, 'Business Loan', 'PNB Business Loan', 10.60, 15.00, 100000, 50000000, 12, 120, 1.00, 0.00, 'Business vintage of 2+ years, turnover and ITR/financial statements required.', 'https://www.pnbindia.in', '2026-09-30');

-- Sample rate changes (changed_by is NULL here; changes made in the admin panel record the admin).
INSERT INTO loan_rate_history (product_id, min_interest_rate, max_interest_rate, processing_fee_percent, change_note, recorded_at) VALUES
    (1, 8.60, 9.75, 0.35, 'Previous reference rate', '2026-06-15 10:00:00'),
    (1, 8.50, 9.65, 0.35, 'Reference rate revised', '2026-09-30 10:00:00'),
    (7, 11.25, 24.00, 2.50, 'Previous reference rate', '2026-07-01 10:00:00'),
    (7, 10.85, 24.00, 2.50, 'Reference rate revised', '2026-09-30 10:00:00');


-- =====================================================================
-- QUERY LIBRARY
-- Commented so this file stays runnable. The app uses the same kind of
-- SQL in app.py; uncomment any query to try it in MySQL.
-- =====================================================================

-- 1. Bank-wise comparison (JOIN) filtered by loan type and amount
-- SELECT b.name AS bank, p.product_name, p.min_interest_rate, p.max_interest_rate,
--        p.processing_fee_percent, p.min_tenure_months, p.max_tenure_months,
--        p.source_url, p.last_updated
-- FROM loan_products p
-- JOIN banks b ON b.bank_id = p.bank_id
-- WHERE p.is_active = 1 AND p.loan_type = 'Home Loan'
--   AND p.min_amount <= 3000000 AND p.max_amount >= 3000000
-- ORDER BY p.min_interest_rate;

-- 2. Average interest rate by bank (GROUP BY)
-- SELECT b.name AS bank,
--        ROUND(AVG((p.min_interest_rate + p.max_interest_rate) / 2), 2) AS avg_rate
-- FROM loan_products p JOIN banks b ON b.bank_id = p.bank_id
-- GROUP BY b.bank_id, b.name ORDER BY avg_rate;

-- 3. Average rate by loan type
-- SELECT loan_type, ROUND(AVG(min_interest_rate), 2) AS avg_min_rate,
--        ROUND(AVG(max_interest_rate), 2) AS avg_max_rate
-- FROM loan_products GROUP BY loan_type;

-- 4. Number of products per bank
-- SELECT b.name AS bank, COUNT(p.product_id) AS products
-- FROM banks b LEFT JOIN loan_products p ON p.bank_id = b.bank_id
-- GROUP BY b.bank_id, b.name;

-- 5. Rate change history with the admin who made the change (3-table JOIN)
-- SELECT r.recorded_at, b.name AS bank, p.product_name, r.min_interest_rate,
--        r.max_interest_rate, r.change_note, u.full_name AS changed_by
-- FROM loan_rate_history r
-- JOIN loan_products p ON p.product_id = r.product_id
-- JOIN banks b ON b.bank_id = p.bank_id
-- LEFT JOIN users u ON u.user_id = r.changed_by
-- ORDER BY r.recorded_at DESC;

-- 6. A user's saved offers
-- SELECT u.full_name, b.name AS bank, p.product_name, p.min_interest_rate, s.saved_at
-- FROM saved_offers s
-- JOIN users u ON u.user_id = s.user_id
-- JOIN loan_products p ON p.product_id = s.product_id
-- JOIN banks b ON b.bank_id = p.bank_id
-- WHERE s.user_id = 1;

-- 7. CRUD examples (parameterized with %s in the app)
-- INSERT INTO saved_offers (user_id, product_id) VALUES (1, 3);
-- UPDATE loan_products SET min_interest_rate = 8.40, last_updated = CURDATE() WHERE product_id = 1;
-- DELETE FROM saved_offers WHERE user_id = 1 AND product_id = 3;
