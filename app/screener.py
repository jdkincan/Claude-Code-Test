"""Composite scoring for watchlist candidates.

Pure functions over a metrics dict so they can run on yfinance data or
manually entered values interchangeably. Missing metrics contribute zero
rather than failing — a partially filled row still ranks.

The strategy trades momentum in BOTH directions, so the momentum score uses
absolute strength; the sign is reported separately as a directional bias.
"""
from __future__ import annotations

from datetime import date, datetime


def momentum_score(ret_1m: float | None, ret_3m: float | None, ret_6m: float | None,
                   pct_from_52w_high: float | None,
                   above_sma50: bool | None, above_sma200: bool | None) -> tuple[float, str]:
    """Return (score 0-100, bias 'positive'/'negative'/'flat').

    Weighted trend strength: recent returns matter most; trend-structure
    confirmations (SMAs, 52w-high proximity) add up to 25 points.
    """
    rets = [(ret_1m, 0.5), (ret_3m, 0.3), (ret_6m, 0.2)]
    known = [(r, w) for r, w in rets if r is not None]
    if not known:
        return 0.0, "flat"
    signed = sum(r * w for r, w in known) / sum(w for _, w in known)
    # 15% weighted return -> 75 points, capped
    strength = min(75.0, abs(signed) / 0.15 * 75.0)

    confirm = 0.0
    trending_up = signed > 0
    if above_sma50 is not None and above_sma50 == trending_up:
        confirm += 10
    if above_sma200 is not None and above_sma200 == trending_up:
        confirm += 5
    if pct_from_52w_high is not None:
        if trending_up and pct_from_52w_high > -0.05:
            confirm += 10  # within 5% of highs confirms up-momentum
        if not trending_up and pct_from_52w_high < -0.20:
            confirm += 10  # deep below highs confirms down-momentum

    bias = "flat"
    if abs(signed) >= 0.03:
        bias = "positive" if signed > 0 else "negative"
    return round(min(100.0, strength + confirm), 1), bias


def vol_score(realized_vol_20d: float | None, vol_percentile: float | None,
              atm_iv: float | None) -> float:
    """0-100. Rewards interesting vol setups at either extreme.

    Percentile near 0 (vol compressed, expansion candidate) or near 100
    (vol elevated, premium-selling candidate) both score high; the middle
    is uninteresting. Absolute vol level adds a smaller kicker.
    """
    score = 0.0
    if vol_percentile is not None:
        score += abs(vol_percentile - 50.0) / 50.0 * 70.0
    level = atm_iv if atm_iv is not None else realized_vol_20d
    if level is not None:
        score += min(30.0, level / 0.60 * 30.0)  # 60% annualized vol -> full 30
    return round(min(100.0, score), 1)


def catalyst_score(catalyst_date: str | None, today: date | None = None) -> float:
    """0-100 based on proximity of a dated catalyst. No date -> 0."""
    if not catalyst_date:
        return 0.0
    today = today or date.today()
    try:
        cat = datetime.strptime(catalyst_date, "%Y-%m-%d").date()
    except ValueError:
        return 0.0
    days = (cat - today).days
    if days < 0:
        return 0.0        # catalyst passed
    if days <= 7:
        return 100.0
    if days <= 30:
        return round(100.0 - (days - 7) / 23.0 * 60.0, 1)   # 100 -> 40
    if days <= 90:
        return round(40.0 - (days - 30) / 60.0 * 40.0, 1)   # 40 -> 0
    return 0.0


def composite_score(metrics: dict, today: date | None = None) -> dict:
    """Blend pillar scores. Weights: momentum 45%, vol 30%, catalyst 25%."""
    mom, bias = momentum_score(
        metrics.get("ret_1m"), metrics.get("ret_3m"), metrics.get("ret_6m"),
        metrics.get("pct_from_52w_high"),
        _to_bool(metrics.get("above_sma50")), _to_bool(metrics.get("above_sma200")),
    )
    vol = vol_score(metrics.get("realized_vol_20d"), metrics.get("vol_percentile"),
                    metrics.get("atm_iv"))
    cat = catalyst_score(metrics.get("catalyst_date"), today)
    total = round(0.45 * mom + 0.30 * vol + 0.25 * cat, 1)
    return {"momentum": mom, "momentum_bias": bias, "vol": vol,
            "catalyst": cat, "total": total}


def _to_bool(v) -> bool | None:
    if v is None:
        return None
    return bool(v)
