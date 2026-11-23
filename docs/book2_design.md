# Book 2 (tactical): intraday mean reversion, design

*Written 2026-11-22, before any Book 2 data was downloaded or any backtest was run.
Every parameter below is a standard textbook value chosen up front. The git history
of this file is the proof that the rules were not tuned to the results.*

## The idea

When a liquid ETF drops sharply within the day, buy it, betting the move was an
overreaction, and sell when it bounces back toward its recent average.

Two risks shape every rule below:

1. **Catching a falling knife.** Some dips are the start of a real selloff. The
   regime filter and the stop-loss exist for this.
2. **Costs.** Book 1 trades weekly; Book 2 trades several times a day, so a few basis
   points per trade decide whether there is any edge at all. Costs are modeled
   conservatively, and results are always shown both before and after costs.

## The rules

| Rule | Choice | Why |
|---|---|---|
| Universe | SPY, QQQ, IWM, DIA, XLF, XLE, XLK, TLT, GLD, EEM | The most liquid ETFs; tightest bid-ask spreads, which matter most at this frequency |
| Bars | 15-minute, regular hours only (9:30-16:00 New York) | Intraday dips play out over minutes to hours; 26 bars a day |
| Regime filter | Only trade an ETF if yesterday's close is above its 200-day moving average | Buy dips in uptrends only; avoids buying "dips" in bear markets (2008, 2020, 2022) |
| Entry | Bar closes 2 standard deviations below its 20-bar moving average | Standard Bollinger Band setting; scales to each ETF's own volatility |
| Take profit | Price climbs back to the 20-bar moving average | The "mean" in mean reversion: about +2σ from entry |
| Stop-loss | Price falls 1σ below entry (σ measured at entry, then frozen) | Risk 1 to make 2, in the same units as the entry rule |
| End of day | Every open position is closed by the end of the day | Pure intraday book: no overnight gap risk |
| Sizing | Hitting the stop loses 0.5% of Book 2's capital | Fixed risk per trade, the way desks set limits; tight stop = bigger size |
| Position limits | Max 25% of the book in one ETF, one position per ETF, no leverage (total ≤ 100%) | Keeps any single trade from dominating |
| Capital | Separate Alpaca paper account | Book 1 keeps its own account; P&L and positions never mix |

## Backtest honesty rules (proposed, to confirm)

These are execution details that stop a backtest from looking better than reality:

- **No look-ahead:** a signal is computed on a bar's close and filled at the *next*
  bar's open. The 200-day filter uses yesterday's close only.
- **Both stop and target inside one bar:** assume the stop was hit first (the worse
  case), since 15-minute bars can't tell which came first.
- **Opening noise:** no new entries in the first 15-minute bar (9:30-9:45).
- **End of day:** no new entries after 15:30; everything still open is sold at the
  15:45 bar's open.
- **Costs:** 2bp per side (4bp round trip) on every trade, roughly half the bid-ask
  spread on the least liquid ETF here (EEM) plus slippage. Also report a stress test
  at 4bp per side. Results are always shown gross *and* net of costs.
- **Data:** Alpaca historical 15-minute bars, as far back as the free plan allows.
- **What we report:** return, volatility, Sharpe, max drawdown, number of trades,
  win rate, average win vs. average loss, and the gross vs. net table. Plus results
  by year, to show whether the edge is stable or came from one period.

## What would count as "it doesn't work"

Decided up front, so we can't move the goalposts later: if the Sharpe after costs
is below about 0.5, or the edge disappears in the 4bp stress test, Book 2 goes
live on paper only as an experiment, and the write-up says so plainly.
