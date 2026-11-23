"""
Reality check: how do REAL SPY option prices compare with the VIX?

The backtest has to price options from the VIX, because free historical
option prices only start in February 2024. But the VIX is not exactly the
implied vol of the at-the-money SPY straddle we sell: it is built from a
whole strip of SPX options, including expensive out-of-the-money puts
(the "skew"), so it usually sits a bit higher. Selling "at the VIX" would
flatter the backtest.

So, for every trading day since February 2024:
  1. take the monthly SPY expiry closest to 30 days out, and the strike
     nearest SPY's close (the straddle we would actually sell)
  2. get the real closing prices of that call and put from Alpaca
  3. find the implied vol that makes our AMERICAN pricer (binomial tree)
     match the real straddle price
  4. compare with the VIX that day: gap = VIX - real implied vol

The median gap becomes the haircut h in the backtest (VIX - h), fixed
BEFORE the strategy backtest runs (docs/book2_attempt2_vol_premium.md).

Also takes a snapshot of today's real bid-ask spreads on at-the-money
options (Alpaca has no historical option quotes).

Run from the project folder:   python src/check_real_options.py
"""

import os
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from alpaca.data.enums import DataFeed, OptionsFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionBarsRequest, OptionChainRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv
from scipy.optimize import brentq

from option_pricing import binomial_tree
from vol_engine import monthly_expiries

ROOT = Path(__file__).resolve().parent.parent
VOL_DATA_FILE = ROOT / "data" / "vol_data.csv"
OUT_FILE = ROOT / "data" / "real_vs_vix.csv"
FIRST_DAY = "2024-02-01"     # Alpaca's option history starts in February 2024
TREE_STEPS = 200             # enough for cent-level accuracy, fast enough for ~700 days
MIN_TRADES = 20              # skip days where either leg barely traded (stale price)


def occ_symbol(expiry, strike, kind) -> str:
    """Standard option symbol, e.g. SPY241220C00590000 = SPY, 20 Dec 2024, call, $590."""
    return f"SPY{expiry:%y%m%d}{'C' if kind == 'call' else 'P'}{int(round(strike * 1000)):08d}"


def american_straddle_iv(price, S, K, T, r, q):
    """Implied vol that makes the American tree's straddle value equal the real price."""
    f = lambda v: (binomial_tree(S, K, T, r, q, v, "call", True, TREE_STEPS)  # noqa: E731
                   + binomial_tree(S, K, T, r, q, v, "put", True, TREE_STEPS) - price)
    try:
        return brentq(f, 0.02, 2.0, xtol=1e-5)
    except ValueError:
        return np.nan  # no vol fits (bad print)


def main() -> None:
    load_dotenv(ROOT / ".env")
    client = OptionHistoricalDataClient(os.getenv("ALPACA_BOOK2_API_KEY"), os.getenv("ALPACA_BOOK2_SECRET_KEY"))
    data = pd.read_csv(VOL_DATA_FILE, index_col=0, parse_dates=True)
    days = data.loc[FIRST_DAY:].index
    expiries = monthly_expiries(data.index[data.index >= "2024-01-01"], days[-1] + timedelta(days=70))

    # 1) Which straddle would we sell each day? Expiry closest to 30 days out, strike nearest spot.
    plan = []
    for d in days:
        exp = min((e for e in expiries if (e - d).days >= 14), key=lambda e: abs((e - d).days - 30))
        plan.append({"date": d, "expiry": exp, "strike": float(round(data.at[d, "spy"]))})
    plan = pd.DataFrame(plan)

    # 2) Fetch the real daily bars, one request per expiry (all the strikes we need).
    print(f"Fetching real option prices for {len(plan)} days, {plan['expiry'].nunique()} expiries...")
    bars = []
    for exp, group in plan.groupby("expiry"):
        symbols = sorted({occ_symbol(exp, k, kind) for k in group["strike"] for kind in ("call", "put")})
        resp = client.get_option_bars(OptionBarsRequest(
            symbol_or_symbols=symbols, timeframe=TimeFrame.Day,
            start=group["date"].min().to_pydatetime(), end=(group["date"].max() + timedelta(days=1)).to_pydatetime()))
        if len(resp.df):
            bars.append(resp.df.reset_index())
    bars = pd.concat(bars)
    bars["date"] = bars["timestamp"].dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    bars = bars.set_index(["symbol", "date"])

    # 3) Real straddle price -> American implied vol, day by day.
    rows = []
    for _, p in plan.iterrows():
        d, exp, K = p["date"], p["expiry"], p["strike"]
        call, put = occ_symbol(exp, K, "call"), occ_symbol(exp, K, "put")
        if (call, d) not in bars.index or (put, d) not in bars.index:
            continue
        c, pt = bars.loc[(call, d)], bars.loc[(put, d)]
        if min(c["trade_count"], pt["trade_count"]) < MIN_TRADES:
            continue
        S, T = data.at[d, "spy"], (exp - d).days / 365
        iv = american_straddle_iv(c["close"] + pt["close"], S, K, T, data.at[d, "r"], data.at[d, "q"])
        rows.append({"date": d, "days_to_expiry": (exp - d).days, "spy": S, "strike": K,
                     "straddle": c["close"] + pt["close"], "real_iv": iv, "vix": data.at[d, "vix"] / 100})
    res = pd.DataFrame(rows).dropna().set_index("date")
    res["gap"] = res["vix"] - res["real_iv"]
    res.to_csv(OUT_FILE)

    g = res["gap"] * 100  # in vol points
    print(f"\nDays measured: {len(res)} of {len(plan)} ({res.index[0].date()} to {res.index[-1].date()})")
    print(f"VIX minus real at-the-money implied vol, in vol points:")
    print(f"  median {g.median():+.2f} | mean {g.mean():+.2f} | 25th pct {g.quantile(.25):+.2f} | "
          f"75th pct {g.quantile(.75):+.2f} | VIX higher on {(g > 0).mean():.0%} of days")
    buckets = pd.cut(res["vix"] * 100, [0, 15, 20, 30, 100], labels=["VIX<15", "15-20", "20-30", "30+"])
    print("\nBy VIX level (median gap, vol points, and number of days):")
    print(g.groupby(buckets, observed=True).agg(["median", "count"]).round(2).to_string())
    # The gap grows with the VIX, so compare a fixed haircut with a proportional one.
    ratio = (res["real_iv"] / res["vix"]).median()
    print(f"\nReal at-the-money vol / VIX: median {ratio:.3f}")
    print(f"{'Haircut method':<22} {'Median abs error':>17} {'Avg error, VIX>25':>18}")
    for name, pred in [(f"VIX - {g.median():.2f} (fixed)", res["vix"] - g.median() / 100),
                       (f"VIX x {ratio:.3f} (scaled)", res["vix"] * ratio)]:
        err = (pred - res["real_iv"]) * 100
        print(f"{name:<22} {err.abs().median():>14.2f} pt {err[res['vix'] > 0.25].mean():>+15.2f} pt")

    # 4) Today's real bid-ask spreads on near-the-money options, next two monthly expiries.
    print("\nToday's real bid-ask spreads, strikes within $5 of SPY, next two monthly expiries:")
    # Centre on SPY's LIVE price (not yesterday's close: SPY can move a lot in a day).
    stocks = StockHistoricalDataClient(os.getenv("ALPACA_BOOK2_API_KEY"), os.getenv("ALPACA_BOOK2_SECRET_KEY"))
    spot = stocks.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols="SPY", feed=DataFeed.IEX))["SPY"].price
    print(f"  SPY live price: ${spot:.2f}")
    upcoming = [e for e in expiries if e.date() > date.today()][:2]
    halves = []
    for exp in upcoming:
        chain = client.get_option_chain(OptionChainRequest(
            underlying_symbol="SPY", expiration_date=exp.date(), feed=OptionsFeed.INDICATIVE,
            strike_price_gte=spot - 5, strike_price_lte=spot + 5))
        for sym, snap in chain.items():
            qt = snap.latest_quote
            if qt and qt.ask_price and qt.bid_price and qt.ask_price > qt.bid_price:
                halves.append((qt.ask_price - qt.bid_price) / 2)
    if halves:
        h = pd.Series(halves)
        print(f"  {len(h)} contracts: half-spread median ${h.median():.3f}, max ${h.max():.3f} "
              f"(we assume $0.05, stress test $0.10)")
    print(f"\nSaved day-by-day comparison to {OUT_FILE}")


if __name__ == "__main__":
    main()
