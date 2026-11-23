"""
Tests for the straddle hedging simulator, against option theory.

Each test simulates thousands of fake months of SPY with a volatility we
choose, so the right answer is known in advance.

Run from the project folder:   python tests/test_vol_engine.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from option_pricing import greeks                                      # noqa: E402
from vol_engine import gbm_paths, short_straddle_pnl, straddle_price   # noqa: E402

S0 = K = 690.0
T, DAYS, N = 21 / 252, 21, 50_000
PREMIUM = straddle_price(S0, K, T, 0, 0, 0.20)
TOLERANCE = 0.005 * PREMIUM  # within 0.5% of the premium (~$0.16 per share)


def run(sold, realized, hedge_vol=None, r=0.0, q=0.0, seed=2):
    paths = gbm_paths(S0, realized, T, DAYS, N, drift=r - q, seed=seed)
    return short_straddle_pnl(paths, K, T, sold, r=r, q=q, hedge_vol=hedge_vol)["pnl"]


def theory(sold, realized):
    """Continuous-hedging answer: the price difference between the two vols."""
    return straddle_price(S0, K, T, 0, 0, sold) - straddle_price(S0, K, T, 0, 0, realized)


def test_fair_price_means_zero_profit():
    """Sold at 20%, market realizes 20%: no premium to collect."""
    assert abs(run(0.20, 0.20).mean()) < TOLERANCE


def test_calm_market_earns_the_vol_gap():
    """Sold at 20%, market realizes 15%: earn about V(20%) - V(15%)."""
    assert abs(run(0.20, 0.15).mean() - theory(0.20, 0.15)) < TOLERANCE


def test_wild_market_loses_the_vol_gap():
    """Sold at 20%, market realizes 25%: lose about V(25%) - V(20%)."""
    assert abs(run(0.20, 0.25).mean() - theory(0.20, 0.25)) < TOLERANCE


def test_rates_and_dividends_dont_create_fake_profit():
    """With 4% rates and a 1.2% dividend yield, a fairly priced straddle still earns ~0
    (checks the interest on cash and the dividends on the hedge shares)."""
    assert abs(run(0.20, 0.20, r=0.04, q=0.012).mean()) < TOLERANCE


def test_daily_hedging_noise_matches_theory():
    """Hedging once a day leaves noise of about sqrt(pi/4) · vol · vega / sqrt(n hedges)
    (Derman & Kamal). Hedging at the true vol isolates that noise."""
    vega = 100 * (greeks(S0, K, T, 0, 0, 0.15, "call")["vega"] + greeks(S0, K, T, 0, 0, 0.15, "put")["vega"])
    predicted = np.sqrt(np.pi / 4) * 0.15 * vega / np.sqrt(DAYS)
    measured = run(0.20, 0.15, hedge_vol=0.15).std()
    assert abs(measured / predicted - 1) < 0.10, (measured, predicted)


def test_more_frequent_hedging_means_less_noise():
    """Hedge 4x a day instead of once: noise should roughly halve (1 / sqrt(4))."""
    daily = run(0.20, 0.15, hedge_vol=0.15).std()
    paths = gbm_paths(S0, 0.15, T, DAYS * 4, N, seed=2)
    four_a_day = short_straddle_pnl(paths, K, T, 0.20, hedge_vol=0.15)["pnl"].std()
    assert 0.4 < four_a_day / daily < 0.6, (four_a_day, daily)


def test_costs_reduce_pnl():
    paths = gbm_paths(S0, 0.20, T, DAYS, 2_000, seed=3)
    free = short_straddle_pnl(paths, K, T, 0.20)["pnl"].mean()
    costly = short_straddle_pnl(paths, K, T, 0.20, hedge_cost_bps=1)["pnl"].mean()
    assert costly < free


if __name__ == "__main__":
    tests = [f for name, f in dict(globals()).items() if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
