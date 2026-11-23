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


# ===========================================================================
# BOOK 2 (tactical): intraday mean reversion.
# Full rules and the reasoning behind each one: docs/book2_design.md,
# written and committed BEFORE any Book 2 data was downloaded.
# ===========================================================================

# The 10 most liquid US ETFs: tightest bid-ask spreads, which is what
# matters most when you trade several times a day.
BOOK2_UNIVERSE = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100 (large-cap tech)",
    "IWM": "Russell 2000 (US small caps)",
    "DIA": "Dow Jones 30",
    "XLF": "US financials sector",
    "XLE": "US energy sector",
    "XLK": "US technology sector",
    "TLT": "Long US Treasuries (20y+)",
    "GLD": "Gold",
    "EEM": "Emerging market equities",
}

BOOK2_START_DATE = "2016-01-01"  # Alpaca's historical stock data begins in 2016
BOOK2_BAR_MINUTES = 15           # one bar = 15 minutes; 26 bars in a full trading day

# Signal and exits (standard Bollinger Band values, fixed up front)
BOOK2_MA_BARS = 20         # moving average and standard deviation over the last 20 bars
BOOK2_ENTRY_SIGMA = 2.0    # buy when a bar closes 2 standard deviations below the average
BOOK2_STOP_SIGMA = 1.0     # stop-loss 1 standard deviation below the entry price
BOOK2_REGIME_DAYS = 200    # only trade an ETF whose last daily close is above its 200-day average

# Risk and costs
BOOK2_RISK_PER_TRADE = 0.005  # hitting the stop loses 0.5% of Book 2's capital
BOOK2_MAX_POSITION = 0.25     # never more than 25% of the book in one ETF
BOOK2_COST_BPS = 2            # cost per side (spread + slippage); stress test at 4bp
