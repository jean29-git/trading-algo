"""
Book 2, stage 1: intraday data pipeline.

Downloads 15-minute bars for the 10 Book 2 ETFs from Alpaca, keeps only
regular trading hours, and runs quality checks before anything else
touches the data.

Two details that matter for a trader:
  - Regular hours only. Alpaca also returns pre-market and after-hours
    bars, where volume is thin and spreads are wide. Dips there are not
    the kind we want to buy, so we drop them.
  - We use the official exchange calendar for each day's open and close,
    so half days (e.g. the day after Thanksgiving, closing at 1pm) and
    holidays are handled correctly instead of assuming 9:30-16:00 always.

Run from the project folder:   python src/book2_data.py
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetCalendarRequest
from dotenv import load_dotenv

from config import BOOK2_BAR_MINUTES, BOOK2_START_DATE, BOOK2_UNIVERSE

ROOT = Path(__file__).resolve().parent.parent
BARS_FILE = ROOT / "data" / "book2_bars_15min.csv"
NY = "America/New_York"


def connect():
    """Log in with the Book 2 paper keys from .env (data access only, no orders here)."""
    load_dotenv(ROOT / ".env")
    key, secret = os.getenv("ALPACA_BOOK2_API_KEY"), os.getenv("ALPACA_BOOK2_SECRET_KEY")
    if not key or "your_" in key:
        raise SystemExit("No Book 2 keys found: paste them into the .env file first.")
    return StockHistoricalDataClient(key, secret), TradingClient(key, secret, paper=True)


def trading_sessions(trading: TradingClient, start, end) -> pd.DataFrame:
    """The exchange calendar: one row per trading day, with its real open and close time."""
    days = trading.get_calendar(GetCalendarRequest(start=start, end=end))
    sessions = pd.DataFrame({
        "date": [pd.Timestamp(d.date) for d in days],
        "open": [pd.Timestamp(d.open) for d in days],
        "close": [pd.Timestamp(d.close) for d in days],
    })
    for col in ("open", "close"):  # Alpaca gives New York local times
        if sessions[col].dt.tz is None:
            sessions[col] = sessions[col].dt.tz_localize(NY)
    sessions["expected_bars"] = ((sessions["close"] - sessions["open"])
                                 / pd.Timedelta(minutes=BOOK2_BAR_MINUTES)).astype(int)
    return sessions.set_index("date")


def download_bars(data: StockHistoricalDataClient, ticker: str, start, end) -> pd.DataFrame:
    """All 15-minute bars for one ETF, timestamps in New York time.

    feed=SIP: the consolidated tape (every US exchange). The free default
    (IEX) is one exchange with ~2% of volume, so its highs and lows would
    miss real moves.
    adjustment=ALL: splits and dividends folded into past prices, like Book 1.
    """
    bars = data.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame(BOOK2_BAR_MINUTES, TimeFrameUnit.Minute),
        start=start,
        end=end,
        adjustment=Adjustment.ALL,
        feed=DataFeed.SIP,
    )).df.reset_index()
    bars["timestamp"] = bars["timestamp"].dt.tz_convert(NY)  # bar START time, New York
    return bars[["symbol", "timestamp", "open", "high", "low", "close", "volume"]]


def regular_hours_only(bars: pd.DataFrame, sessions: pd.DataFrame) -> pd.DataFrame:
    """Keep a bar only if it starts at/after that day's open and before that day's close."""
    day = bars["timestamp"].dt.tz_localize(None).dt.normalize()
    open_, close = day.map(sessions["open"]), day.map(sessions["close"])
    keep = (bars["timestamp"] >= open_) & (bars["timestamp"] < close)  # NaN (not a session) -> dropped
    return bars[keep.fillna(False).astype(bool)]


def quality_report(bars: pd.DataFrame, sessions: pd.DataFrame) -> None:
    """The checks a trader would want before trusting intraday numbers."""
    print("\n=== Book 2 data quality report (regular hours only) ===")
    print(f"{'Ticker':<6} {'First day':<11} {'Days':>5} {'Bars':>8} {'Missing':>8} "
          f"{'Full days':>9} {'Worst bar':>10} {'Best bar':>9}")

    flags = []
    for ticker, b in bars.groupby("symbol"):
        b = b.sort_values("timestamp")
        day = b["timestamp"].dt.tz_localize(None).dt.normalize()
        days = sessions.loc[day.min():day.max()]
        per_day = day.value_counts().reindex(days.index, fill_value=0)
        missing = int((days["expected_bars"] - per_day).clip(lower=0).sum())
        full = (per_day >= days["expected_bars"]).mean()

        # 15-minute returns WITHIN each day (the overnight gap is not a 15-min move).
        ret = b.groupby(day)["close"].pct_change()
        print(f"{ticker:<6} {str(day.min().date()):<11} {len(days):>5} {len(b):>8,} {missing:>8,} "
              f"{full:>9.1%} {ret.min():>10.2%} {ret.max():>9.2%}")

        # Impossible bars (bad prints): high below low, or close outside the bar's range.
        bad = b[(b["high"] < b["low"]) | (b["close"] > b["high"]) | (b["close"] < b["low"])]
        if len(bad):
            flags.append(f"{ticker}: {len(bad)} bars with impossible high/low/close")
        # A 15-minute move above 5% in a big ETF is rare: list them to check by hand.
        for ts, r in ret[ret.abs() > 0.05].items():
            flags.append(f"{ticker}: {r:+.1%} in the 15-min bar starting {b.loc[ts, 'timestamp']:%Y-%m-%d %H:%M}")

    print(f"\nTrading days in calendar: {len(sessions):,} "
          f"(of which half days: {(sessions['expected_bars'] < 26).sum()})")
    print("\nThings to check by hand:" if flags else "\nNo impossible bars, no 15-min moves above 5%.")
    for f in flags:
        print("  " + f)


def main() -> None:
    data, trading = connect()
    start = datetime.fromisoformat(BOOK2_START_DATE)
    end = datetime.now() - timedelta(minutes=20)  # free plan: SIP data is delayed 15 min

    sessions = trading_sessions(trading, start.date(), end.date())
    frames = []
    for ticker in BOOK2_UNIVERSE:
        print(f"Downloading {ticker}...", flush=True)
        frames.append(regular_hours_only(download_bars(data, ticker, start, end), sessions))
    bars = pd.concat(frames, ignore_index=True)

    BARS_FILE.parent.mkdir(exist_ok=True)
    bars.to_csv(BARS_FILE, index=False)
    print(f"Saved {len(bars):,} bars to {BARS_FILE}")
    quality_report(bars, sessions)


if __name__ == "__main__":
    main()
