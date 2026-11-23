# Book 2, attempt #2: the volatility risk premium

*Written 2026-11-23, before any data for this strategy was downloaded or any backtest
was run. Attempt #1 (intraday mean reversion, `docs/book2_design.md`) failed its
pre-set bar; this is a new, separate hypothesis, not a tweak of attempt #1.*

## The idea

Options are, on average, overpriced. The volatility the market *expects* (implied
volatility, roughly the VIX) is usually higher than the volatility that actually
*happens* (realized volatility). Investors pay up for crash insurance, the way an
insurer charges more than expected claims. Carr & Wu (*Review of Financial
Studies*, 2009) find this "variance risk premium" strongly negative for index
options, and not explained by the usual risk factors.

We collect it the textbook way: sell SPY options and **delta hedge** them, so we
make no bet on the market's direction, only on implied vs. realized volatility.

**Why it might keep working:** it is a *risk premium* (payment for bearing crash
risk), not an *anomaly* (a mispricing that traders arbitrage away once published).

**The known danger:** it earns small steady gains and suffers big losses in
crashes (Feb 2018, Mar 2020). The real skill is risk management, which is why the
sizing rule and the VIX term-structure filter below matter as much as the trade.

## The core math (what the P&L is)

A delta-hedged short option earns, each day, approximately

    daily P&L ≈ ½ · Γ · S² · (σ²_implied − σ²_realized) · dt

Γ (gamma) is how fast the option's delta changes, S the SPY price. In words: we are
paid the gap between the variance the option priced in and the variance that
actually showed up. Calm day: we keep the time decay (theta). Big move: we lose
on gamma, because re-hedging forces us to buy high and sell low.

## The rules

| Rule | Choice | Why |
|---|---|---|
| Underlying | SPY | The most liquid options market Alpaca offers |
| Position | **Short 1-month at-the-money straddle** (sell 1 call + 1 put, same strike) | A pure volatility position: at the money, call and put deltas roughly cancel |
| Expiry | Standard monthly SPY expiry (third Friday; Thursday if the exchange is closed) | The most liquid contracts |
| Entry | At the close of the first trading day after a monthly expiry, sell the straddle expiring at the *next* monthly expiry (about 4-5 weeks) | Always one position, rolled monthly |
| Strike | The $1 strike closest to SPY's close | SPY strikes are $1 apart near the money |
| Delta hedge | Every day at the close, trade SPY shares so that the straddle + shares have zero delta (Black-Scholes delta) | Removes the direction bet; once a day is the standard discrete-hedging assumption |
| VIX filter | Every day at the close: if VIX ≥ VIX3M (term structure inverted = stress), buy back the straddle, unwind the hedge, and stay flat until the next monthly entry. Don't open a new straddle on an entry day if VIX ≥ VIX3M. | Stop selling insurance when the market is already panicking |
| Exit | Hold to expiry. Settle at intrinsic value at the expiry-day close. | Collects the full premium; live, we close on expiry day instead (see below) |
| Sizing | At entry: the number of straddles such that the **crash scenario** loses at most **15% of the book**. Crash scenario = SPY −20% instantly, implied vol ×3 (capped at 150%), hedge included. Fractional contracts in the backtest. | Size for the crash we haven't seen, not for the average day |
| No leverage | Option notional (straddles × 100 × SPY price) never above 100% of the book | Same spirit as Book 1 |

## How the backtest prices options

Free historical SPY option prices don't exist before 2024, so the backtest uses
the standard approach of model prices, then checks them against real prices.

- **Model:** Black-Scholes with SPY's actual (not dividend-adjusted) price, the
  13-week T-bill rate (^IRX), and SPY's trailing 12-month dividend yield.
- **Implied vol:** VIX/100 minus a fixed haircut *h*. The VIX includes the put skew
  and sits a bit above at-the-money implied vol, so selling "at the VIX" would
  overstate the premium. *h* is measured once, before the strategy backtest, as the
  median gap between the VIX and the real at-the-money ~30-day SPY implied vol in
  Alpaca's 2024-2026 option data. If the measured gap is negative, *h* = 0. The
  same VIX − *h* is used to mark the position every day until expiry.
- **American vs. European:** SPY options are American (exercisable any day).
  Black-Scholes is European. Before the backtest, a binomial tree (Cox-Ross-
  Rubinstein) measures the early-exercise premium on the options we actually trade,
  to check the approximation. The backtest assumes no early assignment.

### Check 2 result: American vs. European (2026-11-23, before any backtest)

`src/check_early_exercise.py` priced our straddle (strike $690, rates 5%, the
unfavourable case) with Black-Scholes and with a 1,000-step American tree:

- **At entry** (30 days, at the money): American worth $0.13-0.16 more, i.e.
  0.2-0.9% of the straddle. Black-Scholes slightly *under*states the premium we
  receive, a small conservative bias.
- **After a selloff** (SPY -5% to -10%, put in the money): American worth up to
  $1.11 more, i.e. **up to 2.9%**. Here Black-Scholes *under*states what it costs us
  to buy the straddle back, a non-conservative bias, and exactly in the stressed
  markets where the VIX filter makes us buy back.
- **After a rally** (call in the money): no gap (dividends too small to matter).

**Refinement, decided now, before any backtest:** every option *trade* in the
backtest (selling at entry, buying back on a filter exit) is priced with the
American tree. Black-Scholes is still used for daily deltas, crash sizing and
marking open positions, where the gap is small and only shifts P&L between days.

### Check 3 result: Monte Carlo engine check (2026-11-23, before any backtest)

`src/check_monte_carlo.py`: 50,000 simulated months per case, straddle sold at 20%
implied vol, hedged once a day (per share, before costs):

| Market realizes | Avg P&L | Theory |
|---|---|---|
| 20% (= sold) | ≈ $0 | $0 |
| 15% (calmer) | +$7.97 | +$7.94 |
| 25% (wilder) | −$7.87 | −$7.94 |

- Also ≈ $0 with 4% rates and dividends (interest and dividend handling correct).
- **Hedging only once a day leaves noise of about $4.4-5 per share per month**,
  matching the Derman-Kamal formula (√(π/4) · σ · vega / √n) within 5%; hedging
  4x a day halves it. A realistic 3-vol-point premium is worth about $4.8 a month,
  so **each month's noise is as big as the edge**: single months tell us little,
  and in a Black-Scholes world it takes months, in real data (fat tails) far longer.
- Locked in as `tests/test_vol_engine.py` (7 tests).

### Check 4 result: real option prices vs. the VIX (2026-11-23, before any backtest)

`src/check_real_options.py` took, for 679 trading days (Feb 2024 to Nov 2026), the
real closing prices of the straddle we would sell (monthly expiry closest to 30
days, strike nearest SPY) from Alpaca, and found its implied vol with the American
tree.

- **The VIX was above real at-the-money implied vol on 100% of days**, by a median
  of 2.83 vol points. Reason: the VIX is built from a strip of SPX options that
  includes expensive out-of-the-money puts (the skew). A good part of the
  "insurance premium" in the VIX sits in those puts, not in the at-the-money
  straddle we sell.
- **The gap grows with the VIX:** ~2.1 points when VIX < 15, ~2.9 at 15-20, ~3.6
  at 20-30, ~5.1 above 30. Real at-the-money vol is a steady **~84% of the VIX**
  (median ratio 0.837, middle half 0.81-0.86).

**Change from the pre-registered rule (decided now, before any backtest):** the
rule said "VIX minus a fixed haircut". A fixed haircut of 2.83 would overstate the
premium by **2.3 vol points on average when VIX > 25**, flattering the backtest
exactly in the stressed markets that decide a short-vol book's fate. A scaled
haircut fits every regime (error +0.2 points when VIX > 25; median error 0.46
vs. 0.53). So the backtest uses **implied vol = VIX × 0.837**. Fitting a single
ratio on 2024-2026 and applying it to 2006-2023 assumes the skew's share of the
VIX is stable; that assumption is stated here, not hidden.

**Option spreads:** Alpaca has no historical option quotes, only today's. On
2026-11-23 (a stressed day: VIX 35.9 at Friday's close, SPY +5% intraday), the 24
contracts within $5 of SPY (next two monthly expiries) had a **median half-spread
of $0.09** (max $0.34), from Alpaca's free "indicative" feed. That is wider than
the $0.05 assumed, so by the pre-registered rule **the cost becomes $0.09 per share
per option, stress test $0.18**. Probably conservative for calm markets, but a
single snapshot can't show that, so the conservative number stands.

## Costs (fixed up front)

- **Options:** pay half the bid-ask spread on every option trade: **$0.05 per share
  per option** (a $0.10-wide market), on entry, on any filter buy-back, and on the
  in-the-money leg at expiry. **Stress test: $0.10.** If Alpaca's 2024-2026 data
  shows typical spreads wider than this, the measured number replaces it, measured
  before the strategy backtest.
- **Hedge:** 1bp per side on SPY share trades (SPY's spread is about 0.15bp, so this
  is conservative).
- **No interest** is credited on idle cash or premium received. Returns are pure
  strategy P&L, which understates what a real account (cash in T-bills) earns.

## Checks before believing any result

1. **Pricer tests:** Black-Scholes against known textbook values and put-call parity.
2. **Binomial tree:** converges to Black-Scholes for European options; measures the
   American early-exercise premium for 1-month at-the-money SPY options.
3. **Monte Carlo engine check:** simulate SPY paths with a volatility we choose.
   If options are sold at the same vol the market then realizes, average P&L before
   costs must be about zero. If sold at 20% and the market realizes 15%, P&L must
   match the formula above. Also measures the noise from hedging only once a day.
4. **Real-price check:** model prices vs. real Alpaca SPY option prices, 2024-2026
   (this is where *h* and the spread are measured).

## The backtest and what we report

- **Period:** from the first monthly cycle when SPY, VIX, VIX3M and ^IRX are all
  available (VIX3M starts around the end of 2007, so this includes 2008), to today.
- **Report:** annual return, volatility, Sharpe, max drawdown, worst day, worst
  month; P&L split into premium collected vs. hedging losses; average implied vs.
  realized vol; results by year; how often the filter was triggered.
- **Comparisons:** the same strategy *without* the VIX filter (diagnostic, to show
  what the filter adds), and SPY buy-and-hold.
- **After the backtest:** fat-tailed Monte Carlo (block bootstrap of S&P 500 daily
  history back to the 1950s, so 1987 is included, plus crash-jump scenarios) to see
  how the sizing holds up in crashes worse than our sample; bootstrap confidence
  range for the Sharpe ratio.

## What counts as "it doesn't work"

Decided up front, same bar as attempt #1:

- Sharpe after costs below 0.5, **or**
- not positive with the stress-test option spreads ($0.10), **or**
- any single day in the backtest losing more than the 15% crash limit (the sizing
  failed at its one job).

If it fails, we report it as is.

## Result (2026-11-23): it does not pass

`src/vol_backtest.py`, rules exactly as above, July 2006 to November 2026 (221
monthly cycles traded, 23 skipped at entry by the filter). 4 hand-checkable tests
in `tests/test_vol_backtest.py` pass.

| | Official ($0.09 spreads) | Stress ($0.18) | No VIX filter | SPY buy & hold |
|---|---|---|---|---|
| Annual return | -0.7% | -2.0% | -0.6% | +10.8% |
| Volatility | 2.9% | 3.0% | 3.9% | 19.4% |
| Sharpe | -0.23 | -0.65 | -0.14 | 0.63 |
| Max drawdown | -19.9% | -37.7% | -20.9% | -55.2% |
| Worst day | -2.6% | -2.6% | -3.3% | -10.9% |

**Verdict:** Sharpe -0.23 (needed 0.5), negative at stress spreads -> **does not pass.**
(The crash sizing did its job: worst day -2.6%, far inside the 15% limit.)

Where the money went ($, on a $100k start, before costs):

| Cycles | Count | Avg length | P&L per cycle |
|---|---|---|---|
| Held to expiry (calm) | 154 | 27 days | **+$363** |
| Closed by the VIX filter (stress) | 67 | 12 days | **-$597** |

Plus costs of about $130 per cycle (option spreads + hedging), $29k in total.

What we learned:

1. **The at-the-money premium exists but is thin.** We sold at 14.8% vol on average
   vs. 11.7% realized while held (above realized in 79% of cycles), but the real-price
   check showed the VIX overstates at-the-money vol by ~16%: much of the insurance
   premium lives in out-of-the-money puts (the skew), not in the straddle we sold.
2. **The VIX filter sold the insurance back at the top.** It exits the day *after*
   vol has spiked, locking in the mark-to-market loss and missing the usual fall in
   vol afterwards. A stop-loss on a short-vol position is, in effect, buying vol
   after it has gone up. Without the filter the result is no better (-0.6% a year,
   worse months), because the spikes then hit in full.
3. **Costs finish it off.** Option spreads and hedging (~1.6% a year) are larger
   than the ~0.8% a year the strategy makes before costs.
4. **Sizing for a 1987-style crash makes the book safe but small** (average notional
   61% of the book), so the premium collected is small relative to costs.

## Book 2 closed (2026-11-23)

Lesson 1 points to the natural attempt #3: sell out-of-the-money puts, where the
skew premium lives. It was **not attempted**, because it can't be tested honestly
with the data available: free historical prices for those options start in 2024
(~34 months, too few when one month's noise is as big as the edge), and the
standard academic source (OptionMetrics) is not in BU's WRDS subscription.
Modelling the skew without real prices would mean guessing the very thing being
tested. Tweaking attempt #2 after seeing its results was ruled out as overfitting
(the no-filter and zero-spread diagnostics show no small change rescues it).

Book 2 ends as a research write-up: two pre-registered strategies, both failed,
both explained. The tooling (option pricer, American binomial tree, hedging
simulator, Monte Carlo checks, real-price check) stays in the repo.

## Going live (not applicable: the strategy did not pass; kept for the record)

- Alpaca paper account for Book 2 (PA3CY7MMI); options must be enabled on it.
- **Whole contracts only:** one SPY straddle is ~$69k of notional. If the 15% crash
  rule rounds down to zero contracts on a $100k account, the account size has to
  change (Alpaca lets you set a paper account's balance). Decide then, openly.
- **Early assignment (American options):** if the short call is in the money the
  day before SPY goes ex-dividend, buy it back (someone may exercise to collect the
  dividend). If assigned anyway, re-hedge immediately.
- **Expiry day:** close the straddle at 3:45pm instead of letting it expire, to avoid
  automatic exercise and "pin risk" (not knowing whether a near-the-money option
  will be exercised).
- Orders shown and confirmed before sending, as always. At least 1 month of paper
  trading before any decision about real money.
