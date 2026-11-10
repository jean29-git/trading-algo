"""
Stage 1: data pipeline.

Downloads daily prices for every ETF in the universe, then runs quality
checks before anything else touches the data. Bad data is the most
common silent killer of backtests, so we look before we trust.

Run from the project folder:   python src/data.py
"""

from pathlib import Path

import pandas as pd
import yfinance as yf

from config import CASH_TICKER, UNIVERSE

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PRICES_FILE = DATA_DIR / "prices.csv"


def download_prices() -> pd.DataFrame:
    """Download adjusted close prices: one column per ticker, one row per day.

    'Adjusted' means dividends and splits are folded into the price.
    That matters a lot here: TLT pays a monthly coupon. Using raw prices
    would understate bond returns and make the backtest wrong.
    """
    tickers = list(UNIVERSE) + [CASH_TICKER]
    raw = yf.download(tickers, start="2000-01-01", auto_adjust=True, progress=False)
    prices = raw["Close"][tickers]  # keep our column order
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    return prices


def quality_report(prices: pd.DataFrame) -> None:
    """Print the checks a trader would want before trusting the numbers."""
    print("\n=== Data quality report ===")
    print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}"
          f"  ({len(prices):,} trading days)\n")

    print(f"{'Ticker':<6} {'First date':<12} {'Missing':>8} {'Worst day':>10} {'Best day':>9}")
    returns = prices.pct_change()
    for t in prices.columns:
        col = prices[t]
        first = col.first_valid_index()
        # Gaps after the ETF existed = days with no price (a data problem).
        missing = col.loc[first:].isna().sum()
        r = returns[t].dropna()
        print(f"{t:<6} {str(first.date()):<12} {missing:>8} {r.min():>9.1%} {r.max():>9.1%}")

    # Daily moves above 15% on diversified ETFs usually mean a bad print,
    # not a real move, so flag them for a manual look.
    big = returns[returns.abs() > 0.15].stack()
    if big.empty:
        print("\nNo suspicious daily moves (>15%).")
    else:
        print("\nDaily moves above 15%, check these are real:")
        for (date, t), r in big.items():
            print(f"  {date.date()}  {t}  {r:+.1%}")


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    print(f"Downloading {len(UNIVERSE)} ETFs...")
    prices = download_prices()
    prices.to_csv(PRICES_FILE)
    print(f"Saved to {PRICES_FILE}")
    quality_report(prices)


if __name__ == "__main__":
    main()
