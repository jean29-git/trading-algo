"""
Connection test: proves the code can talk to your Alpaca PAPER account.

It only READS (account balance, market clock, latest SPY price).
It places no orders.

Run from the project folder:   python src/alpaca_check.py
"""

import os
from datetime import datetime, timedelta

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv

load_dotenv()  # reads the keys from the .env file into memory
KEY = os.getenv("ALPACA_API_KEY")
SECRET = os.getenv("ALPACA_SECRET_KEY")
if not KEY or "your_" in KEY:
    raise SystemExit("No keys found: paste your paper keys into the .env file first.")

# paper=True is the safety switch: orders can only ever go to fake money.
trading = TradingClient(KEY, SECRET, paper=True)
account = trading.get_account()
clock = trading.get_clock()

print("Connected to Alpaca PAPER account")
print(f"  Status:        {account.status}")
print(f"  Equity:        ${float(account.equity):,.2f}")
print(f"  Cash:          ${float(account.cash):,.2f}")
print(f"  Market open?   {clock.is_open}  (next open {clock.next_open:%a %d %b %H:%M})")

# Market data test: hourly SPY bars, the kind of data strategy 2 will use.
data = StockHistoricalDataClient(KEY, SECRET)
bars = data.get_stock_bars(StockBarsRequest(
    symbol_or_symbols="SPY",
    timeframe=TimeFrame.Hour,
    start=datetime.now() - timedelta(days=5),
    end=datetime.now() - timedelta(minutes=20),  # free data is delayed 15 min
)).df
print(f"\nLast 3 hourly SPY bars:\n{bars.tail(3)[['open', 'high', 'low', 'close', 'volume']]}")
