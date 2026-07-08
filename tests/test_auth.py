"""Auth gate, price refresh, and CSV export tests."""
import os
import tempfile

os.environ.setdefault("PORTFOLIO_DATA_DIR", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_no_auth_when_password_unset(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    client = TestClient(app)
    assert client.get("/", follow_redirects=False).status_code == 200


def test_auth_gate(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "hunter2")
    client = TestClient(app)

    # everything redirects to /login when unauthenticated
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    assert client.get("/journal.csv", follow_redirects=False).status_code == 303

    # login page itself and static assets stay reachable
    assert client.get("/login").status_code == 200
    assert client.get("/static/style.css").status_code == 200

    # wrong password rejected
    r = client.post("/login", data={"password": "wrong"})
    assert r.status_code == 401
    assert client.get("/", follow_redirects=False).status_code == 303

    # correct password grants a session
    r = client.post("/login", data={"password": "hunter2"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 200
    assert "Log out" in client.get("/").text

    # logout revokes it
    client.get("/logout", follow_redirects=False)
    assert client.get("/", follow_redirects=False).status_code == 303


def test_empty_password_never_authenticates(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    client = TestClient(app)
    assert client.post("/login", data={"password": ""}).status_code in (401, 422)


def _make_trade(client, ticker="REF"):
    return client.post("/trades", data={
        "ticker": ticker, "structure": "long_call", "direction": "bullish",
        "pillar": "momentum+", "thesis": "", "entry_date": "2026-07-08",
        "net_debit_credit": "250", "contracts": "1", "notional_exposure": "5000",
        "max_loss": "250", "max_gain": "", "profit_target": "250",
        "stop_rule": "50% of debit", "time_exit_date": "2026-09-18",
        "catalyst_date": ""}, follow_redirects=False)


def test_price_refresh(monkeypatch):
    from app import market_data
    client = TestClient(app)
    assert _make_trade(client, "REF").status_code == 303

    monkeypatch.setattr(market_data, "last_price", lambda t: 123.45)
    assert client.post("/prices/refresh", follow_redirects=False).status_code == 303
    assert "$123.45" in client.get("/").text

    # a failed fetch keeps the cached value
    monkeypatch.setattr(market_data, "last_price", lambda t: None)
    client.post("/prices/refresh", follow_redirects=False)
    assert "$123.45" in client.get("/").text


def test_journal_csv(monkeypatch):
    client = TestClient(app)
    _make_trade(client, "CSVT")
    r = client.get("/journal.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    header, *rows = r.text.strip().splitlines()
    assert "ticker" in header and "realized_pl" in header
    assert any("CSVT" in row for row in rows)
