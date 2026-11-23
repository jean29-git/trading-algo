"""
Option pricing toolkit for Book 2 (volatility risk premium).

Four tools, each one you should be able to explain at a whiteboard:

1. black_scholes(): the price of a EUROPEAN call or put (exercise only at
   expiry), with a continuous dividend yield q because SPY pays dividends.
2. greeks(): how that price reacts to the market:
     delta = change in option price per $1 move in SPY  -> what we hedge
     gamma = change in delta per $1 move                -> why hedging costs us on big moves
     vega  = change in price per 1 vol point            -> our exposure to implied vol
     theta = change in price per day that passes        -> the time decay we collect
3. implied_vol(): runs Black-Scholes backwards: given a market price, which
   volatility makes the formula match it? This is how traders quote options.
4. binomial_tree(): Cox-Ross-Rubinstein tree. Handles AMERICAN options
   (exercise any day, like real SPY options) by checking at every node
   whether exercising now beats holding. Used to measure how wrong the
   European Black-Scholes formula is for the SPY options we trade.

Conventions: S = spot price, K = strike, T = years to expiry, r = interest
rate, q = dividend yield, sigma = volatility (0.20 = 20%), all annualised and
continuously compounded. kind = "call" or "put".
"""

import numpy as np
from scipy.optimize import brentq
from scipy.special import ndtr  # N(x): standard normal cumulative distribution

SQRT_2PI = np.sqrt(2 * np.pi)


def _n(x):
    """Standard normal density n(x) (the bell curve's height)."""
    return np.exp(-0.5 * x * x) / SQRT_2PI


def _d1_d2(S, K, T, r, q, sigma):
    vol_sqrt_t = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / vol_sqrt_t
    return d1, d1 - vol_sqrt_t


def intrinsic(S, K, kind):
    """What the option is worth if exercised right now."""
    return np.maximum(S - K, 0.0) if kind == "call" else np.maximum(K - S, 0.0)


def black_scholes(S, K, T, r, q, sigma, kind):
    """European option price.

    call = S·e^(-qT)·N(d1) - K·e^(-rT)·N(d2)
    put  = K·e^(-rT)·N(-d2) - S·e^(-qT)·N(-d1)
    """
    if T <= 0:
        return intrinsic(S, K, kind)
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    disc_s, disc_k = S * np.exp(-q * T), K * np.exp(-r * T)
    if kind == "call":
        return disc_s * ndtr(d1) - disc_k * ndtr(d2)
    return disc_k * ndtr(-d2) - disc_s * ndtr(-d1)


def greeks(S, K, T, r, q, sigma, kind) -> dict:
    """Delta, gamma, vega (per 1 vol point) and theta (per calendar day) of a European option."""
    if T <= 0:  # at expiry: delta is 0 or 1, everything else is gone
        itm = (S > K) if kind == "call" else (S < K)
        return {"delta": float(itm) * (1 if kind == "call" else -1),
                "gamma": 0.0, "vega": 0.0, "theta": 0.0}
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    eq, er = np.exp(-q * T), np.exp(-r * T)
    gamma = eq * _n(d1) / (S * sigma * np.sqrt(T))
    vega = S * eq * _n(d1) * np.sqrt(T) / 100          # per 1 vol point (e.g. 20% -> 21%)
    decay = -S * eq * _n(d1) * sigma / (2 * np.sqrt(T))  # the part of theta from time value
    if kind == "call":
        delta = eq * ndtr(d1)
        theta = decay - r * K * er * ndtr(d2) + q * S * eq * ndtr(d1)
    else:
        delta = -eq * ndtr(-d1)
        theta = decay + r * K * er * ndtr(-d2) - q * S * eq * ndtr(-d1)
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta / 365}


def implied_vol(price, S, K, T, r, q, kind, low=1e-4, high=5.0):
    """The volatility that makes Black-Scholes equal the market price (NaN if impossible)."""
    floor = black_scholes(S, K, T, r, q, low, kind)
    cap = black_scholes(S, K, T, r, q, high, kind)
    if not (floor <= price <= cap):
        return np.nan  # price below intrinsic value or absurdly high: no vol fits
    return brentq(lambda v: black_scholes(S, K, T, r, q, v, kind) - price, low, high, xtol=1e-8)


def binomial_tree(S, K, T, r, q, sigma, kind, american=True, steps=500):
    """Cox-Ross-Rubinstein binomial tree.

    Split [0, T] into `steps` small periods. In each one, the price goes up by
    u = e^(sigma·sqrt(dt)) or down by d = 1/u, with the 'risk-neutral'
    probability p = (e^((r-q)·dt) - d) / (u - d). Start from the payoffs at
    expiry and walk backwards: each node is worth the discounted average of its
    two children. For an American option, also check at every node whether
    exercising right now is worth more, and take the larger.
    """
    if T <= 0:
        return float(intrinsic(S, K, kind))
    dt = T / steps
    u = np.exp(sigma * np.sqrt(dt))
    d = 1 / u
    p = (np.exp((r - q) * dt) - d) / (u - d)
    disc = np.exp(-r * dt)

    j = np.arange(steps + 1)
    prices = S * u ** j * d ** (steps - j)       # all possible prices at expiry
    values = intrinsic(prices, K, kind)
    for step in range(steps - 1, -1, -1):
        j = np.arange(step + 1)
        prices = S * u ** j * d ** (step - j)
        values = disc * (p * values[1:] + (1 - p) * values[:-1])  # hold: discounted expectation
        if american:
            values = np.maximum(values, intrinsic(prices, K, kind))  # or exercise now
    return float(values[0])
