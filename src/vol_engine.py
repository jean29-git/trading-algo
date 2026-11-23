"""
Book 2 (volatility risk premium): the straddle hedging simulator.

One short straddle, from the day we sell it to expiry:

  day 0      sell 1 call + 1 put (same strike), receive the premium;
             buy SPY shares equal to the straddle's delta, so the
             combined position has no view on direction
  each day   SPY moves; the shares make or lose money; dividends are
             paid on the shares; cash earns (or pays) interest;
             then re-hedge: trade shares to the new delta
  expiry     sell the remaining shares and pay what the straddle is
             worth: |SPY - strike|

All amounts are per share of underlying (one straddle on 1 share).
A real SPY contract covers 100 shares, so multiply by 100.

Works on many price paths at once (one row per path), which is what
the Monte Carlo check needs.
"""

import numpy as np

from option_pricing import black_scholes, greeks


def straddle_price(S, K, T, r, q, sigma):
    """Call + put, same strike: what we receive when we sell."""
    return black_scholes(S, K, T, r, q, sigma, "call") + black_scholes(S, K, T, r, q, sigma, "put")


def straddle_delta(S, K, T, r, q, sigma):
    """Call delta + put delta: how many shares we hold to be direction-neutral."""
    return greeks(S, K, T, r, q, sigma, "call")["delta"] + greeks(S, K, T, r, q, sigma, "put")["delta"]


def short_straddle_pnl(paths, K, T, sell_vol, r=0.0, q=0.0, hedge_vol=None, hedge_cost_bps=0.0) -> dict:
    """P&L of selling a straddle at `sell_vol` and delta-hedging at every step.

    paths:     SPY prices, shape (n_paths, n_steps + 1): entry close ... expiry close.
    T:         years to expiry at entry; one step = T / n_steps.
    sell_vol:  the implied vol the straddle is sold at.
    hedge_vol: the vol used to compute deltas. Default: the implied vol we sold at
               (all a real trader knows). Setting it to the TRUE vol is a
               textbook diagnostic: with continuous hedging the P&L would be
               exactly V(sold vol) - V(true vol). With once-a-day hedging some
               noise remains, std ≈ sqrt(pi/4) · vol · vega / sqrt(number of hedges)
               (Derman & Kamal).
    Returns each P&L component per path, so we can see where money comes from.
    """
    paths = np.atleast_2d(np.asarray(paths, dtype=float))
    n_steps = paths.shape[1] - 1
    dt = T / n_steps
    hedge_vol = sell_vol if hedge_vol is None else hedge_vol
    cost_rate = hedge_cost_bps / 10_000

    S = paths[:, 0]
    premium = straddle_price(S, K, T, r, q, sell_vol)
    shares = straddle_delta(S, K, T, r, q, hedge_vol)
    cash = premium - shares * S                       # premium in, shares bought with it
    hedge = np.zeros(len(S))                          # gains/losses on the shares (+ dividends)
    interest = np.zeros(len(S))
    costs = np.abs(shares) * S * cost_rate

    for t in range(1, n_steps + 1):
        S_prev, S = paths[:, t - 1], paths[:, t]
        hedge += shares * (S - S_prev) + shares * S_prev * q * dt   # price move + dividends on shares
        step_interest = cash * r * dt                               # cash balance earns/pays the rate
        interest += step_interest
        cash += step_interest
        if t < n_steps:                                             # re-hedge, except at expiry
            new_shares = straddle_delta(S, K, T - t * dt, r, q, hedge_vol)
            costs += np.abs(new_shares - shares) * S * cost_rate
            cash -= (new_shares - shares) * S
            shares = new_shares
    costs += np.abs(shares) * S * cost_rate          # sell the last shares at expiry
    payoff = np.abs(S - K)                           # what the straddle is worth at expiry

    return {"premium": premium, "payoff": payoff, "hedge": hedge, "interest": interest,
            "costs": costs, "pnl": premium - payoff + hedge + interest - costs}


def gbm_paths(S0, vol, T, n_steps, n_paths, drift=0.0, seed=0):
    """Simulated SPY prices: geometric Brownian motion (the Black-Scholes world).

    Each step: S_next = S · exp((drift - vol²/2)·dt + vol·sqrt(dt)·Z), Z ~ Normal(0, 1).
    Realized volatility is `vol` by construction, which is the point: we choose it.
    """
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    z = rng.standard_normal((n_paths, n_steps))
    log_steps = (drift - 0.5 * vol ** 2) * dt + vol * np.sqrt(dt) * z
    return S0 * np.exp(np.concatenate([np.zeros((n_paths, 1)), np.cumsum(log_steps, axis=1)], axis=1))
