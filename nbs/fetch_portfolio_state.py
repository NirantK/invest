"""
Fetch current portfolio state using financialdatasets.ai API.
Outputs price comparison and momentum data for all portfolio tickers.
Falls back to yfinance for ETFs not covered by financialdatasets.ai.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

import requests
import yfinance as yf
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

API_KEY = os.getenv("FINANCIAL_DATASETS_API_KEY")
BASE_URL = "https://api.financialdatasets.ai"

# Portfolio tickers
TICKERS = ["PAAS", "HL", "AEM", "WPM", "FNV", "XOM", "SU", "AVDV", "DFIV", "IVAL", "MSTR"]

# Reference prices from Dec 31, 2025
REFERENCE_PRICES = {
    "PAAS": 54.89,
    "HL": 19.50,
    "AEM": 182.04,
    "WPM": 120.90,
    "FNV": 213.11,
    "XOM": 134.09,
    "SU": 49.97,
    "AVDV": 105.53,
    "DFIV": 56.13,
    "IVAL": 35.62,
    "MSTR": 151.95,
}

HEADERS = {"X-API-KEY": API_KEY}


def fetch_snapshot(ticker: str) -> dict | None:
    """Fetch current price snapshot for a ticker."""
    url = f"{BASE_URL}/prices/snapshot?ticker={ticker}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json().get("snapshot")
    print(f"Error fetching snapshot for {ticker}: {response.status_code}")
    return None


def fetch_historical_prices(ticker: str, start_date: str, end_date: str) -> list:
    """Fetch historical daily prices for a ticker."""
    url = f"{BASE_URL}/prices?ticker={ticker}&interval=day&interval_multiplier=1&start_date={start_date}&end_date={end_date}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json().get("prices", [])
    print(f"Error fetching historical prices for {ticker}: {response.status_code}")
    return []


def fetch_yfinance_data(ticker: str, start_date: str, end_date: str) -> dict | None:
    """Fallback to yfinance for ETFs not covered by financialdatasets.ai."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(start=start_date, end=end_date)

        if hist.empty:
            print(f"  No yfinance data for {ticker}")
            return None

        current_price = hist["Close"].iloc[-1]

        # Calculate 3M and 6M returns
        if len(hist) >= 63:  # ~3 months of trading days
            start_3m = hist["Close"].iloc[-63]
            return_3m = ((current_price - start_3m) / start_3m) * 100
        else:
            return_3m = 0

        start_6m = hist["Close"].iloc[0]
        return_6m = ((current_price - start_6m) / start_6m) * 100 if start_6m > 0 else 0

        return {
            "price": current_price,
            "return_3m": return_3m,
            "return_6m": return_6m,
            "day_change_percent": 0,  # yfinance doesn't give this easily
            "market_cap": 0,
        }
    except Exception as e:
        print(f"  yfinance error for {ticker}: {e}")
        return None


def calculate_momentum(prices: list, months: int) -> float | None:
    """Calculate return over specified months from price list."""
    if not prices or len(prices) < 2:
        return None

    # Prices are sorted by date ascending
    # Find price from N months ago
    target_days = months * 30  # Approximate

    if len(prices) < target_days:
        # Use whatever history we have
        start_price = prices[0]["close"]
    else:
        start_price = prices[-target_days]["close"] if len(prices) > target_days else prices[0]["close"]

    end_price = prices[-1]["close"]

    if start_price == 0:
        return None

    return ((end_price - start_price) / start_price) * 100


def main():
    today = datetime.now()
    six_months_ago = today - timedelta(days=180)
    three_months_ago = today - timedelta(days=90)

    start_date = six_months_ago.strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    print(f"Fetching portfolio state as of {today.strftime('%Y-%m-%d')}")
    print(f"Historical data range: {start_date} to {end_date}")
    print("=" * 80)

    results = {}

    for ticker in TICKERS:
        print(f"\nProcessing {ticker}...")

        # Get current snapshot
        snapshot = fetch_snapshot(ticker)

        # Fallback to yfinance if financialdatasets.ai fails (common for ETFs)
        if not snapshot:
            print(f"  Trying yfinance fallback for {ticker}...")
            yf_data = fetch_yfinance_data(ticker, start_date, end_date)
            if yf_data:
                ref_price = REFERENCE_PRICES.get(ticker, 0)
                current_price = yf_data["price"]
                if ref_price > 0:
                    change_pct = ((current_price - ref_price) / ref_price) * 100
                    lower_bound = ref_price * 0.8
                    upper_bound = ref_price * 1.2
                    within_range = lower_bound <= current_price <= upper_bound
                else:
                    change_pct = 0
                    within_range = True

                momentum_positive = yf_data["return_3m"] > 0 and yf_data["return_6m"] > 0

                results[ticker] = {
                    "current_price": current_price,
                    "ref_price": ref_price,
                    "change_pct": change_pct,
                    "within_range": within_range,
                    "return_3m": yf_data["return_3m"],
                    "return_6m": yf_data["return_6m"],
                    "momentum_positive": momentum_positive,
                    "day_change_pct": 0,
                    "market_cap": 0,
                    "source": "yfinance",
                }

                print(f"  Current: ${current_price:.2f} | Ref: ${ref_price:.2f} | Change: {change_pct:+.1f}%")
                print(f"  3M Return: {yf_data['return_3m']:+.1f}% | 6M Return: {yf_data['return_6m']:+.1f}%")
                print(f"  Momentum: {'POSITIVE' if momentum_positive else 'NEGATIVE'} | Within Range: {'YES' if within_range else 'NO'}")
                print(f"  (Source: yfinance)")
                continue
            else:
                print(f"  Skipping {ticker} - no data from either source")
                continue

        current_price = snapshot.get("price", 0)
        ref_price = REFERENCE_PRICES.get(ticker, 0)

        # Calculate price change from reference
        if ref_price > 0:
            change_pct = ((current_price - ref_price) / ref_price) * 100
            lower_bound = ref_price * 0.8
            upper_bound = ref_price * 1.2
            within_range = lower_bound <= current_price <= upper_bound
        else:
            change_pct = 0
            within_range = True

        # Get historical prices for momentum
        prices = fetch_historical_prices(ticker, start_date, end_date)

        # Calculate 3M and 6M momentum
        if prices:
            # Sort by date ascending
            prices_sorted = sorted(prices, key=lambda x: x["time"])

            # 3M return (last ~90 days)
            three_month_idx = max(0, len(prices_sorted) - 63)  # ~63 trading days in 3 months
            if three_month_idx < len(prices_sorted):
                start_3m = prices_sorted[three_month_idx]["close"]
                end_3m = prices_sorted[-1]["close"]
                return_3m = ((end_3m - start_3m) / start_3m) * 100 if start_3m > 0 else 0
            else:
                return_3m = 0

            # 6M return (full range)
            start_6m = prices_sorted[0]["close"]
            end_6m = prices_sorted[-1]["close"]
            return_6m = ((end_6m - start_6m) / start_6m) * 100 if start_6m > 0 else 0
        else:
            return_3m = 0
            return_6m = 0

        momentum_positive = return_3m > 0 and return_6m > 0

        results[ticker] = {
            "current_price": current_price,
            "ref_price": ref_price,
            "change_pct": change_pct,
            "within_range": within_range,
            "return_3m": return_3m,
            "return_6m": return_6m,
            "momentum_positive": momentum_positive,
            "day_change_pct": snapshot.get("day_change_percent", 0),
            "market_cap": snapshot.get("market_cap", 0),
        }

        print(f"  Current: ${current_price:.2f} | Ref: ${ref_price:.2f} | Change: {change_pct:+.1f}%")
        print(f"  3M Return: {return_3m:+.1f}% | 6M Return: {return_6m:+.1f}%")
        print(f"  Momentum: {'POSITIVE' if momentum_positive else 'NEGATIVE'} | Within Range: {'YES' if within_range else 'NO'}")

    # Print summary tables
    print("\n" + "=" * 80)
    print("PRICE COMPARISON TABLE")
    print("=" * 80)
    print(f"{'Ticker':<8} {'Current':>10} {'Reference':>10} {'Change %':>10} {'In Range':>10}")
    print("-" * 48)
    for ticker, data in results.items():
        status = "YES" if data["within_range"] else "NO"
        print(f"{ticker:<8} ${data['current_price']:>8.2f} ${data['ref_price']:>8.2f} {data['change_pct']:>+9.1f}% {status:>10}")

    print("\n" + "=" * 80)
    print("MOMENTUM TABLE")
    print("=" * 80)
    print(f"{'Ticker':<8} {'3M Return':>12} {'6M Return':>12} {'Momentum':>12}")
    print("-" * 44)
    for ticker, data in results.items():
        status = "POSITIVE" if data["momentum_positive"] else "NEGATIVE"
        print(f"{ticker:<8} {data['return_3m']:>+11.1f}% {data['return_6m']:>+11.1f}% {status:>12}")

    # Check for alerts
    print("\n" + "=" * 80)
    print("ALERTS")
    print("=" * 80)

    alerts = []
    for ticker, data in results.items():
        if not data["within_range"]:
            alerts.append(f"PRICE ALERT: {ticker} is outside 20% range (${data['current_price']:.2f} vs ref ${data['ref_price']:.2f})")
        if not data["momentum_positive"]:
            alerts.append(f"MOMENTUM ALERT: {ticker} has negative momentum (3M: {data['return_3m']:+.1f}%, 6M: {data['return_6m']:+.1f}%)")

    if alerts:
        for alert in alerts:
            print(f"  - {alert}")
    else:
        print("  No alerts. All positions within range and have positive momentum.")

    # Generate markdown for us-investment-decisions.md
    print("\n" + "=" * 80)
    print("MARKDOWN OUTPUT (for us-investment-decisions.md)")
    print("=" * 80)

    md_output = f"""
## 11. Current State (Jan 2026)

**As of:** {today.strftime('%Y-%m-%d')}

### Price Comparison vs Dec 31, 2025 Reference

| Ticker | Current | Reference | Change | Within 20% Range |
|--------|---------|-----------|--------|------------------|
"""
    for ticker, data in results.items():
        status = "Yes" if data["within_range"] else "**NO**"
        md_output += f"| {ticker} | ${data['current_price']:.2f} | ${data['ref_price']:.2f} | {data['change_pct']:+.1f}% | {status} |\n"

    md_output += """
### Momentum Status

| Ticker | 3M Return | 6M Return | Combined Momentum |
|--------|-----------|-----------|-------------------|
"""
    for ticker, data in results.items():
        status = "Positive" if data["momentum_positive"] else "**NEGATIVE**"
        md_output += f"| {ticker} | {data['return_3m']:+.1f}% | {data['return_6m']:+.1f}% | {status} |\n"

    # Add alerts section
    if alerts:
        md_output += "\n### Alerts\n\n"
        for alert in alerts:
            md_output += f"- {alert}\n"
    else:
        md_output += "\n### Status\n\nAll positions within 20% range and have positive momentum. DCA can proceed as planned.\n"

    print(md_output)

    return results


if __name__ == "__main__":
    main()
