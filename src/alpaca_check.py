"""
Connection test: proves the code can talk to your Alpaca PAPER account.

It only READS (account balance, market clock, latest SPY price).
It places no orders.

Each book has its own paper account (so positions and P&L never mix):
    python src/alpaca_check.py           # Book 1 account
    python src/alpaca_check.py --book2   # Book 2 account
"""

import os
import sys
from datetime import datetime, timedelta

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv

BOOK = "Book 2" if "--book2" in sys.argv else "Book 1"
PREFIX = "ALPACA_BOOK2_" if BOOK == "Book 2" else "ALPACA_"

load_dotenv()  # reads the keys from the .env file into memory
KEY = os.getenv(PREFIX + "API_KEY")
SECRET = os.getenv(PREFIX + "SECRET_KEY")
if not KEY or "your_" in KEY:
    raise SystemExit(f"No {BOOK} keys found: paste them into the .env file first.")

# paper=True is the safety switch: orders can only ever go to fake money.
trading = TradingClient(KEY, SECRET, paper=True)
account = trading.get_account()
clock = trading.get_clock()

print(f"Connected to Alpaca PAPER account for {BOOK}")
print(f"  Account:       {account.account_number}")
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
