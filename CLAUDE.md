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
  **Attempt #2 (DESIGNED, not built):** volatility risk premium: short 1-month ATM SPY
  straddle, delta-hedged daily, VIX/VIX3M filter checked daily, sized so a -20% crash
  costs <=15% of the book. Rules pre-registered in `docs/book2_attempt2_vol_premium.md`.
  Build order: pricer + binomial tree + Monte Carlo engine check + real-price check
  (Alpaca options data from Feb 2024), then backtest, then fat-tail stress tests.
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
1. Commit current work in GitHub Desktop.
2. Book 1 live: script that computes this week's target weights and rebalances the
   Alpaca paper account (show orders and ask before sending).
3. Book 2: design together, then data (Alpaca intraday bars), backtest, go live.
4. Weekly "trader's note" on positions/P&L and why; README write-up at the end.
