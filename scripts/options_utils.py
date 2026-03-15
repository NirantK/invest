"""Black-Scholes options pricing for backtest overlay.

Simple, conservative options support:
- Protective PUTs on Core holdings (5% OTM, 90 DTE)
- Conviction CALLs on Max holdings (10% OTM, 90 DTE)
- Only buying options (defined risk, no naked selling)
"""

import numpy as np
from scipy.stats import norm


def black_scholes_call(
    S: float, K: float, T: float, r: float, sigma: float
) -> float:
    """European call price. T in years, sigma annualized."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(S - K, 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))


def black_scholes_put(
    S: float, K: float, T: float, r: float, sigma: float
) -> float:
    """European put price. T in years, sigma annualized."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(K - S, 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def delta_call(
    S: float, K: float, T: float, r: float, sigma: float
) -> float:
    """Call delta."""
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1))


def delta_put(
    S: float, K: float, T: float, r: float, sigma: float
) -> float:
    """Put delta."""
    return delta_call(S, K, T, r, sigma) - 1.0


def realized_vol(prices: np.ndarray, window: int = 90) -> float:
    """Annualized realized volatility from daily prices."""
    if len(prices) < window + 1:
        window = len(prices) - 1
    if window < 2:
        return 0.30  # default
    recent = prices[-window - 1:]
    with np.errstate(divide="ignore", invalid="ignore"):
        log_rets = np.diff(np.log(np.maximum(recent, 1e-10)))
    log_rets = log_rets[np.isfinite(log_rets)]
    if len(log_rets) < 2:
        return 0.30
    return float(np.std(log_rets, ddof=1) * np.sqrt(252))


def price_protective_put(
    stock_price: float,
    prices_history: np.ndarray,
    otm_pct: float = 0.05,
    dte: int = 90,
    risk_free: float = 0.05,
) -> dict:
    """Price a protective PUT for a stock position.

    Args:
        stock_price: Current stock price
        prices_history: Array of historical daily prices
        otm_pct: How far OTM (0.05 = 5% below current)
        dte: Days to expiration
        risk_free: Annual risk-free rate

    Returns:
        dict with strike, premium, cost_pct, delta, breakeven
    """
    sigma = realized_vol(prices_history)
    strike = round(stock_price * (1 - otm_pct), 2)
    T = dte / 365.0
    premium = black_scholes_put(stock_price, strike, T, risk_free, sigma)
    d = delta_put(stock_price, strike, T, risk_free, sigma)

    return {
        "type": "PUT",
        "strike": strike,
        "dte": dte,
        "premium": round(premium, 2),
        "cost_pct": premium / stock_price,
        "delta": round(d, 3),
        "sigma": round(sigma, 3),
        "breakeven": round(stock_price + premium, 2),
        "max_loss_protected": round(stock_price - strike - premium, 2),
    }


def price_conviction_call(
    stock_price: float,
    prices_history: np.ndarray,
    otm_pct: float = 0.10,
    dte: int = 90,
    risk_free: float = 0.05,
) -> dict:
    """Price a conviction CALL for leveraged upside.

    Args:
        stock_price: Current stock price
        prices_history: Array of historical daily prices
        otm_pct: How far OTM (0.10 = 10% above current)
        dte: Days to expiration
        risk_free: Annual risk-free rate

    Returns:
        dict with strike, premium, cost_pct, delta, leverage
    """
    sigma = realized_vol(prices_history)
    strike = round(stock_price * (1 + otm_pct), 2)
    T = dte / 365.0
    premium = black_scholes_call(stock_price, strike, T, risk_free, sigma)
    d = delta_call(stock_price, strike, T, risk_free, sigma)

    # Leverage = notional exposure / premium paid
    leverage = stock_price / premium if premium > 0 else 0

    return {
        "type": "CALL",
        "strike": strike,
        "dte": dte,
        "premium": round(premium, 2),
        "cost_pct": premium / stock_price,
        "delta": round(d, 3),
        "sigma": round(sigma, 3),
        "breakeven": round(strike + premium, 2),
        "leverage": round(leverage, 1),
    }


def options_overlay_for_portfolio(
    holdings: list[dict],
    prices: np.ndarray,
    fetched: list[str],
    bucket: str,
    put_budget_pct: float = 0.05,
    call_budget_pct: float = 0.10,
) -> list[dict]:
    """Generate options overlay for a portfolio bucket.

    Core bucket: protective PUTs on all holdings
    Max bucket: conviction CALLs on top holdings

    Args:
        holdings: list of {ticker, price, shares, value, score}
        prices: full price matrix (n_days, n_tickers)
        fetched: ticker name list
        bucket: "core" or "max"
        put_budget_pct: max % of position value for PUT premium
        call_budget_pct: max % of bucket capital for CALL premium

    Returns:
        list of option position dicts
    """
    option_positions = []
    ticker_to_idx = {t: i for i, t in enumerate(fetched)}

    for h in holdings:
        ticker = h["ticker"]
        idx = ticker_to_idx.get(ticker)
        if idx is None:
            continue

        px_history = prices[:, idx]
        valid = px_history[~np.isnan(px_history)]
        if len(valid) < 60:
            continue

        stock_price = h["price"]

        if bucket == "core":
            # Protective PUT: 5% OTM, 90 DTE
            put = price_protective_put(
                stock_price, valid, otm_pct=0.05, dte=90
            )
            # How many contracts? 1 contract = 100 shares
            # Buy enough to cover our position
            n_contracts = max(1, h["shares"] // 100)
            total_cost = put["premium"] * 100 * n_contracts

            # Cap at budget
            max_cost = h["value"] * put_budget_pct
            if total_cost > max_cost and n_contracts > 1:
                n_contracts = max(1, int(max_cost / (put["premium"] * 100)))
                total_cost = put["premium"] * 100 * n_contracts

            option_positions.append({
                **put,
                "ticker": ticker,
                "contracts": n_contracts,
                "total_cost": round(total_cost, 2),
                "shares_protected": n_contracts * 100,
                "bucket": "core",
            })

        elif bucket == "max":
            # Conviction CALL: 10% OTM, 90 DTE
            call = price_conviction_call(
                stock_price, valid, otm_pct=0.10, dte=90
            )
            # Buy 1-2 contracts for leveraged exposure
            n_contracts = 1
            total_cost = call["premium"] * 100 * n_contracts

            option_positions.append({
                **call,
                "ticker": ticker,
                "contracts": n_contracts,
                "total_cost": round(total_cost, 2),
                "notional_exposure": round(
                    stock_price * 100 * n_contracts, 2
                ),
                "bucket": "max",
            })

    return option_positions
