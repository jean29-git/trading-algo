"""
Book 2, attempt #2: backtest of the volatility risk premium strategy.

Rules (docs/book2_attempt2_vol_premium.md, all fixed before this ran):
  - The day after each monthly expiry, at the close: if VIX < VIX3M, sell
    the at-the-money SPY straddle expiring at the next monthly expiry.
    Trade price: American binomial tree at implied vol = VIX x 0.837,
    minus the half-spread on each leg.
  - Size: so that a crash (SPY -20% instantly, vol x3) loses <= 15% of the book.
  - Every close: delta-hedge with SPY shares (Black-Scholes delta).
  - Every close: if VIX >= VIX3M, buy the straddle back (American price +
    half-spread), unwind the hedge, stay flat until the next monthly entry.
  - Expiry: settle at intrinsic value (half-spread paid on the in-the-money leg).

Accounting, each day (in dollars, book starts at $100,000):
  option P&L = -(number of straddles) x (change in the straddle's value)
  hedge P&L  = shares x (change in SPY) + shares x dividend paid that day
  costs      = option half-spreads + 1bp on hedge share trades
No interest is credited on cash (conservative, see the design doc).

Run from the project folder:   python src/vol_backtest.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from backtest import metrics
from config import (VOL_CRASH_LIMIT, VOL_CRASH_MOVE, VOL_CRASH_VOL_CAP, VOL_CRASH_VOL_MULT,
                    VOL_HEDGE_COST_BPS, VOL_IV_SCALE, VOL_OPTION_HALF_SPREAD,
                    VOL_OPTION_HALF_SPREAD_STRESS)
from vol_engine import american_straddle, monthly_expiries, straddle_delta, straddle_price

ROOT = Path(__file__).resolve().parent.parent
VOL_DATA_FILE = ROOT / "data" / "vol_data.csv"
RESULTS_DIR = ROOT / "results"
START_EQUITY = 100_000.0


def crash_size(equity, S, K, T, r, q, sigma, premium):
    """Number of straddles (each on 1 share) so the crash scenario costs <= 15% of the book.

    Crash: SPY -20% instantly, implied vol x3 (capped). Loss per straddle =
    rise in the straddle's value + loss on the hedge shares we hold.
    Also capped so option notional never exceeds the book (no leverage).
    """
    S_crash = S * (1 + VOL_CRASH_MOVE)
    vol_crash = min(sigma * VOL_CRASH_VOL_MULT, VOL_CRASH_VOL_CAP)
    value_after = american_straddle(S_crash, K, T, r, q, vol_crash)
    hedge_loss = -straddle_delta(S, K, T, r, q, sigma) * (S_crash - S)
    loss_per_straddle = (value_after - premium) + hedge_loss
    return min(VOL_CRASH_LIMIT * equity / loss_per_straddle, equity / S)


def run(data: pd.DataFrame, half_spread: float, use_filter: bool = True):
    """Simulate the book day by day. Returns (daily results, list of monthly cycles)."""
    days = data.index
    expiries = [e for e in monthly_expiries(days, days[-1]) if e <= days[-1]]
    entry_days = {days[days > e][0]: e for e in expiries[:-1] if (days > e).any()}
    next_expiry = {e: expiries[i + 1] for i, e in enumerate(expiries[:-1])}
    hedge_cost = VOL_HEDGE_COST_BPS / 10_000

    equity, pos, rows, cycles = START_EQUITY, None, [], []
    for i, t in enumerate(days):
        S, vix, vix3m = data.at[t, "spy"], data.at[t, "vix"] / 100, data.at[t, "vix3m"] / 100
        r, q, div = data.at[t, "r"], data.at[t, "q"], data.at[t, "dividend"]
        sigma = vix * VOL_IV_SCALE
        stressed = use_filter and vix >= vix3m
        opt_pnl = hedge_pnl = cost = traded = 0.0

        # 1) Mark the open position to today's close.
        if pos is not None:
            T = max((pos["expiry"] - t).days, 0) / 365
            value = straddle_price(S, pos["K"], T, r, q, sigma)
            opt_pnl = -pos["n"] * (value - pos["value"])
            hedge_pnl = pos["shares"] * (S - pos["S"]) + pos["shares"] * div
            pos.update(value=value, S=S)

            if t >= pos["expiry"]:                                  # 2a) expiry: settle at intrinsic
                if abs(S - pos["K"]) > 0:
                    cost += pos["n"] * half_spread                  # close the in-the-money leg
                cost += abs(pos["shares"]) * S * hedge_cost
                traded += abs(pos["shares"]) * S
                pos["cycle"].update(exit=t, how="expiry")
                pos = None
            elif stressed:                                          # 2b) filter: buy everything back
                buyback = american_straddle(S, pos["K"], T, r, q, sigma)
                opt_pnl -= pos["n"] * (buyback - value)             # real trade price vs. our mark
                cost += pos["n"] * 2 * half_spread + abs(pos["shares"]) * S * hedge_cost
                traded += pos["n"] * S + abs(pos["shares"]) * S
                pos["cycle"].update(exit=t, how="VIX filter")
                pos = None
            else:                                                   # 2c) re-hedge to the new delta
                new_shares = pos["n"] * straddle_delta(S, pos["K"], T, r, q, sigma)
                cost += abs(new_shares - pos["shares"]) * S * hedge_cost
                traded += abs(new_shares - pos["shares"]) * S
                pos["shares"] = new_shares

        # 3) Entry day: sell next month's straddle if the term structure is calm.
        if pos is None and t in entry_days and t >= data["vix3m"].first_valid_index():
            if stressed:
                cycles.append({"entry": t, "how": "skipped (VIX filter)"})
            else:
                expiry = next_expiry[entry_days[t]]
                K, T = float(round(S)), (expiry - t).days / 365
                premium = american_straddle(S, K, T, r, q, sigma)
                n = crash_size(equity, S, K, T, r, q, sigma, premium)
                value = straddle_price(S, K, T, r, q, sigma)
                shares = n * straddle_delta(S, K, T, r, q, sigma)
                opt_pnl += n * (premium - value)                    # sold at the American price, marked at BS
                cost += n * 2 * half_spread + abs(shares) * S * hedge_cost
                traded += n * S + abs(shares) * S
                cycle = {"entry": t, "expiry": expiry, "K": K, "n": n, "sold_vol": sigma,
                         "premium": n * premium, "how": None}
                cycles.append(cycle)
                pos = {"K": K, "expiry": expiry, "n": n, "value": value, "S": S,
                       "shares": shares, "cycle": cycle}

        pnl = opt_pnl + hedge_pnl - cost
        rows.append({"date": t, "return": pnl / equity, "option_pnl": opt_pnl, "hedge_pnl": hedge_pnl,
                     "cost": cost / equity, "cost_usd": cost, "turnover": traded / equity,
                     "risky": (pos["n"] * S / equity) if pos else 0.0})
        equity += pnl

    result = pd.DataFrame(rows).set_index("date")
    first = result.index[result["risky"] > 0][0]                    # start at the first trade
    result = result.loc[first:]
    result["equity"] = (1 + result["return"]).cumprod()
    return result, pd.DataFrame(cycles)


def realized_vol(spy_total: pd.Series, start, end) -> float:
    r = np.log(spy_total.loc[start:end]).diff().dropna()
    return r.std() * np.sqrt(252) if len(r) > 1 else np.nan


def main() -> None:
    data = pd.read_csv(VOL_DATA_FILE, index_col=0, parse_dates=True)
    data = data.loc[data["vix3m"].first_valid_index() - pd.Timedelta(days=40):]

    print("Running: official rules, stress spreads, and no-filter diagnostic...")
    official, cycles = run(data, VOL_OPTION_HALF_SPREAD)
    stress, _ = run(data, VOL_OPTION_HALF_SPREAD_STRESS)
    no_filter, cycles_nf = run(data, VOL_OPTION_HALF_SPREAD, use_filter=False)

    # SPY buy-and-hold with dividends reinvested, for comparison.
    spy_tr = (data["spy"] + data["dividend"]) / data["spy"].shift(1) - 1
    spy = pd.DataFrame({"return": spy_tr.loc[official.index[0]:].fillna(0)})
    spy["equity"] = (1 + spy["return"]).cumprod()
    spy["turnover"] = spy["cost"] = 0.0
    spy["risky"] = 1.0

    results = {"Vol premium (official)": official, f"Stress spreads (${VOL_OPTION_HALF_SPREAD_STRESS})": stress,
               "No VIX filter (diagnostic)": no_filter, "SPY buy & hold": spy}
    start, end = official.index[0], official.index[-1]
    print(f"\nBook 2, attempt #2: {start.date()} to {end.date()}, "
          f"costs ${VOL_OPTION_HALF_SPREAD}/option/side + {VOL_HEDGE_COST_BPS}bp hedge\n")
    table = pd.DataFrame({name: metrics(res) for name, res in results.items()})
    extra = pd.DataFrame({name: {"Worst day": f"{res['return'].min():.1%}",
                                 "Worst month": f"{((1 + res['return']).resample('M').prod() - 1).min():.1%}"}
                          for name, res in results.items()})
    table = pd.concat([table, extra]).rename(index={"Avg in risky assets": "Avg notional (% of book)"})
    print(table.drop(index=["Turnover / year"]).to_string())

    # Where did the money come from?
    print("\n--- P&L attribution (official, $ on a $100k start) ---")
    print(f"  Options (premium in, payouts/buy-backs out): ${official['option_pnl'].sum():>+12,.0f}")
    print(f"  Delta hedge (SPY shares + dividends):        ${official['hedge_pnl'].sum():>+12,.0f}")
    print(f"  Costs (option spreads + hedge trading):      ${-official['cost_usd'].sum():>+12,.0f}")

    # Monthly cycles: implied vol sold vs. volatility that actually happened.
    traded = cycles[cycles["how"].isin(["expiry", "VIX filter"])].copy()
    total = data["spy"] + data["dividend"].cumsum()  # rough total-return path for realized vol
    traded["realized"] = [realized_vol(total, a, b) for a, b in zip(traded["entry"], traded["exit"])]
    print("\n--- Monthly cycles ---")
    print(f"  Cycles traded: {len(traded)} | held to expiry: {(traded['how'] == 'expiry').sum()} | "
          f"closed by VIX filter: {(traded['how'] == 'VIX filter').sum()} | "
          f"skipped at entry (filter): {(cycles['how'] == 'skipped (VIX filter)').sum()}")
    print(f"  Avg implied vol sold: {traded['sold_vol'].mean():.1%} | avg realized while held: "
          f"{traded['realized'].mean():.1%} | sold above realized in {(traded['sold_vol'] > traded['realized']).mean():.0%} of cycles")
    print(f"  Avg size: {(traded['n'] / 100).mean():.2f} contracts per $100k of book equity at entry")

    print("\n--- By year (official) ---")
    r = official["return"]
    by_year = pd.DataFrame({
        "Return": ((1 + r).groupby(r.index.year).prod() - 1).map("{:+.1%}".format),
        "Worst day": r.groupby(r.index.year).min().map("{:.1%}".format),
        "SPY": ((1 + spy["return"]).groupby(spy.index.year).prod() - 1).map("{:+.1%}".format),
    })
    print(by_year.to_string())

    # The pass/fail bar, written down before this ran.
    sharpe = r.mean() / r.std() * np.sqrt(252)
    rs = stress["return"]
    stress_sharpe = rs.mean() / rs.std() * np.sqrt(252)
    worst = r.min()
    passed = sharpe >= 0.5 and stress_sharpe > 0 and worst >= -VOL_CRASH_LIMIT
    print(f"\nPre-set bar: Sharpe >= 0.5, positive with stress spreads, no day worse than -{VOL_CRASH_LIMIT:.0%}.")
    print(f"Result: Sharpe {sharpe:.2f}, stress Sharpe {stress_sharpe:.2f}, worst day {worst:.1%} -> "
          f"{'PASSES' if passed else 'DOES NOT PASS'}")

    RESULTS_DIR.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for name, res in results.items():
        ax.plot(res.index, res["equity"], label=name, ls="--" if "diagnostic" in name else "-")
    ax.set_yscale("log")
    ax.set_title("Book 2 attempt #2 (short delta-hedged SPY straddle): growth of $1, log scale")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    chart = RESULTS_DIR / "book2_vol_equity_curve.png"
    fig.savefig(chart, dpi=150)
    print(f"\nChart saved to {chart}")


if __name__ == "__main__":
    main()
