"""
Hand-checkable tests for the Book 2 engine.

Each test builds a tiny made-up trading day where we can work out the
right answer on paper, then checks the engine agrees. If the engine is
wrong on a case this simple, the 10-year backtest can't be trusted.

Run from the project folder:   python tests/test_book2_engine.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from book2_backtest import simulate          # noqa: E402
from book2_strategy import indicators, regime_filter  # noqa: E402

N_BARS = 26  # one full trading day


def one_day(n_tickers=1):
    """A flat day at $100: average 100, sigma 0.50, no signals, 25% size."""
    times = pd.date_range("2024-01-02 09:30", periods=N_BARS, freq="15min", tz="America/New_York")
    cols = [f"T{i}" for i in range(n_tickers)]
    flat = lambda v: pd.DataFrame(v, index=times, columns=cols, dtype=float)  # noqa: E731
    bars = {f: flat(100.0) for f in ("open", "high", "low", "close")}
    ind = {"ma": flat(100.0), "sd": flat(0.5), "z": flat(0.0), "size": flat(0.25),
           "entry": flat(False).astype(bool),
           "pos": pd.Series(range(N_BARS), index=times), "n": pd.Series(N_BARS, index=times)}
    return bars, ind


def set_bar(bars, t, o, h, l, c, col=0):
    for f, v in zip(("open", "high", "low", "close"), (o, h, l, c)):
        bars[f].iloc[t, col] = v


def dip_at_bar_5(bars, ind):
    """Signal at the 10:45 bar's close; we should buy at the 11:00 bar's open, $99."""
    ind["entry"].iloc[5, 0] = True
    set_bar(bars, 6, 99.0, 99.5, 98.8, 99.2)  # entry bar: no exit (stop 98.5, target 100)


def test_target():
    bars, ind = one_day()
    dip_at_bar_5(bars, ind)
    set_bar(bars, 7, 99.3, 100.2, 99.2, 100.1)  # trades up through the 100 average
    trades, _ = simulate(bars, ind)
    t = trades.iloc[0]
    assert len(trades) == 1 and t["reason"] == "target"
    assert t["entry"] == 99.0 and t["exit"] == 100.0, (t["entry"], t["exit"])


def test_stop_wins_when_both_hit():
    bars, ind = one_day()
    dip_at_bar_5(bars, ind)
    set_bar(bars, 7, 99.3, 100.2, 98.4, 99.0)  # touches the target AND the stop: assume the worse
    t = simulate(bars, ind)[0].iloc[0]
    assert t["reason"] == "stop" and t["exit"] == 98.5, (t["reason"], t["exit"])


def test_gap_through_stop_fills_at_open():
    bars, ind = one_day()
    dip_at_bar_5(bars, ind)
    set_bar(bars, 7, 98.0, 98.2, 97.9, 98.1)  # opens below the 98.5 stop
    t = simulate(bars, ind)[0].iloc[0]
    assert t["reason"] == "stop" and t["exit"] == 98.0, (t["reason"], t["exit"])


def test_end_of_day_exit():
    bars, ind = one_day()
    dip_at_bar_5(bars, ind)
    for b in range(7, N_BARS):
        set_bar(bars, b, 99.0, 99.0, 99.0, 99.0)  # never reaches stop or target
    t = simulate(bars, ind)[0].iloc[0]
    assert t["reason"] == "end of day" and t["exit_time"].strftime("%H:%M") == "15:45"


def test_capital_limit_deepest_dip_first():
    bars, ind = one_day(n_tickers=5)
    ind["entry"].iloc[5, :] = True
    ind["z"].iloc[5, :] = [-2.1, -3.0, -2.5, -2.8, -2.2]  # T0 is the shallowest dip
    trades, _ = simulate(bars, ind)
    assert sorted(trades["ticker"]) == ["T1", "T2", "T3", "T4"], list(trades["ticker"])  # 4 x 25% = 100%


def test_entry_timing_rules():
    """No signal from the opening bar or after 15:15, even on a big dip."""
    times = pd.date_range("2024-01-02 09:30", periods=N_BARS, freq="15min", tz="America/New_York")
    times = times.append(times + pd.Timedelta(days=1))
    close = pd.DataFrame({"T0": 100 + 0.1 * np.tile([1, -1], N_BARS)}, index=times)
    for b in (N_BARS + 0, N_BARS + 10, N_BARS + 24):  # day 2: 9:30, 12:00, 15:30 bars
        close.iloc[b, 0] = 97.0
    bars = {f: close for f in ("open", "high", "low", "close")}
    entry = indicators(bars, use_regime=False)["entry"]["T0"]
    signals = list(entry[entry].index.strftime("%H:%M"))
    assert signals == ["12:00"], signals


def test_regime_uses_yesterday_only():
    """A crash today can't switch the filter off until tomorrow (we don't know today's close yet)."""
    days = pd.bdate_range("2023-01-02", periods=205).tz_localize("America/New_York") + pd.Timedelta(hours=15)
    close = pd.DataFrame({"T0": np.arange(205, dtype=float) + 100}, index=days)
    close.iloc[203, 0] = 10.0  # crash on day 203
    allowed = regime_filter(close)["T0"]
    assert allowed.iloc[203] and not allowed.iloc[204], (allowed.iloc[203], allowed.iloc[204])


if __name__ == "__main__":
    tests = [f for name, f in dict(globals()).items() if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
