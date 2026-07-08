import math

import pytest

from app import calculators as calc


def test_long_call():
    r = calc.long_call(spot=100, strike=105, premium=2.50, contracts=2)
    assert r.net_debit == 500
    assert r.max_loss == 500
    assert r.max_gain is None
    assert r.breakevens == [107.50]
    assert r.notional_exposure == 20000


def test_long_put():
    r = calc.long_put(spot=100, strike=95, premium=3.00, contracts=1)
    assert r.max_loss == 300
    assert r.max_gain == 9200  # strike to zero minus premium
    assert r.breakevens == [92.0]


def test_debit_call_vertical():
    r = calc.debit_vertical(spot=100, long_strike=100, short_strike=110,
                            net_debit_per_share=4.0, contracts=1, option_type="call")
    assert r.max_loss == 400
    assert r.max_gain == 600
    assert r.breakevens == [104.0]
    assert r.risk_reward == pytest.approx(1.5)


def test_debit_put_vertical_breakeven():
    r = calc.debit_vertical(spot=100, long_strike=100, short_strike=90,
                            net_debit_per_share=4.0, contracts=1, option_type="put")
    assert r.breakevens == [96.0]


def test_credit_put_vertical():
    r = calc.credit_vertical(spot=100, short_strike=95, long_strike=90,
                             net_credit_per_share=1.50, contracts=2, option_type="put")
    assert r.net_debit == -300           # credit received
    assert r.max_gain == 300
    assert r.max_loss == 700             # (5 - 1.5) * 100 * 2
    assert r.breakevens == [93.50]


def test_credit_call_vertical_breakeven():
    r = calc.credit_vertical(spot=100, short_strike=105, long_strike=110,
                             net_credit_per_share=1.0, contracts=1, option_type="call")
    assert r.breakevens == [106.0]


def test_straddle():
    r = calc.straddle(spot=100, strike=100, call_premium=4, put_premium=3, contracts=1)
    assert r.max_loss == 700
    assert r.breakevens == [93, 107]


def test_strangle():
    r = calc.strangle(spot=100, put_strike=95, call_strike=105,
                      call_premium=2, put_premium=1.5, contracts=1)
    assert r.max_loss == 350
    assert r.breakevens == [91.5, 108.5]
    with pytest.raises(ValueError):
        calc.strangle(100, 105, 95, 2, 1.5, 1)  # inverted strikes


def test_cash_secured_put():
    r = calc.cash_secured_put(spot=100, strike=95, premium=2, contracts=1)
    assert r.max_gain == 200
    assert r.max_loss == 9300
    assert r.notional_exposure == 9500   # cash securing assignment


def test_covered_call():
    r = calc.covered_call(spot=100, strike=110, premium=3, contracts=1)
    assert r.max_gain == 1300            # 10 appreciation + 3 premium
    assert r.max_loss == 9700
    assert r.breakevens == [97.0]


def test_spread_wider_than_width_rejected():
    with pytest.raises(ValueError):
        calc.debit_vertical(100, 100, 105, 6.0, 1)
    with pytest.raises(ValueError):
        calc.credit_vertical(100, 95, 90, 5.5, 1)


def test_suggested_contracts():
    # $10k account, 2% risk = $200 budget; $80 max loss per contract -> 2
    assert calc.suggested_contracts(10000, 2.0, 80) == 2
    assert calc.suggested_contracts(10000, 2.0, 250) == 0


def test_leverage_check():
    assert calc.leverage_check(9000, 10000)["ok"]
    over = calc.leverage_check(15000, 10000)
    assert not over["ok"]
    assert "1.50x" in over["message"]


# --- payoff sanity: value at key prices matches the closed-form results -----

def test_payoff_long_call_matches_result():
    params = {"contracts": 1, "spot": 100, "strike": 105, "premium": 2.5}
    assert calc.payoff_at_expiry("long_call", params, 100) == -250       # max loss
    assert calc.payoff_at_expiry("long_call", params, 107.5) == pytest.approx(0)
    assert calc.payoff_at_expiry("long_call", params, 115) == 750


def test_payoff_credit_put_vertical():
    params = {"contracts": 1, "spot": 100, "long_strike": 90, "short_strike": 95,
              "net_credit_per_share": 1.5}
    assert calc.payoff_at_expiry("credit_vertical_put", params, 100) == 150   # keep credit
    assert calc.payoff_at_expiry("credit_vertical_put", params, 85) == -350   # max loss
    assert calc.payoff_at_expiry("credit_vertical_put", params, 93.5) == pytest.approx(0)


def test_payoff_straddle():
    params = {"contracts": 1, "spot": 100, "strike": 100,
              "call_premium": 4, "put_premium": 3}
    assert calc.payoff_at_expiry("straddle", params, 100) == -700
    assert calc.payoff_at_expiry("straddle", params, 110) == 300


def test_payoff_covered_call_caps_at_strike():
    params = {"contracts": 1, "spot": 100, "strike": 110, "premium": 3}
    assert calc.payoff_at_expiry("covered_call", params, 130) == 1300
    assert calc.payoff_at_expiry("covered_call", params, 90) == -700


def test_payoff_curve_shape():
    params = {"contracts": 1, "spot": 100, "strike": 100, "premium": 5}
    curve = calc.payoff_curve("long_call", params, 100, n=41)
    assert len(curve) == 41
    assert curve[0][0] == pytest.approx(60)
    assert curve[-1][0] == pytest.approx(140)
    # monotone non-decreasing for a long call
    values = [v for _, v in curve]
    assert all(b >= a - 1e-9 for a, b in zip(values, values[1:]))
