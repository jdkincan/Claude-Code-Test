"""End-to-end route tests against a temporary database."""
import os
import tempfile

import pytest

_tmpdir = tempfile.mkdtemp()
os.environ["PORTFOLIO_DATA_DIR"] = _tmpdir

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


TRADE = {
    "ticker": "xyz", "structure": "debit_vertical", "direction": "bullish",
    "pillar": "momentum+", "thesis": "uptrend near highs", "entry_date": "2026-07-08",
    "net_debit_credit": "400", "contracts": "1", "notional_exposure": "10000",
    "max_loss": "400", "max_gain": "600", "profit_target": "300",
    "stop_rule": "close below 50% of debit", "time_exit_date": "2026-08-15",
    "catalyst_date": "",
}


def test_pages_render():
    for path in ["/", "/journal", "/trades/new", "/calculator", "/screener",
                 "/performance", "/playbook", "/settings"]:
        r = client.get(path)
        assert r.status_code == 200, path


def test_settings_save():
    r = client.post("/settings", data={
        "account_value": "25000", "total_investable_assets": "500000",
        "per_trade_risk_pct": "2.0", "max_open_positions": "6"})
    assert r.status_code == 200
    assert "Saved." in r.text


def test_trade_lifecycle():
    # create
    r = client.post("/trades", data=TRADE, follow_redirects=False)
    assert r.status_code == 303
    trade_url = r.headers["location"]

    # detail shows plan fields and uppercased ticker
    r = client.get(trade_url)
    assert "XYZ" in r.text
    assert "close below 50% of debit" in r.text

    # appears on dashboard as open with risk counted
    r = client.get("/")
    assert "XYZ" in r.text

    # close at the profit target
    r = client.post(f"{trade_url}/close", data={
        "exit_date": "2026-07-20", "proceeds": "700", "exit_reason": "target",
        "followed_plan": "1", "notes": ""}, follow_redirects=False)
    assert r.status_code == 303

    r = client.get(trade_url)
    assert "$300.00" in r.text  # realized P/L = 700 - 400

    # performance reflects the closed trade
    r = client.get("/performance")
    assert r.status_code == 200
    assert "100%" in r.text  # win rate and adherence

    # double close rejected
    r = client.post(f"{trade_url}/close", data={
        "exit_date": "2026-07-21", "proceeds": "0", "exit_reason": "target",
        "followed_plan": "1"})
    assert r.status_code == 400


def test_trade_validation():
    bad = dict(TRADE, max_loss="0")
    assert client.post("/trades", data=bad).status_code == 400
    bad = dict(TRADE, pillar="catalyst+", catalyst_date="")
    assert client.post("/trades", data=bad).status_code == 400
    bad = dict(TRADE, stop_rule="  ")
    assert client.post("/trades", data=bad).status_code == 400


def test_calculator_long_call():
    r = client.post("/calculator", data={
        "structure": "long_call", "spot": "100", "contracts": "2",
        "strike": "105", "premium": "2.50"})
    assert r.status_code == 200
    assert "$500.00" in r.text        # max loss
    assert "uncapped" in r.text
    assert "payoff-chart" in r.text


def test_calculator_bad_input_shows_error():
    r = client.post("/calculator", data={
        "structure": "debit_vertical", "spot": "100", "contracts": "1",
        "long_strike": "100", "short_strike": "105", "net_per_share": "9",
        "option_type": "call"})
    assert r.status_code == 200
    assert "Invalid input" in r.text


def test_screener_manual_flow():
    r = client.post("/screener/add", data={
        "ticker": "abc", "theme": "AI", "catalyst_note": "earnings",
        "catalyst_date": "2099-01-05", "bias": "bullish"}, follow_redirects=False)
    assert r.status_code == 303

    # manual metrics entry (offline path)
    from app.db import get_db
    conn = get_db()
    item_id = conn.execute("SELECT id FROM watchlist WHERE ticker = 'ABC'").fetchone()["id"]
    conn.close()

    r = client.post(f"/screener/{item_id}/update", data={
        "ret_1m": "0.08", "ret_3m": "0.15", "ret_6m": "0.30",
        "realized_vol_20d": "0.45", "vol_percentile": "90"}, follow_redirects=False)
    assert r.status_code == 303

    r = client.get("/screener")
    assert "ABC" in r.text
    assert "manual" in r.text
    assert "positive" in r.text  # momentum bias from manual returns

    # blank fields keep values; junk rejected
    r = client.post(f"/screener/{item_id}/update", data={"ret_1m": "not-a-number"})
    assert r.status_code == 400

    r = client.post(f"/screener/{item_id}/delete", follow_redirects=False)
    assert r.status_code == 303


def test_price_api_degrades_gracefully(monkeypatch):
    from app import market_data
    monkeypatch.setattr(market_data, "last_price", lambda t: None)
    r = client.get("/api/price/FAKE")
    assert r.status_code == 200
    assert r.json()["price"] is None
