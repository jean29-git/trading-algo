"""
Book 1 live: trade the Alpaca PAPER account to this week's target weights.

What it does, in order:
  1. Download fresh daily prices (same source and same code as the backtest).
  2. Compute this week's target weights with strategy.target_weights(),
     the exact function the backtest uses, so live = backtest logic.
  3. Read the paper account: equity and current positions.
  4. Turn target weights into whole-share targets and list the orders needed.
  5. DRY RUN by default: print everything and send NOTHING.
     With --send, it asks you to type 'yes' before submitting any order.

Execution: run it on Friday afternoon, before 3:50pm New York time.
It then uses market-on-close (MOC) orders, which fill in the closing
auction at the official closing price. That is exactly the price the
backtest assumes we trade at, and the closing auction is the most
liquid moment of the day for ETFs. After 3:50pm Alpaca no longer accepts
MOC orders, so the script falls back to plain market orders (filled
right away if the market is open, or at the next open if it is closed).

Run from the project folder:
    python src/rebalance.py          # dry run: shows the orders, sends nothing
    python src/rebalance.py --send   # shows the orders, asks, then sends them
"""

import argparse
import csv
import math
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
from dotenv import load_dotenv

from config import CASH_TICKER, COST_BPS, LOOKBACK_DAYS, REBALANCE_DAY, UNIVERSE
from data import download_prices
from strategy import target_weights, volatility

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "live" / "orders_log.csv"
MOC_CUTOFF_MINUTES = 10  # Alpaca rejects market-on-close orders after 3:50pm ET
MAX_PRICE_AGE_DAYS = 4   # refuse to trade on prices older than this (stale data)


def connect() -> TradingClient:
    """Log in to the PAPER account with the keys stored in .env."""
    load_dotenv(ROOT / ".env")
    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    if not key or "your_" in key:
        raise SystemExit("No keys found: paste your paper keys into the .env file first.")
    return TradingClient(key, secret, paper=True)  # paper=True: fake money only


def todays_targets():
    """Fresh prices -> this week's target weights, plus the 'why' for each asset."""
    all_prices = download_prices()           # 8 ETFs + BIL, adjusted for dividends
    prices = all_prices[list(UNIVERSE)]      # the signal uses the 8 ETFs only, like the backtest

    # Safety check: never trade on old data.
    last_date = prices.index[-1]
    age = (pd.Timestamp.today().normalize() - last_date).days
    if age > MAX_PRICE_AGE_DAYS:
        raise SystemExit(f"Latest price is from {last_date.date()} ({age} days old). "
                         "Data looks stale, stopping without trading.")

    weights = target_weights(prices).iloc[-1]   # the last row = this week's targets
    latest = all_prices.iloc[-1]                # latest price of each ETF, for share counts
    if weights.isna().any() or latest.isna().any():
        raise SystemExit("A price or weight is missing for the latest day, stopping. "
                         "Try again in a few minutes.")

    # Not used for trading, only printed: the two inputs behind each weight.
    why = pd.DataFrame({
        "12m return": prices.iloc[-1] / prices.iloc[-1 - LOOKBACK_DAYS] - 1,  # trend signal input
        "Volatility": volatility(prices).iloc[-1],                            # sizing input
    })
    return weights, latest, why, last_date


def plan_orders(weights, prices, equity, positions) -> pd.DataFrame:
    """Target weight -> target number of shares -> order = target - what we hold."""
    rows = []
    for ticker, weight in weights.items():
        price = float(prices[ticker])
        # Round DOWN to whole shares: we can never spend more than the account
        # is worth, so no leverage sneaks in (the account allows 4x margin).
        target = math.floor(weight * equity / price)
        now = positions.get(ticker, 0.0)
        rows.append({"Ticker": ticker, "Weight": weight, "Price": price,
                     "Now": now, "Target": target, "Order": target - now})
    return pd.DataFrame(rows).set_index("Ticker")


def pick_order_type(clock):
    """Market-on-close if we're before the 3:50pm cut-off, else a plain market order."""
    minutes_left = (clock.next_close - clock.timestamp).total_seconds() / 60
    if clock.is_open and minutes_left > MOC_CUTOFF_MINUTES:
        return TimeInForce.CLS, "market-on-close (fills at today's official closing price)"
    if clock.is_open:
        return TimeInForce.DAY, "market order (past the MOC cut-off, fills right away)"
    return TimeInForce.DAY, f"market order (market closed, fills at next open {clock.next_open:%a %d %b %H:%M})"


def print_report(plan, why, equity, as_of, order_label):
    print(f"\nBook 1 rebalance | prices as of {as_of.date()} | "
          f"PAPER equity ${equity:,.2f}\n")
    print(f"{'Ticker':<6} {'12m ret':>8} {'Vol':>6} {'Trend':>6} {'Weight':>7} "
          f"{'Price':>9} {'Now':>6} {'Target':>7}   Order")
    for ticker, r in plan.iterrows():
        if ticker in why.index:
            ret, vol = why.loc[ticker, "12m return"], why.loc[ticker, "Volatility"]
            stats = f"{ret:>+8.1%} {vol:>6.1%} {'ON' if ret > 0 else 'off':>6}"
        else:
            stats = f"{'(cash: T-bills)':>22}"
        order = r["Order"]
        action = "-" if order == 0 else f"{'BUY' if order > 0 else 'SELL'} {abs(order):g}"
        print(f"{ticker:<6} {stats} {r['Weight']:>7.1%} {r['Price']:>9.2f} "
              f"{r['Now']:>6g} {r['Target']:>7g}   {action}")

    invested = (plan["Target"] * plan["Price"]).sum()
    traded = (plan["Order"].abs() * plan["Price"]).sum()
    risky = plan["Weight"].drop(CASH_TICKER).sum()
    print(f"\nIn risky assets: {risky:.1%} | In T-bills ({CASH_TICKER}): "
          f"{plan.loc[CASH_TICKER, 'Weight']:.1%} | "
          f"Cash left over from whole-share rounding: ${equity - invested:,.2f}")
    print(f"Value traded: ${traded:,.0f} | Est. cost at {COST_BPS}bp: ${traded * COST_BPS / 10_000:,.2f}")
    print(f"Order type: {order_label}")


def send_orders(client, plan, time_in_force):
    """Submit the orders, sells first, and keep a record of each one."""
    orders = plan[plan["Order"] != 0].sort_values("Order")  # negative = sells, so they go first
    LOG_FILE.parent.mkdir(exist_ok=True)
    new_file = not LOG_FILE.exists()
    with open(LOG_FILE, "a", newline="") as f:
        log = csv.writer(f)
        if new_file:
            log.writerow(["sent_at", "ticker", "side", "qty", "est_price",
                          "target_weight", "order_type", "order_id"])
        for ticker, r in orders.iterrows():
            side = OrderSide.BUY if r["Order"] > 0 else OrderSide.SELL
            qty = abs(r["Order"])
            order = client.submit_order(MarketOrderRequest(
                symbol=ticker, qty=qty, side=side, time_in_force=time_in_force))
            print(f"  sent {side.value.upper():<4} {qty:g} {ticker}  (status: {order.status.value})")
            log.writerow([datetime.now().isoformat(timespec="seconds"), ticker, side.value,
                          qty, round(r["Price"], 2), round(r["Weight"], 4),
                          time_in_force.value, order.id])
    print(f"\nOrders logged to {LOG_FILE}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebalance Book 1 on the Alpaca paper account.")
    parser.add_argument("--send", action="store_true",
                        help="submit the orders (you will be asked to confirm first)")
    args = parser.parse_args()

    client = connect()
    equity = float(client.get_account().equity)
    positions = {p.symbol: float(p.qty) for p in client.get_all_positions()}
    clock = client.get_clock()

    print("Downloading fresh prices...")
    weights, prices, why, as_of = todays_targets()
    plan = plan_orders(weights, prices, equity, positions)
    time_in_force, order_label = pick_order_type(clock)
    print_report(plan, why, equity, as_of, order_label)

    # Positions this book doesn't own: report them, never touch them.
    others = [s for s in positions if s not in plan.index]
    if others:
        print(f"\nNote: the account also holds {', '.join(others)}. Book 1 leaves those alone.")
    if datetime.now().weekday() != REBALANCE_DAY:
        print("\nNote: today is not Friday. The strategy rebalances on Fridays; "
              "trading on other days won't match the backtest.")

    if not args.send:
        print("\nDRY RUN: nothing was sent. To place these orders: python src/rebalance.py --send")
        return
    if plan["Order"].eq(0).all():
        print("\nAlready on target, nothing to trade.")
        return
    # Safety: if orders from an earlier run are still waiting, sending again would double them.
    if client.get_orders():
        raise SystemExit("\nThere are open orders waiting from an earlier run. "
                         "Check the Alpaca dashboard, then re-run once they've filled or been cancelled.")

    n = int(plan["Order"].ne(0).sum())
    if input(f"\nType 'yes' to send these {n} orders to your PAPER account: ").strip().lower() != "yes":
        print("Cancelled, nothing sent.")
        return
    send_orders(client, plan, time_in_force)


if __name__ == "__main__":
    main()
