# Personal Options Account — Strategy Playbook

## Mandate

- **Vehicle**: personal brokerage account, options-focused.
- **Size**: a deliberately small slice of total investable assets. This is the
  risk sleeve; it must never grow into the core portfolio. Review the sleeve's
  share of investable assets quarterly (Settings page shows it live).
- **Leverage**: total notional exposure of open positions ≤ **1x account value**.
  No margin borrowing. The dashboard flags any breach.
- **Style**: defined-risk positions with **max loss, profit target, stop rule,
  and time exit written down at entry**. If any of those is unknown, the trade
  does not go on.

## The three pillars

Every trade is tagged with exactly one pillar at entry. The tag drives the
performance review — a pillar that doesn't pay gets its allocation cut.

### 1. Momentum (positive or negative)
Trade persistent price trends in either direction.
- **Positive**: strong multi-month uptrend, near 52-week highs, above the 50-
  and 200-day averages. Express with long calls or call debit spreads.
- **Negative**: persistent downtrend, well below the averages. Express with
  long puts or put debit spreads.
- The screener scores momentum by **absolute** trend strength and shows the
  direction as a bias — both signs are tradable.

### 2. Volatility
Trade the level of volatility, not direction.
- **Long vol** (straddles/strangles) when realized vol sits in the bottom
  decile of its 1-year range and something on the calendar can wake it up.
- **Short vol** (credit spreads — always defined-risk, never naked) when vol
  is in the top decile and the move it prices looks overdone.

### 3. Thematic / catalyst (positive or negative)
A dated event or a theme with a clear path to repricing: earnings, product
launches, regulatory decisions, index changes.
- A **catalyst date is mandatory** for these trades (the journal enforces it).
- Position must be on before the catalyst and the default exit is shortly
  after it — a catalyst trade without its catalyst is a different trade.

## Risk limits (hard rules)

| Rule | Limit |
|---|---|
| Max loss per trade | risk % of account set in Settings (default 2%) |
| Notional exposure | ≤ 1x account value across all open positions |
| Max open positions | set in Settings (default 8) |
| Concentration | no more than 2 open positions on one theme/underlying |
| Structure | defined-risk only; no naked short options |

## Defined at entry — the non-negotiables

Logged in the journal before or immediately at fill:

1. **Max loss ($)** — the worst case, sized within the per-trade risk budget.
2. **Profit target ($)** — where gains get taken or the position gets reduced.
3. **Stop rule** — the specific condition that forces an early exit
   (e.g. "close if the position is worth less than half the debit paid",
   "close on a daily close back below the 50-day").
4. **Time exit date** — the calendar date the position comes off regardless,
   chosen well before expiry to avoid gamma/decay endgames.
5. **Catalyst date** — required for catalyst trades.

## Exit discipline

- An exit that follows rules 1–5 is a **plan exit** — mark "followed plan: yes"
  when closing, whatever the P/L. Discretionary overrides are allowed but must
  be marked honestly; the performance page tracks the adherence rate.
- Time exits are not optional. Theta is a real position cost; hope is not.
- After a catalyst passes, the catalyst trade is closed — win, lose, or flat.

## Entry checklist

Before logging a trade, all boxes ticked:

- [ ] Which pillar is this, and does the evidence actually fit it?
- [ ] What invalidates the thesis? (goes in the thesis field)
- [ ] Max loss within the per-trade risk budget (calculator suggests size)
- [ ] Notional exposure keeps the account ≤ 1x (calculator checks)
- [ ] Profit target, stop rule, time exit written down
- [ ] Catalyst date entered if applicable
- [ ] Position count and theme concentration within limits

## Review cadence

- **Weekly**: dashboard sweep — anything at/past its time exit or catalyst
  date gets closed or re-underwritten as a new trade.
- **Monthly**: performance page — win rate, expectancy, adherence, P/L by
  pillar. Adherence below ~90% is a process problem, not a market problem.
- **Quarterly**: sleeve size vs. investable assets; playbook edits happen here,
  not mid-trade.
