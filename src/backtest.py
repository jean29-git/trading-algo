"""
Stage 2b: the backtest engine.

Simulates the strategy day by day, like a real account:
  - every day, the portfolio moves with the prices of what it holds
  - every Friday at the close, it looks at the signal and trades to
    the new target weights, paying COST_BPS on every dollar traded

Avoiding look-ahead bias: the weights decided on Friday use only prices
up to and including Friday's close, and they only earn returns from the
NEXT trading day onward. The strategy never uses information it couldn't
have had at the time.

Run from the project folder:   python src/backtest.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # save charts to files, don't open windows
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import COST_BPS, REBALANCE_DAY, UNIVERSE
from strategy import inverse_vol_weights, target_weights

ROOT = Path(__file__).resolve().parent.parent
PRICES_FILE = ROOT / "data" / "prices.csv"
RESULTS_DIR = ROOT / "results"


def run_backtest(prices: pd.DataFrame, weights: pd.DataFrame, start) -> pd.DataFrame:
    """Simulate holding `weights` (rebalanced weekly) and return daily results."""
    prices = prices.loc[start:]
    weights = weights.loc[start:]
    returns = prices.pct_change().fillna(0)
    cost_rate = COST_BPS / 10_000

    holdings = pd.Series(0.0, index=prices.columns)  # current weight in each asset
    rows = []
    for date in prices.index:
        # 1) Today's market move changes the value of what we hold.
        day_return = float((holdings * returns.loc[date]).sum())
        # Positions drift: winners grow as a share of the portfolio, losers shrink.
        grown = holdings * (1 + returns.loc[date])
        holdings = grown / (1 + day_return)

        # 2) On Fridays, trade to the new targets at the close.
        traded = 0.0
        if date.weekday() == REBALANCE_DAY:
            target = weights.loc[date].fillna(0)
            traded = float((target - holdings).abs().sum())  # fraction of portfolio traded
            holdings = target
        cost = traded * cost_rate

        rows.append({"date": date, "return": day_return - cost,
                     "turnover": traded, "cost": cost,
                     "invested": float(holdings.sum())})

    result = pd.DataFrame(rows).set_index("date")
    result["equity"] = (1 + result["return"]).cumprod()
    return result


def metrics(result: pd.DataFrame) -> dict:
    """Headline numbers a trader looks at first."""
    r = result["return"]
    years = len(r) / 252
    cagr = result["equity"].iloc[-1] ** (1 / years) - 1
    vol = r.std() * np.sqrt(252)
    drawdown = result["equity"] / result["equity"].cummax() - 1
    weekly = (1 + r).resample("W-FRI").prod() - 1
    return {
        "Annual return": f"{cagr:.1%}",
        "Volatility": f"{vol:.1%}",
        "Sharpe": f"{(r.mean() * 252) / vol:.2f}",
        "Max drawdown": f"{drawdown.min():.1%}",
        "Hit rate (weeks)": f"{(weekly > 0).mean():.0%}",
        "Turnover / year": f"{result['turnover'].sum() / years:.1f}x",
        "Costs / year": f"{result['cost'].sum() / years:.2%}",
        "Avg invested": f"{result['invested'].mean():.0%}",
    }


def main() -> None:
    prices = pd.read_csv(PRICES_FILE, index_col=0, parse_dates=True)[list(UNIVERSE)]

    strategy_w = target_weights(prices)
    # Start once every asset has a full signal + volatility history.
    start = strategy_w.dropna().index[0]

    # Benchmark 1: classic 60/40, 60% US stocks / 40% Treasuries.
    sixty_forty = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    sixty_forty["SPY"], sixty_forty["IEF"] = 0.6, 0.4
    # Benchmark 2: the SAME risk-parity basket, always fully invested.
    # Comparing against this isolates what the trend filter itself adds.
    always_in = inverse_vol_weights(prices)

    results = {
        "Trend strategy": run_backtest(prices, strategy_w, start),
        "60/40": run_backtest(prices, sixty_forty, start),
        "Risk parity, no trend filter": run_backtest(prices, always_in, start),
    }

    end = prices.index[-1]
    print(f"\nBacktest {start.date()} to {end.date()}, costs {COST_BPS}bp per trade\n")
    table = pd.DataFrame({name: metrics(res) for name, res in results.items()})
    print(table.to_string())

    RESULTS_DIR.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for name, res in results.items():
        ax.plot(res.index, res["equity"], label=name)
    ax.set_yscale("log")
    ax.set_title("Growth of $1 (log scale)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    chart = RESULTS_DIR / "equity_curve.png"
    fig.savefig(chart, dpi=150)
    print(f"\nChart saved to {chart}")


if __name__ == "__main__":
    main()
