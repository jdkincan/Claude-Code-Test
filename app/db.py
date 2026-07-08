"""SQLite storage for the options toolkit.

Single local database file. Schema is created on first connect; ALTERs are
avoided by keeping the schema additive-only via CREATE TABLE IF NOT EXISTS.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DATA_DIR = Path(os.environ.get("PORTFOLIO_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    account_value REAL NOT NULL DEFAULT 10000,
    total_investable_assets REAL NOT NULL DEFAULT 100000,
    per_trade_risk_pct REAL NOT NULL DEFAULT 2.0,
    max_open_positions INTEGER NOT NULL DEFAULT 8
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    structure TEXT NOT NULL,
    direction TEXT NOT NULL,              -- bullish / bearish / neutral
    pillar TEXT NOT NULL,                 -- momentum+ / momentum- / vol / catalyst+ / catalyst-
    thesis TEXT NOT NULL DEFAULT '',
    entry_date TEXT NOT NULL,
    net_debit_credit REAL NOT NULL,       -- total dollars paid (negative = credit received)
    contracts INTEGER NOT NULL,
    notional_exposure REAL NOT NULL DEFAULT 0,
    max_loss REAL NOT NULL,               -- defined at entry, dollars (positive number)
    max_gain REAL,                        -- dollars; NULL = uncapped
    profit_target REAL NOT NULL,          -- dollars of profit at which to take gains
    stop_rule TEXT NOT NULL,              -- e.g. "close if position value < 50% of debit"
    time_exit_date TEXT NOT NULL,         -- hard calendar exit
    catalyst_date TEXT,                   -- optional dated catalyst
    status TEXT NOT NULL DEFAULT 'open',  -- open / closed
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trade_legs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    side TEXT NOT NULL,                   -- long / short
    option_type TEXT NOT NULL,            -- call / put / stock
    strike REAL,
    expiry TEXT,
    premium REAL                          -- per-share premium
);

CREATE TABLE IF NOT EXISTS trade_exits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    exit_date TEXT NOT NULL,
    proceeds REAL NOT NULL,               -- dollars received closing (negative = paid to close)
    realized_pl REAL NOT NULL,
    exit_reason TEXT NOT NULL,            -- target / stop / time / catalyst / discretionary
    followed_plan INTEGER NOT NULL DEFAULT 1,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL UNIQUE,
    theme TEXT NOT NULL DEFAULT '',
    catalyst_note TEXT NOT NULL DEFAULT '',
    catalyst_date TEXT,
    bias TEXT NOT NULL DEFAULT 'none',    -- bullish / bearish / none
    -- metrics: fetched from yfinance or entered manually; manual wins until re-fetch
    last_price REAL,
    ret_1m REAL, ret_3m REAL, ret_6m REAL,
    pct_from_52w_high REAL,
    above_sma50 INTEGER, above_sma200 INTEGER,
    realized_vol_20d REAL,
    vol_percentile REAL,                  -- 20d realized vol percentile over 1y (IV-rank proxy)
    atm_iv REAL,
    metrics_source TEXT,                  -- 'yfinance' / 'manual'
    metrics_updated_at TEXT
);

INSERT OR IGNORE INTO settings (id) VALUES (1);
"""


def get_db(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or DATA_DIR / "portfolio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
