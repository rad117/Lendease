<#
  Connect LendEase to a hosted MySQL in one go. Run it yourself from the project root:

      powershell -ExecutionPolicy Bypass -File scripts\connect_database.ps1

  You paste the connection URL once (input is hidden). The script then:
    1. saves it as DATABASE_URL in your local .env,
    2. stores it as a Vercel production environment variable,
    3. loads the tables + demo data (this DROPS and recreates the LendEase tables in that database),
    4. redeploys to production.

  Safe to re-run: if .env already has a DATABASE_URL you can reuse it instead of pasting again.
#>

# Native tools (vercel, python) write progress to stderr. Windows PowerShell turns redirected stderr
# into errors, so never "Stop" on those: each step checks the exit code instead.
$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Fail($message) { Write-Host "ERROR: $message" -ForegroundColor Red; exit 1 }

# ---- 1. connection URL -> .env
$url = $null
if (Test-Path .env) {
  $saved = Get-Content .env | Where-Object { $_ -match '^\s*DATABASE_URL=(.+)$' } | Select-Object -First 1
  if ($saved) {
    $reuse = Read-Host ".env already has a DATABASE_URL. Use it? (y = use saved, n = paste a new one)"
    if ($reuse -eq "y") { $url = ($saved -replace '^\s*DATABASE_URL=', '').Trim() }
  }
}
if (-not $url) {
  $secure = Read-Host "Paste your MySQL connection URL (mysql://user:password@host:port/dbname)" -AsSecureString
  $url = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)).Trim()
  if ($url -notmatch '^mysql(\+pymysql)?://') { Fail "That doesn't look like a mysql:// URL." }

  $lines = @()
  if (Test-Path .env) { $lines = @(Get-Content .env | Where-Object { $_ -notmatch '^\s*DATABASE_URL=' }) }
  $lines += "DATABASE_URL=$url"
  # No BOM: python-dotenv would otherwise read the first key as "﻿DATABASE_URL".
  [IO.File]::WriteAllLines((Join-Path (Get-Location) ".env"), $lines, (New-Object Text.UTF8Encoding($false)))
  Write-Host "Saved DATABASE_URL to .env"
}

# ---- 2. Vercel production env var (remove an old one first; it is fine if none exists)
cmd /c "vercel env rm DATABASE_URL production --yes >nul 2>&1"
$url | cmd /c "vercel env add DATABASE_URL production >nul 2>&1"
if ($LASTEXITCODE -ne 0) { Fail "Could not save DATABASE_URL to Vercel. Run 'vercel whoami' to check you are logged in." }
Write-Host "Saved DATABASE_URL to Vercel (production)"

# ---- 3. schema + demo data
$confirm = Read-Host "Load the tables + demo data? This DROPS and recreates the LendEase tables. (y = load, n = skip, already loaded)"
if ($confirm -eq "y") {
  & .\.venv\Scripts\python.exe scripts\init_db.py --yes
  if ($LASTEXITCODE -ne 0) { Fail "Loading the database failed; the message above says why. Nothing was deployed." }
} else {
  Write-Host "Skipped loading data."
}

# ---- 4. redeploy
cmd /c "vercel deploy --prod --yes 2>&1"
if ($LASTEXITCODE -ne 0) { Fail "Deploy failed; see the output above." }
Write-Host "Done. Log in on your site with demo@lendease.com / Demo@123" -ForegroundColor Green
