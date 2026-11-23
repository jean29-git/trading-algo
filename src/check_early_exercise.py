"""
How wrong is Black-Scholes for the SPY options we trade?

SPY options are AMERICAN (exercisable any day); Black-Scholes prices
EUROPEAN options (exercise at expiry only). This script prices our
actual position, a short at-the-money straddle, both ways and reports
the gap ("early-exercise premium"):

  - at entry (about 30 days to expiry, strike = spot)
  - later in the month, after SPY has moved (one leg now in the money)
  - across calm (12%), normal (18%) and stressed (35%) volatility

Rates are set at 5%, near the top of the backtest period: higher rates
make early exercise of puts MORE valuable, so this is the unfavourable case.

Limitation: dividends are modelled as a continuous yield. Real SPY pays
quarterly, and calls can be worth exercising the day before an
ex-dividend date. That case is handled by a live trading rule (buy back
in-the-money calls before ex-dividend), not by the pricing model.

Run from the project folder:   python src/check_early_exercise.py
"""

from option_pricing import binomial_tree, black_scholes

K = 690.0       # strike: SPY was ~$690 when the straddle was sold
R, Q = 0.05, 0.012
STEPS = 1000


def straddle(S, T, sigma, american):
    if american:
        return sum(binomial_tree(S, K, T, R, Q, sigma, kind, True, STEPS) for kind in ("call", "put"))
    return sum(black_scholes(S, K, T, R, Q, sigma, kind) for kind in ("call", "put"))


def main() -> None:
    print("Short at-the-money SPY straddle, strike $690: European (Black-Scholes) vs American (tree)\n")
    print(f"{'Situation':<34} {'Vol':>4} {'European':>9} {'American':>9} {'Gap $':>7} {'Gap %':>7}")
    cases = [
        ("Entry: 30 days left, SPY $690", 690, 30),
        ("Mid-month: 15 days, SPY $690", 690, 15),
        ("After a 5% drop: 15 days, $655", 655.5, 15),
        ("After a 10% drop: 15 days, $621", 621, 15),
        ("After a 10% rally: 15 days, $759", 759, 15),
        ("Near expiry: 3 days, $621 (deep put)", 621, 3),
    ]
    worst = 0.0
    for label, S, days in cases:
        for sigma in (0.12, 0.18, 0.35):
            eu, am = straddle(S, days / 365, sigma, False), straddle(S, days / 365, sigma, True)
            gap = am - eu
            worst = max(worst, gap / eu)
            print(f"{label:<34} {sigma:>4.0%} {eu:>9.2f} {am:>9.2f} {gap:>7.3f} {gap / eu:>7.2%}")
        print()
    print(f"Largest gap: {worst:.2%} of the straddle's value.")


if __name__ == "__main__":
    main()
