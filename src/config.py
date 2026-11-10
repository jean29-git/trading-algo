"""
Strategy settings, in one place so nothing is hidden inside the code.

The universe: 8 ETFs, each standing in for one macro asset class.
A trend-following fund trades futures on these markets; ETFs let us
do the same thing with a normal brokerage account.
"""

UNIVERSE = {
    # Equities
    "SPY": "US equities (S&P 500)",
    "EFA": "Developed ex-US equities (Europe, Japan)",
    "EEM": "Emerging market equities",
    # Rates / duration
    "TLT": "Long US Treasuries (20y+), a bet on falling long-end yields",
    "IEF": "Intermediate US Treasuries (7-10y)",
    # Real assets
    "GLD": "Gold",
    "DBC": "Broad commodities basket (energy, metals, ags)",
    # FX
    "UUP": "US dollar index (long USD vs EUR, JPY, GBP...)",
}

# Where idle cash sits: BIL holds 1-3 month US Treasury bills, so it earns
# roughly the Fed funds rate. Holding it (instead of plain cash) is also
# exactly what we will do live on Alpaca, so the backtest matches reality.
CASH_TICKER = "BIL"

# Backtest starts once every ETF has trading history (UUP launched Feb 2007).
START_DATE = "2007-03-01"

# ---------------------------------------------------------------------------
# Strategy parameters. Chosen ONCE, before looking at any results, using
# standard values from the trend-following literature. We do not tune them
# to make the backtest look better (that would be overfitting).
# ---------------------------------------------------------------------------

LOOKBACK_DAYS = 252   # trend signal: return over the past ~12 months (252 trading days)
VOL_DAYS = 60         # volatility estimate: past ~3 months of daily returns
REBALANCE_DAY = 4     # trade once a week, at Friday's close (Mon=0 ... Fri=4)

# Trading cost per dollar traded, covering bid-ask spread + slippage.
# Alpaca charges no commission, but you still cross the spread. Big ETFs
# like SPY trade at ~1bp spreads; DBC and UUP are wider. 5bp (0.05%) is a
# deliberately conservative average.
COST_BPS = 5
