"""
Book 2: the trading signal and position sizing (intraday mean reversion).

The rules, easy to say out loud in an interview (full reasoning in
docs/book2_design.md):

1. REGIME (when we're allowed to play): only buy dips in an ETF whose
   last daily close is above its 200-day average. In a long-term uptrend,
   a sharp intraday drop is more often noise (a big seller, a headline
   overreaction) than the start of a real selloff.

2. ENTRY (what a 'sharp dip' is): a 15-minute bar closes more than 2
   standard deviations below its 20-bar average. Measuring in standard
   deviations makes the rule fair across ETFs: a 0.5% drop is a big deal
   for SPY but ordinary for XLE.

3. SIZE (how much): sized so that hitting the stop would lose 0.5% of the
   book, capped at 25% per ETF. In practice the cap almost always binds
   (15-minute moves are small, so stops are tight).

This file only says WHAT we want to do. The backtest (book2_backtest.py)
decides what actually happens: fills, stops, targets, costs.
"""

import pandas as pd

from config import (BOOK2_ENTRY_SIGMA, BOOK2_MA_BARS,
                    BOOK2_MAX_POSITION, BOOK2_REGIME_DAYS, BOOK2_RISK_PER_TRADE,
                    BOOK2_STOP_SIGMA, BOOK2_UNIVERSE)

NY = "America/New_York"


def load_bars(path) -> dict:
    """15-min bars from book2_data.py -> {'open': table, 'high': ..., 'low': ..., 'close': ...}.

    Each table has one row per 15-minute bar (start time, New York) and one
    column per ETF.
    """
    raw = pd.read_csv(path)
    # utc=True first because the file mixes -05:00 (winter) and -04:00 (summer) offsets.
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True).dt.tz_convert(NY)
    tickers = list(BOOK2_UNIVERSE)
    return {field: raw.pivot(index="timestamp", columns="symbol", values=field)[tickers]
            for field in ("open", "high", "low", "close")}


def trading_day(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """The calendar date (New York) each bar belongs to."""
    return index.tz_localize(None).normalize()


def bar_clock(index: pd.DatetimeIndex) -> tuple:
    """For each bar: its number within the day (0 = 9:30 bar) and how many bars that day has.

    Full days have 26 bars, half days 14, so 'n' tells us when that day ends.
    """
    day = pd.Series(trading_day(index), index=index)
    pos = day.groupby(day).cumcount()
    n = day.groupby(day).transform("size")
    return pos, n


def regime_filter(close: pd.DataFrame) -> pd.DataFrame:
    """True on days when the ETF's PREVIOUS daily close was above its 200-day average.

    Uses yesterday's close only, so nothing from today leaks into today's decision.
    """
    day = trading_day(close.index)
    daily_close = close.groupby(day).last()              # last 15-min close = daily close
    above = daily_close > daily_close.rolling(BOOK2_REGIME_DAYS).mean()
    allowed_today = above.shift(1).fillna(False).astype(bool)  # yesterday's verdict
    return allowed_today.reindex(day).set_axis(close.index)    # spread over every bar of the day


def indicators(bars: dict, use_regime: bool = True) -> dict:
    """Everything the backtest (and later the live script) needs, bar by bar."""
    close = bars["close"]
    ma = close.rolling(BOOK2_MA_BARS).mean()   # the 'mean' we expect price to revert to
    sd = close.rolling(BOOK2_MA_BARS).std()    # how much price normally wobbles around it
    z = (close - ma) / sd                      # how many standard deviations below/above the mean

    pos, n = bar_clock(close.index)
    # Timing: no signal from the opening bar (auction noise), and the last
    # signal is the 15:15 bar, filled at 15:30 (n - 3 = bar 23 on a full day).
    can_enter = (pos >= 1) & (pos <= n - 3)

    entry = (z < -BOOK2_ENTRY_SIGMA) & can_enter.to_numpy()[:, None]  # same timing for every ETF
    if use_regime:
        entry = entry & regime_filter(close)

    # Size so that a stop-out costs RISK_PER_TRADE of the book, capped at MAX_POSITION.
    stop_distance = BOOK2_STOP_SIGMA * sd / close      # stop distance as a % of price
    size = (BOOK2_RISK_PER_TRADE / stop_distance).clip(upper=BOOK2_MAX_POSITION)

    return {"ma": ma, "sd": sd, "z": z, "entry": entry.astype(bool), "size": size,
            "pos": pos, "n": n}
