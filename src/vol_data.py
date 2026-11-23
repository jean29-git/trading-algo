"""
Book 2 (volatility risk premium), stage 1: market data.

Downloads, from Yahoo Finance (free):
  SPY     the ACTUAL closing price, NOT dividend-adjusted. Option strikes are
          set on the real traded price, and that price drops on ex-dividend
          days, so adjusting it (like Book 1 does) would be wrong here.
  ^VIX    30-day implied vol of the S&P 500, from SPX options: our vol input
  ^VIX3M  3-month implied vol: VIX vs VIX3M is the term-structure filter
  ^IRX    13-week T-bill yield: the interest rate r in Black-Scholes
  SPY dividends, to get the dividend yield q

Then runs quality checks and saves one table, one row per trading day.

Run from the project folder:   python src/vol_data.py
"""

from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
VOL_DATA_FILE = ROOT / "data" / "vol_data.csv"
TICKERS = {"SPY": "spy", "^VIX": "vix", "^VIX3M": "vix3m", "^IRX": "irx"}


def download() -> pd.DataFrame:
    raw = yf.download(list(TICKERS), start="2000-01-01", auto_adjust=False, progress=False)
    data = raw["Close"][list(TICKERS)].rename(columns=TICKERS)  # 'Close' = not dividend-adjusted
    data.index = pd.to_datetime(data.index).tz_localize(None)
    data = data.dropna(subset=["spy"])                           # keep SPY trading days only
    # During market hours Yahoo adds a row for TODAY with live prices: that is not
    # a closing price, so keep completed days only.
    data = data[data.index < pd.Timestamp.today().normalize()]

    # Dividends: cash paid per share on each ex-dividend date.
    divs = yf.Ticker("SPY").dividends
    divs.index = pd.to_datetime(divs.index).tz_localize(None).normalize()
    data["dividend"] = divs.reindex(data.index).fillna(0.0)

    # q: dividends paid over the last 12 months / today's price (trailing yield).
    trailing = data["dividend"].rolling("365D").sum()
    data["q"] = trailing / data["spy"]
    # r: the T-bill yield is quoted in percent (4.2 = 4.2%).
    data["r"] = data["irx"].ffill() / 100
    return data


def quality_report(data: pd.DataFrame) -> None:
    print("\n=== Volatility book data quality report ===")
    print(f"{'Series':<9} {'First day':<11} {'Missing':>8} {'Min':>8} {'Max':>8}")
    for col in ("spy", "vix", "vix3m", "irx", "q"):
        s = data[col]
        first = s.first_valid_index()
        missing = int(s.loc[first:].isna().sum())
        print(f"{col:<9} {str(first.date()):<11} {missing:>8} {s.min():>8.3f} {s.max():>8.3f}")

    start = data[["vix", "vix3m"]].dropna().index[0]
    print(f"\nAll series available from {start.date()} -> backtest can start there.")
    both = data.loc[start:, ["vix", "vix3m"]].dropna()
    inverted = (both["vix"] >= both["vix3m"]).mean()
    print(f"Days with VIX >= VIX3M (filter says 'stressed'): {inverted:.1%}")
    print(f"Dividends found: {(data['dividend'] > 0).sum()} payments; "
          f"latest trailing yield {data['q'].iloc[-1]:.2%}")

    # Moves big enough to double-check by hand.
    spy_ret = data["spy"].pct_change()
    flags = [f"  SPY {r:+.1%} on {d.date()}" for d, r in spy_ret[spy_ret.abs() > 0.07].items()]
    vix_chg = data["vix"].pct_change()
    flags += [f"  VIX {r:+.0%} on {d.date()}" for d, r in vix_chg[vix_chg > 0.5].items()]
    print("\nBig moves to check are real:" if flags else "\nNo extreme moves flagged.")
    print("\n".join(flags))


def main() -> None:
    data = download()
    VOL_DATA_FILE.parent.mkdir(exist_ok=True)
    data.to_csv(VOL_DATA_FILE)
    print(f"Saved {len(data):,} days to {VOL_DATA_FILE}")
    quality_report(data)


if __name__ == "__main__":
    main()
