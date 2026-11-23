"""
Book 2: the backtest engine (intraday mean reversion).

Walks through every 15-minute bar in time order, like a trader watching
the screen. At each bar, in this order:

  1. FILL: buy orders decided at the previous bar's close fill at this
     bar's OPEN (never at the close that triggered them: no look-ahead).
  2. EXIT: for each open position, check the stop and the target during
     this bar, like resting orders sitting at the broker:
       - opens beyond the stop or target -> exit at the open (a gap fills worse)
       - both stop and target inside one bar -> assume the STOP came first
         (15-min bars can't say which came first, so take the worse case)
       - on the day's last bar (15:45), sell everything at its open
  3. SIGNAL: at this bar's close, look for new dips. If more ETFs signal
     than capital allows, fill the deepest dip first.

Costs are charged per side on every trade. Results are shown before costs,
after costs (2bp/side), and in a stress test (4bp/side).

Run from the project folder:   python src/book2_backtest.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # save charts to files, don't open windows
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from backtest import metrics
from book2_strategy import indicators, load_bars, trading_day
from config import BOOK2_BAR_MINUTES, BOOK2_COST_BPS, BOOK2_REGIME_DAYS, BOOK2_STOP_SIGMA

ROOT = Path(__file__).resolve().parent.parent
BARS_FILE = ROOT / "data" / "book2_bars_15min.csv"
TRADES_FILE = ROOT / "data" / "book2_trades.csv"
RESULTS_DIR = ROOT / "results"
MIN_ORDER = 0.01  # don't bother with orders smaller than 1% of the book


def simulate(bars: dict, ind: dict):
    """Run the rules bar by bar. Returns (list of trades, % of book invested at each bar)."""
    O, H, L, C = (bars[f].to_numpy() for f in ("open", "high", "low", "close"))
    MA, SD, Z = ind["ma"].to_numpy(), ind["sd"].to_numpy(), ind["z"].to_numpy()
    ENTRY, SIZE = ind["entry"].to_numpy(), ind["size"].to_numpy()
    pos, n = ind["pos"].to_numpy(), ind["n"].to_numpy()
    times, tickers = bars["close"].index, list(bars["close"].columns)

    positions = {}  # ETF column -> {entry bar, entry price, stop price, weight}
    pending = []    # buy orders waiting for the next bar's open
    trades, invested = [], np.zeros(len(times))

    for t in range(len(times)):
        # 1) FILL last bar's buy orders at this bar's open.
        for j, weight, sd in pending:
            if np.isnan(O[t, j]):
                continue  # no trading in this ETF during this bar: order cancelled
            price = O[t, j]
            positions[j] = {"t": t, "price": price, "weight": weight,
                            "stop": price - BOOK2_STOP_SIGMA * sd}  # stop frozen at entry
        pending = []
        invested[t] = sum(p["weight"] for p in positions.values())

        # 2) EXIT: stops, targets, and the end-of-day close-out.
        last_bar = pos[t] == n[t] - 1
        for j in list(positions):
            p = positions[j]
            exit_price, reason = None, None
            if last_bar:
                exit_price, reason = O[t, j], "end of day"
                if np.isnan(exit_price):  # no 15:45 bar: use the last price we saw
                    exit_price = C[:t, j][~np.isnan(C[:t, j])][-1]
            elif not np.isnan(O[t, j]):
                stop, target = p["stop"], MA[t - 1, j]  # target = average as of the last bar
                if O[t, j] <= stop:
                    exit_price, reason = O[t, j], "stop"
                elif O[t, j] >= target:
                    exit_price, reason = O[t, j], "target"
                elif L[t, j] <= stop:
                    exit_price, reason = stop, "stop"     # stop first if both are hit
                elif H[t, j] >= target:
                    exit_price, reason = target, "target"
            if reason:
                trades.append({"ticker": tickers[j], "entry_time": times[p["t"]],
                                "exit_time": times[t], "entry": p["price"], "exit": exit_price,
                                "weight": p["weight"], "reason": reason,
                                "minutes": (t - p["t"] + (reason != "end of day")) * BOOK2_BAR_MINUTES})
                del positions[j]

        # 3) SIGNAL: new dips at this bar's close, deepest first.
        if last_bar:
            continue
        candidates = [j for j in np.flatnonzero(ENTRY[t]) if j not in positions]
        room = 1.0 - sum(p["weight"] for p in positions.values())  # no leverage
        for j in sorted(candidates, key=lambda j: Z[t, j]):
            weight = min(SIZE[t, j], room)
            if weight < MIN_ORDER:
                break
            pending.append((j, weight, SD[t, j]))
            room -= weight

    trades = pd.DataFrame(trades)
    if len(trades):
        trades["return"] = trades["exit"] / trades["entry"] - 1  # on the position, before costs
    return trades, pd.Series(invested, index=times)


def daily_results(trades: pd.DataFrame, invested: pd.Series, days, cost_bps: float) -> pd.DataFrame:
    """Turn trades into one row per day: return after costs, turnover, cost, % invested.

    Book 2 is always flat at night, so each day's P&L is just the sum of
    that day's trades, each weighted by its share of the book.
    """
    day = trading_day(pd.DatetimeIndex(trades["exit_time"]))
    gross = (trades["weight"] * trades["return"]).groupby(day).sum().reindex(days, fill_value=0.0)
    turnover = (2 * trades["weight"]).groupby(day).sum().reindex(days, fill_value=0.0)  # buy + sell
    cost = turnover * cost_bps / 10_000
    risky = invested.groupby(trading_day(invested.index)).mean().reindex(days, fill_value=0.0)
    result = pd.DataFrame({"return": gross - cost, "turnover": turnover,
                           "cost": cost, "risky": risky}, index=days)
    result["equity"] = (1 + result["return"]).cumprod()
    return result


def trade_stats(trades: pd.DataFrame, n_days: int, cost_bps: float) -> pd.Series:
    """What a desk head asks about a short-term strategy: how often, how good, how it exits."""
    round_trip = 2 * cost_bps / 10_000
    net = trades["return"] - round_trip
    wins, losses = net[net > 0], net[net <= 0]
    reasons = trades["reason"].value_counts(normalize=True)
    return pd.Series({
        "Trades": f"{len(trades):,}",
        "Trades per day": f"{len(trades) / n_days:.1f}",
        "Avg position size": f"{trades['weight'].mean():.0%} of book",
        "Avg trade, before costs": f"{trades['return'].mean() * 1e4:+.1f}bp",
        "Round-trip cost": f"{round_trip * 1e4:.1f}bp",
        "Avg trade, after costs": f"{net.mean() * 1e4:+.1f}bp",
        "Win rate (after costs)": f"{len(wins) / len(net):.0%}",
        "Avg win / avg loss": f"{wins.mean() * 1e4:+.0f}bp / {losses.mean() * 1e4:+.0f}bp",
        "Exit: target / stop / end of day":
            f"{reasons.get('target', 0):.0%} / {reasons.get('stop', 0):.0%} / {reasons.get('end of day', 0):.0%}",
        "Avg holding time": f"{trades['minutes'].mean():.0f} min",
    })


def by_year(result: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """Is the edge steady, or did it all come from one year?"""
    r = result["return"]
    year = r.index.year
    trade_year = trading_day(pd.DatetimeIndex(trades["exit_time"])).year
    return pd.DataFrame({
        "Return": ((1 + r).groupby(year).prod() - 1).map("{:+.1%}".format),
        "Sharpe": (r.groupby(year).mean() / r.groupby(year).std() * np.sqrt(252)).map("{:.2f}".format),
        "Trades": trades.groupby(trade_year).size(),
    })


def by_etf(trades: pd.DataFrame, cost_bps: float) -> pd.DataFrame:
    """Which ETFs carry the strategy, and which ones cost us money?"""
    net = trades["return"] - 2 * cost_bps / 10_000
    g = trades.assign(net=net, pnl=net * trades["weight"]).groupby("ticker")
    return pd.DataFrame({
        "Trades": g.size(),
        "Avg trade after costs": (g["net"].mean() * 1e4).map("{:+.1f}bp".format),
        "Win rate": g["net"].apply(lambda x: (x > 0).mean()).map("{:.0%}".format),
        "Total P&L (% of book)": (g["pnl"].sum() * 100).map("{:+.1f}%".format),
    })


def main() -> None:
    print("Loading 15-minute bars...")
    bars = load_bars(BARS_FILE)

    # Start once the 200-day regime filter has a full history for every ETF.
    all_days = trading_day(bars["close"].index).unique()
    days = all_days[BOOK2_REGIME_DAYS + 1:]
    start = days[0]

    print("Running the backtest (official rules, with the 200-day filter)...")
    trades, invested = simulate(bars, indicators(bars, use_regime=True))
    trades = trades[trading_day(pd.DatetimeIndex(trades["exit_time"])) >= start]
    print("Running the diagnostic (no regime filter)...")
    trades_nf, invested_nf = simulate(bars, indicators(bars, use_regime=False))
    trades_nf = trades_nf[trading_day(pd.DatetimeIndex(trades_nf["exit_time"])) >= start]

    stress_bps = 2 * BOOK2_COST_BPS
    results = {
        "Before costs": daily_results(trades, invested, days, 0),
        f"After costs ({BOOK2_COST_BPS}bp)": daily_results(trades, invested, days, BOOK2_COST_BPS),
        f"Stress ({stress_bps}bp)": daily_results(trades, invested, days, stress_bps),
        "No filter, diagnostic": daily_results(trades_nf, invested_nf, days, BOOK2_COST_BPS),
    }
    official = results[f"After costs ({BOOK2_COST_BPS}bp)"]

    print(f"\nBook 2 backtest {start.date()} to {days[-1].date()} ({len(days):,} trading days)\n")
    table = pd.DataFrame({name: metrics(res) for name, res in results.items()})
    print(table.rename(index={"Avg in risky assets": "Avg % of book invested"}).to_string())

    print(f"\n--- Trades (official rules, {BOOK2_COST_BPS}bp per side) ---")
    print(trade_stats(trades, len(days), BOOK2_COST_BPS).to_string())
    print("\n--- By ETF ---")
    print(by_etf(trades, BOOK2_COST_BPS).to_string())
    print("\n--- By year (after costs) ---")
    print(by_year(official, trades).to_string())

    # The pass/fail bar written in docs/book2_design.md before any result.
    r_off, r_stress = official["return"], results[f"Stress ({stress_bps}bp)"]["return"]
    sharpe = r_off.mean() / r_off.std() * np.sqrt(252)
    stress_sharpe = r_stress.mean() / r_stress.std() * np.sqrt(252)
    passed = sharpe >= 0.5 and stress_sharpe > 0
    print(f"\nPre-set bar: Sharpe after costs >= 0.5 AND still positive at {stress_bps}bp.")
    print(f"Result: Sharpe {sharpe:.2f}, stress Sharpe {stress_sharpe:.2f} -> "
          f"{'PASSES' if passed else 'DOES NOT PASS'}")

    trades.to_csv(TRADES_FILE, index=False)
    RESULTS_DIR.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for name, res in results.items():
        ax.plot(res.index, res["equity"], label=name, ls="--" if "diagnostic" in name else "-")
    ax.axhline(1, color="grey", lw=0.8)
    ax.set_title("Book 2 (intraday mean reversion): growth of $1")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    chart = RESULTS_DIR / "book2_equity_curve.png"
    fig.savefig(chart, dpi=150)
    print(f"\nTrades saved to {TRADES_FILE}\nChart saved to {chart}")


if __name__ == "__main__":
    main()
