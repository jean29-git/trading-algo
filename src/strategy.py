"""
Stage 2a: the trading signal and position sizing.

Two rules, both easy to say out loud in an interview:

1. TREND (direction): if an asset's price is higher than 12 months ago,
   hold it. If not, hold cash instead. Markets trend because investors
   under-react to news and big macro moves (a hiking cycle, a dollar rally,
   a commodity boom) play out over months, not days.

2. SIZE (risk): give each asset weight in proportion to 1 / its volatility.
   Without this, the stock and commodity ETFs (daily swings of 1-2%) would
   drown out the Treasury ETF IEF (~0.4%). Inverse-vol makes each asset
   contribute roughly the same risk. This is the 'risk parity' idea.

Long-only and no leverage: weights add up to at most 100%, and whatever
is switched off sits in cash.
"""

import numpy as np
import pandas as pd

from config import LOOKBACK_DAYS, VOL_DAYS


def trend_signal(prices: pd.DataFrame) -> pd.DataFrame:
    """1 if the asset is up over the lookback window, else 0."""
    past_return = prices / prices.shift(LOOKBACK_DAYS) - 1
    signal = (past_return > 0).astype(float)
    return signal.where(past_return.notna())  # no signal until we have 12m of history


def volatility(prices: pd.DataFrame) -> pd.DataFrame:
    """Annualised volatility from the last VOL_DAYS daily returns."""
    daily = prices.pct_change()
    return daily.rolling(VOL_DAYS).std() * np.sqrt(252)


def inverse_vol_weights(prices: pd.DataFrame) -> pd.DataFrame:
    """Risk-parity weights across ALL assets, summing to 100%."""
    inv = 1 / volatility(prices)
    return inv.div(inv.sum(axis=1), axis=0)


def target_weights(prices: pd.DataFrame) -> pd.DataFrame:
    """The strategy: risk-parity weights, but only for assets in an uptrend.

    Note we do NOT re-scale the remaining weights back up to 100%. If half
    the assets are in downtrends, the portfolio is ~half in cash. That is
    the defensive feature: in 2008 or 2022, most things fall and the
    strategy steps aside.
    """
    return inverse_vol_weights(prices) * trend_signal(prices)
