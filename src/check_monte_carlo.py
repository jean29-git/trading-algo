"""
Monte Carlo check of the straddle hedging simulator.

We simulate 50,000 fake months of SPY where WE choose the realized
volatility, then sell a 1-month at-the-money straddle at 20% implied vol
and delta-hedge it once a day. Theory says what should happen:

  - market realizes 20% (= what we sold): average P&L about zero
  - market realizes 15% (calmer than priced): we earn about
        V(20%) - V(15%), the price gap between the two vols
  - market realizes 25% (wilder than priced): we lose about the same

If the simulator doesn't reproduce these, it has a bug, and nothing it
says about real data can be trusted.

It also measures the NOISE from hedging only once a day, which tells us
how many months of history we need before a result means anything.

Kept clean on purpose: zero rates, no dividends, no costs, so the only
thing driving P&L is implied vs. realized volatility.

Run from the project folder:   python src/check_monte_carlo.py
"""

import numpy as np

from vol_engine import gbm_paths, short_straddle_pnl, straddle_price

S0 = K = 690.0
T, DAYS = 21 / 252, 21       # one trading month, hedged at each daily close
N_PATHS = 50_000
SOLD_AT = 0.20


def scenario(realized, hedge_vol=None, sold_at=SOLD_AT, seed=1):
    paths = gbm_paths(S0, realized, T, DAYS, N_PATHS, seed=seed)
    pnl = short_straddle_pnl(paths, K, T, sold_at, hedge_vol=hedge_vol)["pnl"]
    theory = straddle_price(S0, K, T, 0, 0, sold_at) - straddle_price(S0, K, T, 0, 0, realized)
    return pnl, theory


def main() -> None:
    premium = straddle_price(S0, K, T, 0, 0, SOLD_AT)
    print(f"Sell a 1-month ${K:.0f} straddle at {SOLD_AT:.0%} implied vol: premium ${premium:.2f} per share")
    print(f"{N_PATHS:,} simulated months per line, hedged once a day. Per share, before costs.\n")
    print(f"{'Market realizes':<34} {'Avg P&L':>8} {'Theory':>8} {'Std error':>10} {'Std dev':>8} {'Win %':>6}")

    lines = [
        ("20% (same as sold)", 0.20, None),
        ("15% (calmer than priced)", 0.15, None),
        ("25% (wilder than priced)", 0.25, None),
        ("15%, hedged with TRUE vol", 0.15, 0.15),
    ]
    for label, realized, hedge_vol in lines:
        pnl, theory = scenario(realized, hedge_vol)
        print(f"{label:<34} {pnl.mean():>+8.2f} {theory:>+8.2f} {pnl.std() / np.sqrt(len(pnl)):>10.3f} "
              f"{pnl.std():>8.2f} {(pnl > 0).mean():>6.0%}")

    # How noisy is a realistic premium? Sell at 18%, market realizes 15%
    # (a 3-vol-point gap, roughly the typical size of the premium).
    pnl, theory = scenario(0.15, sold_at=0.18, seed=2)
    months_needed = (2 * pnl.std() / pnl.mean()) ** 2
    print(f"\nRealistic case: sold at 18%, realized 15% -> avg {pnl.mean():+.2f}, "
          f"std {pnl.std():.2f} per month (theory {theory:+.2f})")
    print(f"Months needed before that edge is 2 standard errors from zero: about {months_needed:.0f}")
    print("Caveat: that is in a Black-Scholes world (constant vol, no crashes). Real months are far\n"
          "noisier (vol spikes, crash days), so real data needs many more months. The real backtest\n"
          "and the fat-tailed stress tests will show how many.")


if __name__ == "__main__":
    main()
