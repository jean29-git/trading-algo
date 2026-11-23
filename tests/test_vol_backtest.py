"""
Hand-checkable tests for the volatility book backtest.

Made-up markets where we can work out the answer on paper:
  - SPY never moves: we should keep exactly the premium, minus costs
  - a stress day mid-month: the VIX filter must buy everything back
  - stress on an entry day: no new straddle that month

Run from the project folder:   python tests/test_vol_backtest.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from config import VOL_IV_SCALE                  # noqa: E402
from vol_backtest import START_EQUITY, crash_size, run  # noqa: E402
from vol_engine import american_straddle         # noqa: E402

HALF_SPREAD = 0.09


def flat_market(price=700.0, vix=0.20, vix3m=0.22):
    """Jan-Apr 2024 weekdays (no holidays in this made-up calendar, so Feb 19 counts as a
    trading day). Monthly expiries: Jan 19, Feb 16, Mar 15, Apr 19."""
    days = pd.bdate_range("2024-01-02", "2024-04-30")
    return pd.DataFrame({"spy": price, "vix": vix * 100, "vix3m": vix3m * 100,
                         "r": 0.0, "q": 0.0, "dividend": 0.0}, index=days)


def test_flat_market_keeps_the_premium():
    """SPY never moves, so the straddle expires worthless and the hedge makes nothing:
    option P&L over the first cycle must equal exactly n x the premium received."""
    data = flat_market()
    result, cycles = run(data, HALF_SPREAD)
    first = cycles.iloc[0]
    assert first["entry"] == pd.Timestamp("2024-01-22") and first["expiry"] == pd.Timestamp("2024-02-16")
    T = (first["expiry"] - first["entry"]).days / 365
    premium = american_straddle(700.0, 700.0, T, 0, 0, 0.20 * VOL_IV_SCALE)
    n = crash_size(START_EQUITY, 700.0, 700.0, T, 0, 0, 0.20 * VOL_IV_SCALE, premium)
    cycle = result.loc["2024-01-22":"2024-02-16"]
    assert abs(cycle["option_pnl"].sum() - n * premium) < 1e-6, (cycle["option_pnl"].sum(), n * premium)
    assert abs(cycle["hedge_pnl"].sum()) < 1e-9
    assert cycle["cost_usd"].sum() >= n * 2 * HALF_SPREAD  # spreads on entry, + small hedge costs
    assert first["how"] == "expiry"


def test_crash_sizing_hits_the_limit_or_the_notional_cap():
    """The crash scenario should cost exactly 15% of the book (unless notional caps it)."""
    T, sigma = 25 / 365, 0.20 * VOL_IV_SCALE
    premium = american_straddle(700.0, 700.0, T, 0, 0, sigma)
    n = crash_size(START_EQUITY, 700.0, 700.0, T, 0, 0, sigma, premium)
    assert n * 700.0 <= START_EQUITY + 1e-6                         # never more notional than the book
    crash_value = american_straddle(560.0, 700.0, T, 0, 0, min(3 * sigma, 1.5))
    loss = n * (crash_value - premium)                               # hedge ~0 at the money with r=q=0
    assert loss <= 0.15 * START_EQUITY * 1.02, loss


def test_vix_filter_buys_back_mid_month():
    data = flat_market()
    data.loc["2024-02-01", "vix3m"] = 15.0                           # VIX 20 >= VIX3M 15: stressed
    result, cycles = run(data, HALF_SPREAD)
    first = cycles.iloc[0]
    assert first["how"] == "VIX filter" and first["exit"] == pd.Timestamp("2024-02-01"), first.to_dict()
    assert (result.loc["2024-02-02":"2024-02-16", "risky"] == 0).all()  # flat until next entry
    assert cycles.iloc[1]["entry"] == pd.Timestamp("2024-02-19")        # re-enters next month


def test_no_entry_when_stressed_on_entry_day():
    data = flat_market()
    data.loc["2024-02-19", "vix3m"] = 15.0
    _, cycles = run(data, HALF_SPREAD)
    skipped = cycles[cycles["entry"] == pd.Timestamp("2024-02-19")]
    assert skipped.iloc[0]["how"] == "skipped (VIX filter)"
    assert cycles.iloc[-1]["entry"] == pd.Timestamp("2024-03-18")       # next cycle trades normally


if __name__ == "__main__":
    tests = [f for name, f in dict(globals()).items() if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
