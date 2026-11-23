# Project brief for Claude

## Who I am
Jean, sophomore at Boston University (Economics & CS), recruiting for Sales & Trading
internships (summer 2028). New to coding, Git and the terminal: explain every step
in plain English, go one step at a time, and explain code so I can defend it in an
interview. I want to be a trader, not a developer: market logic matters more than
clever code.

## The project
A passion project I'll update several times a week and show to friends, family and
people in the industry. Two strategy "books", run like a small trading desk:

- **Book 1, core (DONE: backtest; TODO: live):** cross-asset trend following on 8 ETFs
  (SPY, EFA, EEM, TLT, IEF, GLD, DBC, UUP). Hold an asset if its 12-month return > 0,
  size by inverse 60-day volatility (risk parity), idle cash in BIL (T-bills),
  rebalance weekly at Friday close, 5bp cost per dollar traded. Long-only, no leverage.
  Backtest 2008-2026: 3.4%/yr, vol 4.5%, Sharpe 0.76, max DD -7.7%, vs 60/40
  (8.5%, Sharpe 0.77, DD -31.4%) and the same basket with no trend filter
  (4.7%, Sharpe 0.83, DD -12.5%). Honest takeaway: the trend filter cut drawdowns
  but lowered Sharpe vs. always holding the basket. We report this as is.
- **Book 2, tactical (v1 DONE: backtest FAILED):** intraday mean reversion, rules
  pre-registered in `docs/book2_design.md` (10 liquid ETFs, 15-min bars, buy 2σ dips
  below the 20-bar average, 200-day filter, 1σ stop, flat by close, own paper account
  PA3CY7MMI). Result 2016-2026: no edge before costs (-0.7bp/trade), -13.7%/yr and
  Sharpe -2.82 after 2bp costs. Reported as is. Code: `src/book2_*.py`,
  tests in `tests/test_book2_engine.py`.
  **Attempt #2 (DONE: backtest FAILED):** volatility risk premium: short 1-month ATM SPY
  straddle, delta-hedged daily, VIX/VIX3M filter checked daily, sized so a -20% crash
  costs <=15% of the book. Rules pre-registered in `docs/book2_attempt2_vol_premium.md`.
  Real-price check: ATM vol = VIX x 0.837, spreads $0.09. Result 2006-2026: -0.7%/yr,
  Sharpe -0.23. Calm months +$363/cycle, filter exits -$597/cycle, costs ~1.6%/yr.
  Code: `src/option_pricing.py`, `vol_engine.py`, `vol_backtest.py` (+ tests).
  **Book 2 is CLOSED (2026-11-23):** attempt #3 (OTM put selling) not tested, no
  historical OTM option data (OptionMetrics not in BU's WRDS). Don't reopen by
  tweaking attempts #1/#2. BU's WRDS does have CRSP (survivorship-free stocks), useful
  for a future Book 3 (stat arb / relative value).
- **Phase 2 idea:** volatility-regime filter (VIX vs VIX3M term structure).

## Rules
- Don't overfit: pick parameters up front from standard values, no tuning to results.
- Be honest when something doesn't work; that's still a good story.
- Paper trading only (`paper=True`). No real money until paper has run 1+ month.
- API keys live in `.env` (git-ignored). Never print, log or commit them.
- Ask before pushing to GitHub or placing any orders, even paper ones.

## Setup
- Mac, project at ~/Desktop/trading-algo, Python 3.9 in `.venv`
  (`source .venv/bin/activate`). GitHub repo: jean29-git/trading-algo (private),
  managed with GitHub Desktop.
- `src/config.py` settings, `src/data.py` yfinance download + quality checks,
  `src/strategy.py` signal + weights, `src/backtest.py` engine + metrics + chart,
  `src/alpaca_check.py` read-only Alpaca connection test (working).

## Next steps
1. Book 1 live: `src/rebalance.py` is built (dry run by default, `--send` asks for a
   typed yes). First real rebalance Fri 2026-11-27, a half day (close 1pm ET): run
   before 12:50pm ET so market-on-close orders are accepted; review orders with Jean.
2. Weekly "trader's note" on Book 1 positions/P&L and why (first one: the -9% week
   to Nov 20, VIX 35.9 above VIX3M, then a sharp rebound on Nov 23).
3. Phase 2 idea (VIX vs VIX3M filter for Book 1): note Book 2 attempt #2 found this
   filter exits *after* vol spikes; design carefully, pre-register before testing.
4. Later: Book 3 (stat arb / relative value), designed from scratch, CRSP via WRDS.
5. README write-up: Book 1 results, Book 2's two failures and what they taught.
