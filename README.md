# Options Toolkit

A local, single-user web app for running a small, options-focused personal
brokerage account with discipline: momentum (either direction), volatility,
and thematic/catalyst trades — always defined-risk, with max P/L and exits
written down at entry, and total notional exposure capped at 1x account value.

## What's inside

| Page | What it does |
|---|---|
| **Dashboard** | Open positions, capital at risk, notional vs. the 1x leverage cap, overdue time-exits/catalysts, and a refresh button for live underlying prices |
| **Journal** | Log trades — max loss, profit target, stop rule, and time exit are required at entry; close with an exit reason and plan-adherence flag; CSV export |
| **Calculator** | Max loss/gain, breakevens, risk/reward, and suggested contract count for 8 structures (long call/put, debit/credit verticals, straddle, strangle, cash-secured put, covered call), with an interactive expiry payoff chart and one-click "send to journal" |
| **Screener** | Watchlist ranked by a composite score: momentum 45% (absolute strength, direction shown as bias), volatility 30% (extremes score high), catalyst proximity 25% |
| **Performance** | Win rate, avg win/loss, expectancy, P/L by strategy pillar, plan-adherence rate |
| **Playbook** | The written strategy rules (`docs/playbook.md`), rendered in-app |
| **Settings** | Account value, total investable assets, per-trade risk %, max open positions |

## Setup

```bash
pip install -r requirements.txt
python run.py
# open http://127.0.0.1:8000
```

Data lives in a local SQLite file at `data/portfolio.db` (created on first run,
gitignored). Set `PORTFOLIO_DATA_DIR` to store it elsewhere.

## Hosting it on the web (password protected)

Set `APP_PASSWORD` to require a login on every page (and `SECRET_KEY` so
sessions survive restarts):

```bash
APP_PASSWORD='your-password' SECRET_KEY='random-hex' python run.py
```

To get a permanent HTTPS link on a free GCP VM, see
**[docs/deploy-gcp.md](docs/deploy-gcp.md)** — one script run in Cloud Shell
sets up the VM, TLS via Caddy/Let's Encrypt, a DuckDNS hostname, systemd,
and nightly database backups.

## Verifying trades with an AI

**[docs/trade-verification.md](docs/trade-verification.md)** is a
copy-paste prompt for any AI: attach a screenshot of your broker's trade
confirmation plus the app's trade page (or a `/journal.csv` row) and it
reconciles the two field by field, aware of the app's conventions
(total-dollar amounts, negative credits, fee exclusions).

## Market data

The screener and price autofill use **yfinance** (Yahoo Finance) when online.
Every metric can also be entered manually per ticker — manual values persist
and everything keeps working offline; rows are marked with their source
(`yfinance` or `manual`).

## Tests

```bash
python -m pytest tests/ -q
```

Covers the options math (known-answer tests per structure), the screener
scoring, and full route flows (trade lifecycle, validation, manual screener
entry) via FastAPI's TestClient.

## Disclaimer

Personal record-keeping and analysis tooling only — not investment advice,
not a brokerage integration, and no order routing.
