# Trade Verification Prompt

Copy everything below the line into any capable AI (Claude, ChatGPT, Gemini, …)
together with **two attachments**:

1. A screenshot of the **broker trade confirmation** (or the confirm text pasted in)
2. A screenshot of the **Options Toolkit trade page** for the same trade
   (`/trades/{id}`), or the trade's row from the `/journal.csv` export pasted in

The AI will produce a field-by-field reconciliation and a verdict.

---

## Prompt

You are reconciling a records mismatch check between (A) a brokerage trade
confirmation and (B) a personal trade-journal entry from a web app called
Options Toolkit. Your job: determine whether A and B describe the **same
trade with the same economics**, and flag every discrepancy precisely.

### How the Options Toolkit records trades (source B's conventions)

- **Net debit/credit** is the **TOTAL dollar amount for the whole position**,
  not per share and not per contract. A **credit received is shown as a
  negative number** (e.g. `-300` = $300 credit collected). Broker confirms
  usually quote **per-share** prices — normalize with:
  `total = per_share_price × 100 × number_of_contracts` (standard equity
  options multiplier of 100).
- The app's dollar figures **exclude commissions and fees**. A small
  difference exactly equal to the confirm's fee line is NOT a mismatch —
  note it as "fees, expected".
- **Structure names**: `long_call`, `long_put`, `debit_vertical` (bull call
  or bear put spread), `credit_vertical` (short put or short call spread),
  `straddle`, `strangle`, `cash_secured_put`, `covered_call`. A multi-leg
  broker confirm may list legs separately — net them before comparing.
- **Contracts** = number of spreads/units, not the total leg count (a
  2-lot vertical shows `contracts: 2` even though 4 option legs traded).
- **Dates** are ISO `YYYY-MM-DD`. `entry_date` should match the confirm's
  trade date (not settlement date).
- Journal-only planning fields (`max_loss`, `max_gain`, `profit_target`,
  `stop_rule`, `time_exit_date`, `catalyst_date`, `pillar`, `thesis`,
  `notional_exposure`) will NOT appear on a broker confirm — do not flag
  them as missing from A. But DO sanity-check `max_loss`: for a debit
  structure it should equal the total debit; for a credit vertical it
  should equal `(strike_width − credit_per_share) × 100 × contracts`.

### What to do

1. **Extract from A (broker confirm)**: ticker/underlying, action(s)
   (buy/sell to open/close), option type(s), strike(s), expiration(s),
   quantity per leg, price per leg (state per-share vs total), net
   debit/credit, trade date, fees/commissions if shown.
2. **Extract from B (app page or CSV row)**: ticker, structure, direction,
   contracts, net debit/credit (total $), entry date, and the plan fields.
3. **Normalize** A to the app's conventions (totals, signed credit, netted
   multi-leg price, structure name inferred from the legs).
4. Output a **comparison table**: one row per field —
   `Field | Broker confirm (normalized) | Journal entry | MATCH / MISMATCH / N/A`.
5. Check the derived values: does the confirm's leg structure imply the
   journal's `structure` name? Is `max_loss` consistent with the structure's
   math? Is `notional_exposure ≈ spot × 100 × contracts` (or
   `strike × 100 × contracts` for a cash-secured put)?
6. Finish with a one-line **verdict**: ✅ SAME TRADE, ⚠️ SAME TRADE WITH
   NOTES (list them), or ❌ DISCREPANCY (list what's wrong and what the
   journal entry should say).

### Gotchas to check deliberately

- Per-share vs total-dollar confusion (factor-of-100 or factor-of-contracts
  errors are the most common).
- Sign errors: a credit recorded as a positive debit.
- Partial fills: the confirm may show fewer contracts than the order; compare
  against filled quantity.
- Multiple confirms for one multi-leg order: ask for the missing legs rather
  than declaring a mismatch.
- Weekly vs monthly expiration of the same week, and near-miss strikes
  (e.g. 105 vs 105.5) — read carefully rather than pattern-matching.
- If either image is unreadable or a required field is not visible, say
  exactly which field you could not verify instead of guessing.
