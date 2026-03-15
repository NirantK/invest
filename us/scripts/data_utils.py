"""Shared data fetching and caching for investment scripts."""

import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from functools import wraps
from pathlib import Path

import numpy as np
import yfinance as yf

CACHE_DIR = Path(__file__).parent.parent / "data" / "price_cache"


def daily_disk_cache(func):
    """Cache results to disk keyed by (args, today). Auto-stale after midnight."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        key = "__".join(str(a) for a in args)
        cache_file = CACHE_DIR / f"{func.__name__}__{key}__{today}.pkl"
        if cache_file.exists():
            return pickle.loads(cache_file.read_bytes())
        result = func(*args, **kwargs)
        if result is not None:
            cache_file.write_bytes(pickle.dumps(result))
        for f in CACHE_DIR.glob(f"{func.__name__}__*.pkl"):
            if not f.name.endswith(f"__{today}.pkl"):
                f.unlink(missing_ok=True)
        return result
    return wrapper


def build_total_return(close: np.ndarray, divs: np.ndarray) -> np.ndarray:
    """Build total return index from close prices and dividends."""
    tri = close.copy()
    cumulative_div_yield = 0.0
    for i in range(1, len(close)):
        if close[i - 1] != 0:
            div_yield = divs[i] / close[i - 1]
        else:
            div_yield = 0
        cumulative_div_yield = (1 + cumulative_div_yield) * (1 + div_yield) - 1
        tri[i] = close[i] * (1 + cumulative_div_yield)
    return tri


@daily_disk_cache
def fetch_one_dict(ticker: str, period: str) -> dict | None:
    """Fetch total return as numpy dict. Used by backtest."""
    hist = yf.Ticker(ticker).history(period=period)
    if hist.empty:
        return None
    tri = build_total_return(hist["Close"].values, hist["Dividends"].values)
    dates = np.array([d.strftime("%Y-%m-%d") for d in hist.index.to_pydatetime()])
    return {"dates": dates, "tri": tri}


def fetch_all_numpy(
    tickers: list[str], period: str = "5y"
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Fetch all tickers, align to common dates.

    Returns (prices[n_days, n_tickers], dates[n_days], tickers_fetched).
    NaN where data missing, forward-filled after first valid.
    """
    raw = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_one_dict, t, period): t for t in tickers}
        for future in as_completed(futures):
            t = futures[future]
            result = future.result()
            if result is not None and len(result["tri"]) > 0:
                raw[t] = result

    if not raw:
        return np.array([]), np.array([]), []

    all_dates = sorted(set().union(*(set(v["dates"]) for v in raw.values())))
    date_to_idx = {d: i for i, d in enumerate(all_dates)}
    fetched_tickers = sorted(raw.keys())

    prices = np.full((len(all_dates), len(fetched_tickers)), np.nan)
    for j, t in enumerate(fetched_tickers):
        indices = np.array([date_to_idx[d] for d in raw[t]["dates"]])
        prices[indices, j] = raw[t]["tri"]

    # Forward-fill NaNs (leave leading NaN for late-starting tickers)
    for j in range(prices.shape[1]):
        col = prices[:, j]
        mask = np.isnan(col)
        if mask.all():
            continue
        first_valid = np.argmax(~mask)
        # Vectorized forward fill using numpy
        valid_idx = np.where(~mask[first_valid:])[0] + first_valid
        if len(valid_idx) > 1:
            fill_idx = np.arange(first_valid, len(col))
            insert_points = np.searchsorted(valid_idx, fill_idx, side="right") - 1
            insert_points = np.clip(insert_points, 0, len(valid_idx) - 1)
            col[first_valid:] = col[valid_idx[insert_points]]

    return prices, np.array(all_dates), fetched_tickers


# ── Earnings momentum ────────────────────────────────────────────────────────


@daily_disk_cache
def fetch_earnings(ticker: str) -> dict | None:
    """Fetch quarterly Diluted EPS history. Returns {date_str: eps} or None."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        inc = yf.Ticker(ticker).quarterly_income_stmt
    if inc is None or inc.empty:
        return None
    eps_rows = [r for r in inc.index if "Diluted EPS" in r]
    if not eps_rows:
        return None
    eps = inc.loc[eps_rows[0]].dropna()
    if len(eps) < 2:
        return None
    # Return as {date_str: eps_value}, sorted chronologically
    result = {}
    for dt, val in sorted(zip(eps.index, eps.values)):
        result[dt.strftime("%Y-%m-%d")] = float(val)
    return result


def fetch_all_earnings(tickers: list[str]) -> dict[str, dict[str, float]]:
    """Fetch earnings for all tickers in parallel. Returns {ticker: {date: eps}}."""
    earnings = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_earnings, t): t for t in tickers}
        for future in as_completed(futures):
            t = futures[future]
            result = future.result()
            if result is not None:
                earnings[t] = result
    return earnings


def build_earnings_momentum(
    earnings: dict[str, dict[str, float]],
    dates: np.ndarray,
    tickers: list[str],
) -> np.ndarray:
    """Build earnings momentum matrix aligned to trading dates.

    Returns shape (n_days, n_tickers) with YoY EPS growth at each day.
    NaN where no earnings data available. Value is forward-filled from
    most recent earnings report until next report.
    """
    n_days = len(dates)
    n_tickers = len(tickers)
    earn_mom = np.full((n_days, n_tickers), np.nan)

    for j, t in enumerate(tickers):
        if t not in earnings:
            continue
        eps_data = earnings[t]
        eps_dates = sorted(eps_data.keys())
        if len(eps_dates) < 5:
            # Need at least 5 quarters for YoY comparison
            continue

        # Compute YoY growth for each quarter (compare to same quarter last year = 4 quarters ago)
        for i in range(4, len(eps_dates)):
            current_eps = eps_data[eps_dates[i]]
            prior_eps = eps_data[eps_dates[i - 4]]
            if abs(prior_eps) > 0.01:
                yoy_growth = (current_eps - prior_eps) / abs(prior_eps)
            else:
                # Near-zero prior EPS: use sign-based signal
                yoy_growth = 1.0 if current_eps > prior_eps else -1.0 if current_eps < prior_eps else 0.0

            # Find the date index for this earnings report and forward-fill
            report_date = eps_dates[i]
            next_report = eps_dates[i + 1] if i + 1 < len(eps_dates) else None

            start_idx = np.searchsorted(dates, report_date)
            end_idx = np.searchsorted(dates, next_report) if next_report else n_days
            earn_mom[start_idx:end_idx, j] = yoy_growth

    return earn_mom
