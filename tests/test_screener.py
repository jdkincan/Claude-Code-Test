from datetime import date

from app import screener


def test_momentum_score_strong_uptrend():
    score, bias = screener.momentum_score(
        ret_1m=0.10, ret_3m=0.20, ret_6m=0.35,
        pct_from_52w_high=-0.01, above_sma50=True, above_sma200=True)
    assert bias == "positive"
    assert score == 100.0  # capped: strong returns + all confirmations


def test_momentum_score_downtrend_uses_absolute_strength():
    up, _ = screener.momentum_score(0.10, 0.15, 0.20, None, None, None)
    down, bias = screener.momentum_score(-0.10, -0.15, -0.20, None, None, None)
    assert down == up  # both directions trade
    assert bias == "negative"


def test_momentum_score_confirmations_match_direction():
    # SMAs below price on a downtrend contradict; no confirmation points
    contradicted, _ = screener.momentum_score(-0.10, -0.10, -0.10, None, True, True)
    confirmed, _ = screener.momentum_score(-0.10, -0.10, -0.10, -0.30, False, False)
    assert confirmed > contradicted


def test_momentum_score_missing_data():
    score, bias = screener.momentum_score(None, None, None, None, None, None)
    assert (score, bias) == (0.0, "flat")


def test_vol_score_extremes_beat_middle():
    low = screener.vol_score(0.20, 5.0, None)
    mid = screener.vol_score(0.20, 50.0, None)
    high = screener.vol_score(0.20, 95.0, None)
    assert low > mid and high > mid


def test_vol_score_prefers_iv_over_realized():
    with_iv = screener.vol_score(0.20, 50.0, 0.60)
    without = screener.vol_score(0.20, 50.0, None)
    assert with_iv > without


def test_catalyst_score_proximity():
    today = date(2026, 7, 8)
    assert screener.catalyst_score("2026-07-10", today) == 100.0     # this week
    near = screener.catalyst_score("2026-07-25", today)
    far = screener.catalyst_score("2026-09-20", today)
    assert 40.0 <= near <= 100.0
    assert 0.0 <= far < near
    assert screener.catalyst_score("2026-07-01", today) == 0.0       # passed
    assert screener.catalyst_score(None, today) == 0.0
    assert screener.catalyst_score("not-a-date", today) == 0.0


def test_composite_weights():
    metrics = {"ret_1m": 0.10, "ret_3m": 0.20, "ret_6m": 0.35,
               "pct_from_52w_high": -0.01, "above_sma50": 1, "above_sma200": 1,
               "realized_vol_20d": 0.60, "vol_percentile": 95.0, "atm_iv": 0.60,
               "catalyst_date": "2026-07-10"}
    s = screener.composite_score(metrics, today=date(2026, 7, 8))
    assert s["momentum"] == 100.0
    assert s["catalyst"] == 100.0
    expected = round(0.45 * s["momentum"] + 0.30 * s["vol"] + 0.25 * s["catalyst"], 1)
    assert s["total"] == expected


def test_composite_empty_metrics():
    s = screener.composite_score({}, today=date(2026, 7, 8))
    assert s["total"] == 0.0
    assert s["momentum_bias"] == "flat"
