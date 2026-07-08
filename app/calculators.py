"""Options structure math: defined-risk P/L, breakevens, sizing, payoff curves.

All money values are total dollars for the whole position (contracts x 100)
unless a name says per_share. Premiums are entered per share, as quoted.

Conventions:
- max_loss / max_gain are positive dollar magnitudes; max_gain=None means uncapped.
- A net debit is money paid (positive); a net credit is represented by the
  structure's own fields, not sign tricks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

MULT = 100  # standard equity option multiplier


@dataclass
class StructureResult:
    structure: str
    contracts: int
    net_debit: float          # dollars paid to open (negative = credit received)
    max_loss: float           # dollars, positive
    max_gain: float | None    # dollars, positive; None = uncapped
    breakevens: list[float]
    notional_exposure: float  # dollars of underlying controlled
    warnings: list[str] = field(default_factory=list)

    @property
    def risk_reward(self) -> float | None:
        if self.max_gain is None or self.max_loss == 0:
            return None
        return self.max_gain / self.max_loss


def _pos(name: str, value: float) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def long_call(spot: float, strike: float, premium: float, contracts: int) -> StructureResult:
    _pos("premium", premium)
    debit = premium * MULT * contracts
    return StructureResult(
        structure="long_call", contracts=contracts, net_debit=debit,
        max_loss=debit, max_gain=None,
        breakevens=[strike + premium],
        notional_exposure=spot * MULT * contracts,
    )


def long_put(spot: float, strike: float, premium: float, contracts: int) -> StructureResult:
    _pos("premium", premium)
    debit = premium * MULT * contracts
    return StructureResult(
        structure="long_put", contracts=contracts, net_debit=debit,
        max_loss=debit,
        max_gain=(strike - premium) * MULT * contracts,
        breakevens=[strike - premium],
        notional_exposure=spot * MULT * contracts,
    )


def debit_vertical(spot: float, long_strike: float, short_strike: float,
                   net_debit_per_share: float, contracts: int,
                   option_type: str = "call") -> StructureResult:
    """Bull call spread or bear put spread (pay a debit, defined max gain)."""
    _pos("net debit", net_debit_per_share)
    width = abs(short_strike - long_strike)
    if net_debit_per_share >= width:
        raise ValueError("net debit must be less than spread width")
    debit = net_debit_per_share * MULT * contracts
    if option_type == "call":
        be = long_strike + net_debit_per_share
    else:
        be = long_strike - net_debit_per_share
    return StructureResult(
        structure=f"debit_vertical_{option_type}", contracts=contracts, net_debit=debit,
        max_loss=debit,
        max_gain=(width - net_debit_per_share) * MULT * contracts,
        breakevens=[be],
        notional_exposure=spot * MULT * contracts,
    )


def credit_vertical(spot: float, short_strike: float, long_strike: float,
                    net_credit_per_share: float, contracts: int,
                    option_type: str = "put") -> StructureResult:
    """Short put spread / short call spread (collect a credit, defined max loss)."""
    _pos("net credit", net_credit_per_share)
    width = abs(long_strike - short_strike)
    if net_credit_per_share >= width:
        raise ValueError("net credit must be less than spread width")
    credit = net_credit_per_share * MULT * contracts
    if option_type == "put":
        be = short_strike - net_credit_per_share
    else:
        be = short_strike + net_credit_per_share
    return StructureResult(
        structure=f"credit_vertical_{option_type}", contracts=contracts, net_debit=-credit,
        max_loss=(width - net_credit_per_share) * MULT * contracts,
        max_gain=credit,
        breakevens=[be],
        notional_exposure=spot * MULT * contracts,
    )


def straddle(spot: float, strike: float, call_premium: float, put_premium: float,
             contracts: int) -> StructureResult:
    _pos("call premium", call_premium)
    _pos("put premium", put_premium)
    total = call_premium + put_premium
    debit = total * MULT * contracts
    return StructureResult(
        structure="straddle", contracts=contracts, net_debit=debit,
        max_loss=debit, max_gain=None,
        breakevens=[strike - total, strike + total],
        notional_exposure=spot * MULT * contracts,
    )


def strangle(spot: float, put_strike: float, call_strike: float,
             call_premium: float, put_premium: float, contracts: int) -> StructureResult:
    _pos("call premium", call_premium)
    _pos("put premium", put_premium)
    if put_strike >= call_strike:
        raise ValueError("put strike must be below call strike")
    total = call_premium + put_premium
    debit = total * MULT * contracts
    return StructureResult(
        structure="strangle", contracts=contracts, net_debit=debit,
        max_loss=debit, max_gain=None,
        breakevens=[put_strike - total, call_strike + total],
        notional_exposure=spot * MULT * contracts,
    )


def cash_secured_put(spot: float, strike: float, premium: float, contracts: int) -> StructureResult:
    _pos("premium", premium)
    credit = premium * MULT * contracts
    return StructureResult(
        structure="cash_secured_put", contracts=contracts, net_debit=-credit,
        max_loss=(strike - premium) * MULT * contracts,
        max_gain=credit,
        breakevens=[strike - premium],
        notional_exposure=strike * MULT * contracts,  # cash to secure assignment
    )


def covered_call(spot: float, strike: float, premium: float, contracts: int) -> StructureResult:
    """Buy 100 shares per contract at spot, sell a call at strike."""
    _pos("premium", premium)
    stock_cost = spot * MULT * contracts
    credit = premium * MULT * contracts
    return StructureResult(
        structure="covered_call", contracts=contracts, net_debit=stock_cost - credit,
        max_loss=(spot - premium) * MULT * contracts,  # stock to zero, keep premium
        max_gain=(strike - spot + premium) * MULT * contracts,
        breakevens=[spot - premium],
        notional_exposure=stock_cost,
    )


# --- Sizing -----------------------------------------------------------------

def suggested_contracts(account_value: float, per_trade_risk_pct: float,
                        max_loss_per_contract: float) -> int:
    """Largest contract count whose worst case stays within the risk budget."""
    _pos("account value", account_value)
    _pos("per-trade risk %", per_trade_risk_pct)
    _pos("max loss per contract", max_loss_per_contract)
    budget = account_value * per_trade_risk_pct / 100.0
    return max(0, math.floor(budget / max_loss_per_contract))


def leverage_check(notional_exposure: float, account_value: float) -> dict:
    """Enforce the mandate's <= 1x notional exposure cap."""
    ratio = notional_exposure / account_value if account_value > 0 else float("inf")
    return {
        "leverage": ratio,
        "ok": ratio <= 1.0,
        "message": ("OK: within 1x leverage cap" if ratio <= 1.0
                    else f"EXCEEDS 1x leverage cap ({ratio:.2f}x notional vs account)"),
    }


# --- Payoff at expiry -------------------------------------------------------

def payoff_at_expiry(structure: str, params: dict, price: float) -> float:
    """Total dollar P/L at expiry for one position at a given underlying price."""
    c = params["contracts"]
    m = MULT * c
    if structure == "long_call":
        return (max(0.0, price - params["strike"]) - params["premium"]) * m
    if structure == "long_put":
        return (max(0.0, params["strike"] - price) - params["premium"]) * m
    if structure.startswith("debit_vertical"):
        lo, hi = sorted([params["long_strike"], params["short_strike"]])
        if structure.endswith("call"):
            intrinsic = min(max(0.0, price - lo), hi - lo)
        else:
            intrinsic = min(max(0.0, hi - price), hi - lo)
        return (intrinsic - params["net_debit_per_share"]) * m
    if structure.startswith("credit_vertical"):
        lo, hi = sorted([params["long_strike"], params["short_strike"]])
        if structure.endswith("put"):
            intrinsic = min(max(0.0, hi - price), hi - lo)   # short spread value against us
        else:
            intrinsic = min(max(0.0, price - lo), hi - lo)
        return (params["net_credit_per_share"] - intrinsic) * m
    if structure == "straddle":
        k = params["strike"]
        total = params["call_premium"] + params["put_premium"]
        return (abs(price - k) - total) * m
    if structure == "strangle":
        total = params["call_premium"] + params["put_premium"]
        intrinsic = max(0.0, price - params["call_strike"]) + max(0.0, params["put_strike"] - price)
        return (intrinsic - total) * m
    if structure == "cash_secured_put":
        return (params["premium"] - max(0.0, params["strike"] - price)) * m
    if structure == "covered_call":
        stock_pl = min(price, params["strike"]) - params["spot"]
        return (stock_pl + params["premium"]) * m
    raise ValueError(f"unknown structure {structure}")


def payoff_curve(structure: str, params: dict, spot: float, n: int = 81) -> list[tuple[float, float]]:
    """(price, P/L) points across +/-40% of spot for charting."""
    lo, hi = spot * 0.6, spot * 1.4
    step = (hi - lo) / (n - 1)
    return [(lo + i * step, payoff_at_expiry(structure, params, lo + i * step)) for i in range(n)]
