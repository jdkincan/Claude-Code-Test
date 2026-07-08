"""Personal brokerage options toolkit — single-user web app.

Optional password protection: set APP_PASSWORD to require login on every
route (used for hosted deployments; local runs without it need no login).
Set SECRET_KEY too in production so sessions survive restarts.
"""
from __future__ import annotations

import csv
import hmac
import io
import json
import os
import secrets
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import markdown as md
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import calculators as calc
from app import market_data, screener
from app.db import get_db

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Options Toolkit")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["auth_enabled"] = lambda: bool(os.environ.get("APP_PASSWORD"))
templates.env.filters["money"] = lambda v: f"${v:,.0f}" if v is not None else "—"
templates.env.filters["money2"] = lambda v: f"${v:,.2f}" if v is not None else "—"
templates.env.filters["pct"] = lambda v: f"{v * 100:+.1f}%" if v is not None else "—"

PILLARS = ["momentum+", "momentum-", "vol", "catalyst+", "catalyst-"]
STRUCTURES = ["long_call", "long_put", "debit_vertical", "credit_vertical",
              "straddle", "strangle", "cash_secured_put", "covered_call"]
EXIT_REASONS = ["target", "stop", "time", "catalyst", "discretionary"]


def db() -> sqlite3.Connection:
    return get_db()


def get_settings(conn) -> sqlite3.Row:
    return conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()


def render(request: Request, template: str, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, template, ctx)


# --- Auth (active only when APP_PASSWORD is set) ------------------------------

@app.middleware("http")
async def require_auth(request: Request, call_next):
    password = os.environ.get("APP_PASSWORD")
    path = request.url.path
    if password and path != "/login" and not path.startswith("/static"):
        if not request.session.get("authed"):
            return RedirectResponse("/login", status_code=303)
    return await call_next(request)


# Added after the auth middleware so it wraps it (outermost), making
# request.session available inside require_auth.
app.add_middleware(SessionMiddleware,
                   secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
                   max_age=30 * 24 * 3600, same_site="lax")


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return render(request, "login.html", error=None)


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, password: str = Form(...)):
    expected = os.environ.get("APP_PASSWORD", "")
    if expected and hmac.compare_digest(password, expected):
        request.session["authed"] = True
        return RedirectResponse("/", status_code=303)
    resp = render(request, "login.html", error="Wrong password.")
    resp.status_code = 401
    return resp


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# --- Dashboard ---------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    conn = db()
    try:
        settings = get_settings(conn)
        open_trades = conn.execute(
            "SELECT * FROM trades WHERE status = 'open' ORDER BY time_exit_date").fetchall()
        capital_at_risk = sum(t["max_loss"] for t in open_trades)
        notional = sum(t["notional_exposure"] for t in open_trades)
        lev = calc.leverage_check(notional, settings["account_value"])
        today = date.today().isoformat()
        upcoming = [t for t in open_trades
                    if t["time_exit_date"] <= today
                    or (t["catalyst_date"] and t["catalyst_date"] <= today)]
        prices = {r["ticker"]: r for r in conn.execute("SELECT * FROM price_cache")}
        return render(request, "dashboard.html", settings=settings,
                      open_trades=open_trades, capital_at_risk=capital_at_risk,
                      notional=notional, leverage=lev, upcoming=upcoming, today=today,
                      prices=prices)
    finally:
        conn.close()


@app.post("/prices/refresh")
def refresh_prices():
    """Pull the latest underlying price for every open-trade ticker.

    Fetch failures keep the previous cached value, so the page keeps working
    offline with a stale-but-labeled price.
    """
    conn = db()
    try:
        tickers = [r["ticker"] for r in conn.execute(
            "SELECT DISTINCT ticker FROM trades WHERE status = 'open'")]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for ticker in tickers:
            price = market_data.last_price(ticker)
            if price is not None:
                conn.execute("""
                    INSERT INTO price_cache (ticker, price, updated_at) VALUES (?,?,?)
                    ON CONFLICT(ticker) DO UPDATE SET price=excluded.price,
                        updated_at=excluded.updated_at""", (ticker, price, now))
        conn.commit()
        return RedirectResponse("/", status_code=303)
    finally:
        conn.close()


# --- Journal -----------------------------------------------------------------

@app.get("/journal", response_class=HTMLResponse)
def journal(request: Request):
    conn = db()
    try:
        trades = conn.execute("""
            SELECT t.*, e.realized_pl, e.exit_date, e.exit_reason
            FROM trades t LEFT JOIN trade_exits e ON e.trade_id = t.id
            ORDER BY t.entry_date DESC, t.id DESC""").fetchall()
        return render(request, "journal.html", trades=trades)
    finally:
        conn.close()


@app.get("/journal.csv")
def journal_csv():
    conn = db()
    try:
        rows = conn.execute("""
            SELECT t.id, t.ticker, t.structure, t.direction, t.pillar, t.entry_date,
                   t.contracts, t.net_debit_credit, t.notional_exposure, t.max_loss,
                   t.max_gain, t.profit_target, t.stop_rule, t.time_exit_date,
                   t.catalyst_date, t.status, e.exit_date, e.proceeds, e.realized_pl,
                   e.exit_reason, e.followed_plan, t.thesis
            FROM trades t LEFT JOIN trade_exits e ON e.trade_id = t.id
            ORDER BY t.entry_date, t.id""").fetchall()
        buf = io.StringIO()
        writer = csv.writer(buf)
        if rows:
            writer.writerow(rows[0].keys())
            writer.writerows([tuple(r) for r in rows])
        else:
            writer.writerow(["no trades"])
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=journal.csv"})
    finally:
        conn.close()


@app.get("/trades/new", response_class=HTMLResponse)
def new_trade_form(request: Request):
    conn = db()
    try:
        settings = get_settings(conn)
        prefill = dict(request.query_params)  # from calculator "send to journal"
        return render(request, "trade_form.html", settings=settings, prefill=prefill,
                      pillars=PILLARS, structures=STRUCTURES,
                      today=date.today().isoformat())
    finally:
        conn.close()


@app.post("/trades")
def create_trade(
    ticker: str = Form(...), structure: str = Form(...), direction: str = Form(...),
    pillar: str = Form(...), thesis: str = Form(""), entry_date: str = Form(...),
    net_debit_credit: float = Form(...), contracts: int = Form(...),
    notional_exposure: float = Form(0),
    max_loss: float = Form(...), max_gain: str = Form(""),
    profit_target: float = Form(...), stop_rule: str = Form(...),
    time_exit_date: str = Form(...), catalyst_date: str = Form(""),
):
    if pillar not in PILLARS:
        raise HTTPException(400, "invalid pillar")
    if max_loss <= 0:
        raise HTTPException(400, "max loss must be a positive dollar amount")
    if not stop_rule.strip():
        raise HTTPException(400, "stop rule is required — exits are defined at entry")
    if pillar.startswith("catalyst") and not catalyst_date:
        raise HTTPException(400, "catalyst trades require a catalyst date")
    conn = db()
    try:
        cur = conn.execute("""
            INSERT INTO trades (ticker, structure, direction, pillar, thesis, entry_date,
                net_debit_credit, contracts, notional_exposure, max_loss, max_gain,
                profit_target, stop_rule, time_exit_date, catalyst_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ticker.upper().strip(), structure, direction, pillar, thesis, entry_date,
             net_debit_credit, contracts, notional_exposure, max_loss,
             float(max_gain) if max_gain.strip() else None,
             profit_target, stop_rule, time_exit_date, catalyst_date or None))
        conn.commit()
        return RedirectResponse(f"/trades/{cur.lastrowid}", status_code=303)
    finally:
        conn.close()


@app.get("/trades/{trade_id}", response_class=HTMLResponse)
def trade_detail(request: Request, trade_id: int):
    conn = db()
    try:
        trade = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not trade:
            raise HTTPException(404)
        exit_row = conn.execute(
            "SELECT * FROM trade_exits WHERE trade_id = ?", (trade_id,)).fetchone()
        return render(request, "trade_detail.html", trade=trade, exit=exit_row,
                      exit_reasons=EXIT_REASONS, today=date.today().isoformat())
    finally:
        conn.close()


@app.post("/trades/{trade_id}/close")
def close_trade(trade_id: int, exit_date: str = Form(...), proceeds: float = Form(...),
                exit_reason: str = Form(...), followed_plan: str = Form("0"),
                notes: str = Form("")):
    if exit_reason not in EXIT_REASONS:
        raise HTTPException(400, "invalid exit reason")
    conn = db()
    try:
        trade = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not trade:
            raise HTTPException(404)
        if trade["status"] != "open":
            raise HTTPException(400, "trade already closed")
        realized = proceeds - trade["net_debit_credit"]
        conn.execute("""
            INSERT INTO trade_exits (trade_id, exit_date, proceeds, realized_pl,
                exit_reason, followed_plan, notes) VALUES (?,?,?,?,?,?,?)""",
            (trade_id, exit_date, proceeds, realized, exit_reason,
             1 if followed_plan == "1" else 0, notes))
        conn.execute("UPDATE trades SET status = 'closed' WHERE id = ?", (trade_id,))
        conn.commit()
        return RedirectResponse(f"/trades/{trade_id}", status_code=303)
    finally:
        conn.close()


# --- Performance -------------------------------------------------------------

@app.get("/performance", response_class=HTMLResponse)
def performance(request: Request):
    conn = db()
    try:
        rows = conn.execute("""
            SELECT t.pillar, e.realized_pl, e.followed_plan, e.exit_reason
            FROM trade_exits e JOIN trades t ON t.id = e.trade_id""").fetchall()
        n = len(rows)
        wins = [r for r in rows if r["realized_pl"] > 0]
        losses = [r for r in rows if r["realized_pl"] <= 0]
        stats = {
            "n": n,
            "total_pl": sum(r["realized_pl"] for r in rows),
            "win_rate": len(wins) / n if n else None,
            "avg_win": sum(r["realized_pl"] for r in wins) / len(wins) if wins else None,
            "avg_loss": sum(r["realized_pl"] for r in losses) / len(losses) if losses else None,
            "adherence": sum(r["followed_plan"] for r in rows) / n if n else None,
        }
        if stats["win_rate"] is not None and stats["avg_win"] is not None and stats["avg_loss"] is not None:
            stats["expectancy"] = (stats["win_rate"] * stats["avg_win"]
                                   + (1 - stats["win_rate"]) * stats["avg_loss"])
        else:
            stats["expectancy"] = None
        by_pillar = {}
        for r in rows:
            p = by_pillar.setdefault(r["pillar"], {"n": 0, "pl": 0.0})
            p["n"] += 1
            p["pl"] += r["realized_pl"]
        return render(request, "performance.html", stats=stats, by_pillar=by_pillar)
    finally:
        conn.close()


# --- Calculator --------------------------------------------------------------

def _build_structure(structure: str, f: dict) -> calc.StructureResult:
    spot = float(f["spot"])
    contracts = int(f.get("contracts") or 1)
    if structure == "long_call":
        return calc.long_call(spot, float(f["strike"]), float(f["premium"]), contracts)
    if structure == "long_put":
        return calc.long_put(spot, float(f["strike"]), float(f["premium"]), contracts)
    if structure == "debit_vertical":
        return calc.debit_vertical(spot, float(f["long_strike"]), float(f["short_strike"]),
                                   float(f["net_per_share"]), contracts, f.get("option_type", "call"))
    if structure == "credit_vertical":
        return calc.credit_vertical(spot, float(f["short_strike"]), float(f["long_strike"]),
                                    float(f["net_per_share"]), contracts, f.get("option_type", "put"))
    if structure == "straddle":
        return calc.straddle(spot, float(f["strike"]), float(f["call_premium"]),
                             float(f["put_premium"]), contracts)
    if structure == "strangle":
        return calc.strangle(spot, float(f["put_strike"]), float(f["call_strike"]),
                             float(f["call_premium"]), float(f["put_premium"]), contracts)
    if structure == "cash_secured_put":
        return calc.cash_secured_put(spot, float(f["strike"]), float(f["premium"]), contracts)
    if structure == "covered_call":
        return calc.covered_call(spot, float(f["strike"]), float(f["premium"]), contracts)
    raise ValueError(f"unknown structure {structure}")


def _payoff_params(structure: str, f: dict, contracts: int) -> dict:
    p = {"contracts": contracts, "spot": float(f["spot"])}
    for key in ("strike", "premium", "long_strike", "short_strike", "net_per_share",
                "call_premium", "put_premium", "call_strike", "put_strike"):
        if f.get(key) not in (None, ""):
            p[key] = float(f[key])
    if "net_per_share" in p:
        p["net_debit_per_share"] = p["net_credit_per_share"] = p["net_per_share"]
    return p


@app.get("/calculator", response_class=HTMLResponse)
def calculator_form(request: Request):
    conn = db()
    try:
        return render(request, "calculator.html", settings=get_settings(conn),
                      structures=STRUCTURES, result=None, form={}, curve_json=None)
    finally:
        conn.close()


@app.post("/calculator", response_class=HTMLResponse)
async def calculator_run(request: Request):
    form = dict(await request.form())
    conn = db()
    try:
        settings = get_settings(conn)
        structure = form.get("structure", "")
        error = None
        result = suggestion = lev = curve_json = None
        try:
            result = _build_structure(structure, form)
            per_contract_loss = result.max_loss / result.contracts
            suggestion = calc.suggested_contracts(
                settings["account_value"], settings["per_trade_risk_pct"], per_contract_loss)
            lev = calc.leverage_check(result.notional_exposure, settings["account_value"])
            params = _payoff_params(result.structure, form, result.contracts)
            curve = calc.payoff_curve(result.structure, params, float(form["spot"]))
            curve_json = json.dumps({
                "points": [[round(p, 2), round(v, 2)] for p, v in curve],
                "breakevens": result.breakevens, "spot": float(form["spot"]),
            })
        except (ValueError, KeyError) as e:
            error = f"Invalid input: {e}"
        return render(request, "calculator.html", settings=settings,
                      structures=STRUCTURES, result=result, form=form, error=error,
                      suggestion=suggestion, leverage=lev, curve_json=curve_json)
    finally:
        conn.close()


# --- Screener ----------------------------------------------------------------

METRIC_FIELDS = ["last_price", "ret_1m", "ret_3m", "ret_6m", "pct_from_52w_high",
                 "above_sma50", "above_sma200", "realized_vol_20d", "vol_percentile",
                 "atm_iv"]


@app.get("/screener", response_class=HTMLResponse)
def screener_page(request: Request):
    conn = db()
    try:
        rows = conn.execute("SELECT * FROM watchlist ORDER BY ticker").fetchall()
        scored = []
        for r in rows:
            m = dict(r)
            scores = screener.composite_score(m)
            scored.append({"row": r, "scores": scores})
        scored.sort(key=lambda s: s["scores"]["total"], reverse=True)
        return render(request, "screener.html", items=scored)
    finally:
        conn.close()


@app.post("/screener/add")
def screener_add(ticker: str = Form(...), theme: str = Form(""),
                 catalyst_note: str = Form(""), catalyst_date: str = Form(""),
                 bias: str = Form("none")):
    conn = db()
    try:
        conn.execute("""
            INSERT INTO watchlist (ticker, theme, catalyst_note, catalyst_date, bias)
            VALUES (?,?,?,?,?)
            ON CONFLICT(ticker) DO UPDATE SET theme=excluded.theme,
                catalyst_note=excluded.catalyst_note,
                catalyst_date=excluded.catalyst_date, bias=excluded.bias""",
            (ticker.upper().strip(), theme, catalyst_note, catalyst_date or None, bias))
        conn.commit()
        return RedirectResponse("/screener", status_code=303)
    finally:
        conn.close()


@app.post("/screener/{item_id}/scan")
def screener_scan(item_id: int):
    conn = db()
    try:
        row = conn.execute("SELECT * FROM watchlist WHERE id = ?", (item_id,)).fetchone()
        if not row:
            raise HTTPException(404)
        metrics = market_data.fetch_metrics(row["ticker"])
        if metrics:
            cols = [k for k in metrics if k in METRIC_FIELDS or
                    k in ("metrics_source", "metrics_updated_at")]
            sets = ", ".join(f"{c} = ?" for c in cols)
            conn.execute(f"UPDATE watchlist SET {sets} WHERE id = ?",
                         [metrics[c] for c in cols] + [item_id])
            conn.commit()
        return RedirectResponse("/screener", status_code=303)
    finally:
        conn.close()


@app.post("/screener/scan-all")
def screener_scan_all():
    conn = db()
    try:
        for row in conn.execute("SELECT id FROM watchlist").fetchall():
            screener_scan(row["id"])
        return RedirectResponse("/screener", status_code=303)
    finally:
        conn.close()


@app.post("/screener/{item_id}/update")
async def screener_manual_update(item_id: int, request: Request):
    """Manual entry/override of any metric field; blanks leave values unchanged."""
    form = dict(await request.form())
    conn = db()
    try:
        if not conn.execute("SELECT 1 FROM watchlist WHERE id = ?", (item_id,)).fetchone():
            raise HTTPException(404)
        updates, values = [], []
        for field in METRIC_FIELDS:
            raw = form.get(field, "").strip()
            if raw == "":
                continue
            if field in ("above_sma50", "above_sma200"):
                values.append(1 if raw.lower() in ("1", "true", "yes", "y") else 0)
            else:
                try:
                    values.append(float(raw))
                except ValueError:
                    raise HTTPException(400, f"{field} must be a number")
            updates.append(f"{field} = ?")
        if updates:
            updates.append("metrics_source = 'manual'")
            updates.append("metrics_updated_at = datetime('now')")
            conn.execute(f"UPDATE watchlist SET {', '.join(updates)} WHERE id = ?",
                         values + [item_id])
            conn.commit()
        return RedirectResponse("/screener", status_code=303)
    finally:
        conn.close()


@app.post("/screener/{item_id}/delete")
def screener_delete(item_id: int):
    conn = db()
    try:
        conn.execute("DELETE FROM watchlist WHERE id = ?", (item_id,))
        conn.commit()
        return RedirectResponse("/screener", status_code=303)
    finally:
        conn.close()


# --- Playbook, settings, misc --------------------------------------------------

@app.get("/playbook", response_class=HTMLResponse)
def playbook(request: Request):
    path = BASE_DIR.parent / "docs" / "playbook.md"
    html = md.markdown(path.read_text(), extensions=["tables"])
    return render(request, "playbook.html", content=html)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    conn = db()
    try:
        return render(request, "settings.html", settings=get_settings(conn), saved=False)
    finally:
        conn.close()


@app.post("/settings", response_class=HTMLResponse)
def settings_save(request: Request, account_value: float = Form(...),
                  total_investable_assets: float = Form(...),
                  per_trade_risk_pct: float = Form(...),
                  max_open_positions: int = Form(...)):
    conn = db()
    try:
        conn.execute("""
            UPDATE settings SET account_value = ?, total_investable_assets = ?,
                per_trade_risk_pct = ?, max_open_positions = ? WHERE id = 1""",
            (account_value, total_investable_assets, per_trade_risk_pct, max_open_positions))
        conn.commit()
        return render(request, "settings.html", settings=get_settings(conn), saved=True)
    finally:
        conn.close()


@app.get("/api/price/{ticker}")
def api_price(ticker: str):
    price = market_data.last_price(ticker)
    return JSONResponse({"ticker": ticker.upper(), "price": price})
