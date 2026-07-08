"""yfinance wrappers. Every function returns None (or {} for fetch_metrics)
on any failure so callers fall back to manually entered values.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def last_price(ticker: str) -> float | None:
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="5d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:  # network down, bad ticker, API change — all fall back
        log.warning("last_price(%s) failed: %s", ticker, e)
        return None


def fetch_metrics(ticker: str) -> dict:
    """Momentum + vol metrics from 1y of daily closes, plus ATM IV if available.

    Returns {} on total failure; partial dicts are fine (screener treats
    missing keys as unknown).
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        if hist.empty or len(hist) < 30:
            return {}
        close = hist["Close"]
        price = float(close.iloc[-1])

        def ret(days: int) -> float | None:
            if len(close) <= days:
                return None
            return float(price / close.iloc[-1 - days] - 1.0)

        # 20d realized vol, annualized, plus its percentile over the year
        rets = close.pct_change().dropna()
        vol_series = rets.rolling(20).std().dropna() * (252 ** 0.5)
        current_vol = float(vol_series.iloc[-1]) if len(vol_series) else None
        percentile = None
        if current_vol is not None and len(vol_series) > 20:
            percentile = float((vol_series <= current_vol).mean() * 100.0)

        sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        high_52w = float(close.max())

        metrics = {
            "last_price": price,
            "ret_1m": ret(21),
            "ret_3m": ret(63),
            "ret_6m": ret(126),
            "pct_from_52w_high": price / high_52w - 1.0,
            "above_sma50": (price > sma50) if sma50 is not None else None,
            "above_sma200": (price > sma200) if sma200 is not None else None,
            "realized_vol_20d": current_vol,
            "vol_percentile": percentile,
            "atm_iv": _atm_iv(t, price),
            "metrics_source": "yfinance",
            "metrics_updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return metrics
    except Exception as e:
        log.warning("fetch_metrics(%s) failed: %s", ticker, e)
        return {}


def _atm_iv(t, price: float) -> float | None:
    """Implied vol of the call nearest the money on the nearest expiry."""
    try:
        expiries = t.options
        if not expiries:
            return None
        chain = t.option_chain(expiries[0]).calls
        if chain.empty:
            return None
        atm = chain.iloc[(chain["strike"] - price).abs().argsort().iloc[0]]
        iv = float(atm["impliedVolatility"])
        return iv if iv > 0 else None
    except Exception:
        return None
