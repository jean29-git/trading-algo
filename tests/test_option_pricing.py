"""
Tests for the option pricer: textbook values and no-arbitrage relationships.

If the pricer fails any of these, every number built on it (the backtest,
the hedges, the crash sizing) would be wrong.

Run from the project folder:   python tests/test_option_pricing.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from option_pricing import binomial_tree, black_scholes, greeks, implied_vol  # noqa: E402

# A realistic SPY-like option: $690 spot, at the money, 30 days, 4% rates, 1.2% dividend, 18% vol.
SPY = dict(S=690.0, K=690.0, T=30 / 365, r=0.04, q=0.012, sigma=0.18)


def test_textbook_values():
    """Hull, Options, Futures and Other Derivatives: S=42, K=40, r=10%, vol=20%, 6 months."""
    call = black_scholes(42, 40, 0.5, 0.10, 0.0, 0.20, "call")
    put = black_scholes(42, 40, 0.5, 0.10, 0.0, 0.20, "put")
    assert round(call, 2) == 4.76 and round(put, 2) == 0.81, (call, put)


def test_put_call_parity():
    """No-arbitrage: call - put = S·e^(-qT) - K·e^(-rT), whatever the volatility."""
    for S, K, sigma in [(690, 690, 0.18), (690, 650, 0.40), (100, 120, 0.10)]:
        p = dict(S=S, K=K, T=0.25, r=0.04, q=0.012, sigma=sigma)
        lhs = black_scholes(**p, kind="call") - black_scholes(**p, kind="put")
        rhs = S * np.exp(-0.012 * 0.25) - K * np.exp(-0.04 * 0.25)
        assert abs(lhs - rhs) < 1e-9, (lhs, rhs)


def test_greeks_match_finite_differences():
    """Each Greek must equal the 'bump the input slightly and reprice' answer."""
    for kind in ("call", "put"):
        g = greeks(**SPY, kind=kind)
        price = lambda **kw: black_scholes(**{**SPY, **kw}, kind=kind)  # noqa: E731
        h = 0.01
        delta = (price(S=SPY["S"] + h) - price(S=SPY["S"] - h)) / (2 * h)
        gamma = (price(S=SPY["S"] + h) - 2 * price() + price(S=SPY["S"] - h)) / h ** 2
        vega = (price(sigma=SPY["sigma"] + 0.0001) - price(sigma=SPY["sigma"] - 0.0001)) / 0.0002 / 100
        # Theta is the INSTANTANEOUS decay rate (quoted per day), so bump time by a
        # tiny amount, not a full day (decay itself speeds up over a whole day).
        eps = 1e-6
        theta = (price(T=SPY["T"] - eps) - price(T=SPY["T"] + eps)) / (2 * eps) / 365
        assert abs(g["delta"] - delta) < 1e-6, (kind, "delta", g["delta"], delta)
        assert abs(g["gamma"] - gamma) < 1e-4, (kind, "gamma", g["gamma"], gamma)
        assert abs(g["vega"] - vega) < 1e-6, (kind, "vega", g["vega"], vega)
        assert abs(g["theta"] - theta) < 1e-6, (kind, "theta", g["theta"], theta)


def test_straddle_delta():
    """A straddle at strike = spot is NOT exactly delta-neutral (~+0.06 here, from rates and
    the vol term in d1); the exactly neutral strike is K = S·e^((r - q + sigma²/2)·T).
    That gap is one reason we hedge daily instead of assuming the straddle is neutral."""
    straddle_delta = lambda **kw: (greeks(**{**SPY, **kw}, kind="call")["delta"]  # noqa: E731
                                   + greeks(**{**SPY, **kw}, kind="put")["delta"])
    assert 0.03 < straddle_delta() < 0.08, straddle_delta()
    neutral_k = SPY["S"] * np.exp((SPY["r"] - SPY["q"] + SPY["sigma"] ** 2 / 2) * SPY["T"])
    assert abs(straddle_delta(K=neutral_k)) < 1e-9, straddle_delta(K=neutral_k)


def test_implied_vol_round_trip():
    """Price an option at 18% vol, then ask which vol fits that price: must get 18% back."""
    for kind in ("call", "put"):
        price = black_scholes(**SPY, kind=kind)
        iv = implied_vol(price, SPY["S"], SPY["K"], SPY["T"], SPY["r"], SPY["q"], kind)
        assert abs(iv - 0.18) < 1e-6, (kind, iv)


def test_expiry_is_intrinsic_value():
    assert black_scholes(700, 690, 0, 0.04, 0.012, 0.18, "call") == 10
    assert black_scholes(700, 690, 0, 0.04, 0.012, 0.18, "put") == 0


def test_tree_converges_to_black_scholes():
    """A European tree with many steps must agree with the formula (to about a cent)."""
    for kind in ("call", "put"):
        bs = black_scholes(**SPY, kind=kind)
        tree = binomial_tree(**SPY, kind=kind, american=False, steps=2000)
        assert abs(tree - bs) < 0.01, (kind, tree, bs)


def test_american_call_no_dividend_equals_european():
    """Merton: never exercise a call early on a stock with no dividends."""
    p = {**SPY, "q": 0.0}
    american = binomial_tree(**p, kind="call", american=True, steps=1000)
    european = binomial_tree(**p, kind="call", american=False, steps=1000)
    assert abs(american - european) < 1e-9, (american, european)


def test_american_put_worth_more_when_deep_in_the_money():
    """A deep in-the-money put is worth exercising early (get the strike now, earn interest on it)."""
    p = {**SPY, "S": 550.0, "T": 0.5, "r": 0.05}
    american = binomial_tree(**p, kind="put", american=True)
    european = binomial_tree(**p, kind="put", american=False)
    assert american > european + 0.5, (american, european)
    assert american >= 690.0 - 550.0  # never worth less than exercising right now


if __name__ == "__main__":
    tests = [f for name, f in dict(globals()).items() if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
