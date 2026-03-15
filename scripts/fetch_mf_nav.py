"""
Fetch Indian Mutual Fund NAV data from mfapi.in
API docs: https://www.mfapi.in/

Example scheme codes:
- 119551: Nippon India Gold ETF
- 120503: HDFC Liquid Fund
- 118989: PPFAS Flexi Cap Fund
"""

import httpx

MFAPI_BASE = "https://api.mfapi.in/mf"


def get_mf_nav(scheme_code: int) -> dict:
    """Get latest NAV and scheme info."""
    resp = httpx.get(f"{MFAPI_BASE}/{scheme_code}", timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_mf_history(scheme_code: int) -> list:
    """Get historical NAV data."""
    data = get_mf_nav(scheme_code)
    return data.get("data", [])


def get_latest_nav(scheme_code: int) -> dict:
    """Get just the latest NAV value."""
    data = get_mf_nav(scheme_code)
    meta = data.get("meta", {})
    nav_data = data.get("data", [])
    latest = nav_data[0] if nav_data else {}
    return {
        "scheme_code": scheme_code,
        "scheme_name": meta.get("scheme_name"),
        "fund_house": meta.get("fund_house"),
        "nav": float(latest.get("nav", 0)) if latest else None,
        "date": latest.get("date"),
    }


def search_mf(query: str) -> list:
    """Search mutual funds by name."""
    resp = httpx.get(f"{MFAPI_BASE}/search", params={"q": query}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_all_mf_list() -> list:
    """Get list of all available mutual funds."""
    resp = httpx.get(MFAPI_BASE, timeout=30)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    # Test with Nippon India Gold ETF
    print("Testing mfapi.in integration...")
    result = get_latest_nav(119551)
    print(f"Scheme: {result['scheme_name']}")
    print(f"NAV: {result['nav']} as of {result['date']}")

    print("\nSearching for 'gold'...")
    funds = search_mf("gold")[:5]
    for fund in funds:
        print(f"  {fund['schemeCode']}: {fund['schemeName']}")
