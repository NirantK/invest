"""Shared data fetching and caching for investment scripts."""

import pickle
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from functools import wraps
from pathlib import Path

import httpx
import numpy as np
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

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
    """Build total return index from close prices and dividends.

    Vectorized: cumulative product of (1 + div_yield) applied to close prices.
    """
    shifted_close = np.roll(close, 1)
    shifted_close[0] = close[0]  # avoid div by zero on first element
    with np.errstate(divide="ignore", invalid="ignore"):
        div_yields = np.where(shifted_close != 0, divs / shifted_close, 0.0)
    div_yields[0] = 0.0  # no yield on first day
    cumulative_div_factor = np.cumprod(1 + div_yields)
    return close * cumulative_div_factor


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

    _forward_fill_columns(prices)
    return prices, np.array(all_dates), fetched_tickers


def _forward_fill_columns(prices: np.ndarray) -> None:
    """Forward-fill NaN values column-wise in place. Vectorized per-column."""
    for j in range(prices.shape[1]):
        col = prices[:, j]
        mask = np.isnan(col)
        if mask.all():
            continue
        first_valid = int(np.argmax(~mask))
        valid_idx = np.where(~mask[first_valid:])[0] + first_valid
        if len(valid_idx) > 1:
            fill_idx = np.arange(first_valid, len(col))
            insert_points = np.searchsorted(valid_idx, fill_idx, side="right") - 1
            insert_points = np.clip(insert_points, 0, len(valid_idx) - 1)
            col[first_valid:] = col[valid_idx[insert_points]]


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


# ── Indian Mutual Fund data (mfapi.in) ──────────────────────────────────────

MFAPI_BASE = "https://api.mfapi.in/mf"


def search_mf_schemes(query: str) -> list[dict]:
    """Search mfapi.in by name. Returns [{schemeCode, schemeName}, ...]."""
    resp = httpx.get(f"{MFAPI_BASE}/search", params={"q": query}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_all_mf_schemes() -> list[dict]:
    """Get all scheme codes from mfapi.in. Returns [{schemeCode, schemeName}, ...]."""
    resp = httpx.get(MFAPI_BASE, timeout=60)
    resp.raise_for_status()
    return resp.json()


MF_CACHE_DIR = Path(__file__).parent.parent / "data" / "mf_nav_cache"


def _load_mf_cache(scheme_code: int) -> dict | None:
    """Load cached MF NAV data. Returns {"dates": np.array, "tri": np.array} or None."""
    cache_file = MF_CACHE_DIR / f"{scheme_code}.pkl"
    if cache_file.exists():
        return pickle.loads(cache_file.read_bytes())
    return None


def _save_mf_cache(scheme_code: int, data: dict) -> None:
    """Save MF NAV data to incremental cache."""
    MF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = MF_CACHE_DIR / f"{scheme_code}.pkl"
    cache_file.write_bytes(pickle.dumps(data))


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError)),
    reraise=True,
)
def _mfapi_get(scheme_code: int) -> dict:
    """Single mfapi GET with tenacity exponential backoff."""
    resp = httpx.get(f"{MFAPI_BASE}/{scheme_code}", timeout=60)
    resp.raise_for_status()
    return resp.json()


def _fetch_mf_nav_incremental(scheme_code: int) -> dict | None:
    """Fetch MF NAV with incremental caching.

    If cached data exists, only fetches new data points after the last cached date.
    Merges new data with cached, saves back, returns full history.
    """
    cached = _load_mf_cache(scheme_code)
    last_cached_date = cached["dates"][-1] if cached else None

    try:
        data = _mfapi_get(scheme_code)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
        return cached  # all retries exhausted, fall back to stale cache
    nav_entries = data.get("data", [])
    if not nav_entries:
        return cached

    # Parse new entries
    parsed = []
    for entry in nav_entries:
        nav_str = entry.get("nav", "")
        date_str = entry.get("date", "")
        if not nav_str or not date_str:
            continue
        nav_val = float(nav_str)
        if nav_val <= 0:
            continue
        dt = datetime.strptime(date_str, "%d-%m-%Y")
        iso = dt.strftime("%Y-%m-%d")
        # Skip dates already in cache
        if last_cached_date and iso <= last_cached_date:
            continue
        parsed.append((iso, nav_val))

    if cached and not parsed:
        return cached  # no new data, return cache as-is

    # Merge with cached data
    if cached and parsed:
        parsed.sort(key=lambda x: x[0])
        new_dates = np.array([p[0] for p in parsed])
        new_navs = np.array([p[1] for p in parsed])
        merged_dates = np.concatenate([cached["dates"], new_dates])
        merged_navs = np.concatenate([cached["tri"], new_navs])
        result = {"dates": merged_dates, "tri": merged_navs}
    elif parsed:
        parsed.sort(key=lambda x: x[0])
        result = {
            "dates": np.array([p[0] for p in parsed]),
            "tri": np.array([p[1] for p in parsed]),
        }
    else:
        return None

    if len(result["tri"]) < 2:
        return None

    _save_mf_cache(scheme_code, result)
    return result


def fetch_all_mf_numpy(
    scheme_codes: list[int], period: str = "max"
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Fetch all MF schemes with incremental caching, align to common dates.

    Returns (prices[n_days, n_schemes], dates[n_days], scheme_labels).
    Fetches in batches of 50 to avoid overwhelming mfapi.in.
    """
    import time as _time
    raw = {}
    batch_size = 50
    total = len(scheme_codes)

    for batch_start in range(0, total, batch_size):
        batch = scheme_codes[batch_start:batch_start + batch_size]
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_fetch_mf_nav_incremental, sc): sc for sc in batch}
            for future in as_completed(futures):
                sc = futures[future]
                result = future.result()
                if result is not None and len(result["tri"]) > 0:
                    raw[str(sc)] = result
        done = min(batch_start + batch_size, total)
        if done < total:
            print(f"  Fetched {done}/{total} schemes ({len(raw)} valid)...")
            _time.sleep(0.5)  # brief pause between batches

    if not raw:
        return np.array([]), np.array([]), []

    all_dates = sorted(set().union(*(set(v["dates"]) for v in raw.values())))
    date_to_idx = {d: i for i, d in enumerate(all_dates)}
    fetched = sorted(raw.keys())

    prices = np.full((len(all_dates), len(fetched)), np.nan)
    for j, sc in enumerate(fetched):
        indices = np.array([date_to_idx[d] for d in raw[sc]["dates"]])
        prices[indices, j] = raw[sc]["tri"]

    _forward_fill_columns(prices)
    return prices, np.array(all_dates), fetched
