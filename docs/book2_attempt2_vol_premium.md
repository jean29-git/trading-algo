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

## Going live (later, paper only)

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
