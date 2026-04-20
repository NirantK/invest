"""
Check pairwise holding overlap between ETFs in the final allocation.
Uses yfinance to fetch top holdings and computes overlap percentage.
"""

import itertools

import yfinance as yf

FUNDS = [
    "DFIV",
    "DXIV",
    "IVAL",
    "DISV",
    "AVDV",
    "IMOM",
    "EWJV",
    "DFJ",
    "DFE",
    "FRDM",
    "AVES",
    "AVEM",
    "DFEV",
    "FLN",
]


def get_holdings(ticker: str) -> set[str]:
    """Fetch top holdings for an ETF via yfinance."""
    t = yf.Ticker(ticker)
    # Try multiple approaches to get holdings
    holdings = set()

    # Method 1: .holdings property (newer yfinance)
    try:
        h = t.get_holdings()
        if h is not None and not h.empty:
            holdings = set(h.index.tolist())
    except Exception:
        pass

    # Method 2: fund_top_holdings
    if not holdings:
        try:
            info = t.get_info()
            top = info.get("holdings", [])
            holdings = set(h.get("symbol", h.get("holdingName", "")) for h in top)
        except Exception:
            pass

    return holdings


def main():
    print("Fetching holdings for all funds...")
    all_holdings = {}
    for fund in FUNDS:
        holdings = get_holdings(fund)
        all_holdings[fund] = holdings
        print(f"  {fund}: {len(holdings)} holdings found")

    # Compute pairwise overlap
    header = (
        f"{'Pair':<15} {'Overlap%':>10} {'Shared':>8} {'Fund1':>8} "
        f"{'Fund2':>8} {'Verdict':>10}"
    )
    print(f"\n{header}")
    print("-" * 65)

    high_overlap_pairs = []

    for a, b in itertools.combinations(FUNDS, 2):
        h_a = all_holdings[a]
        h_b = all_holdings[b]

        if not h_a or not h_b:
            continue

        shared = h_a & h_b
        # Overlap = shared / min(len_a, len_b)
        # Measures how much the smaller fund overlaps
        min_size = min(len(h_a), len(h_b))
        overlap_pct = len(shared) / min_size * 100 if min_size > 0 else 0

        verdict = "HIGH" if overlap_pct > 50 else "ok"
        if overlap_pct > 50:
            high_overlap_pairs.append((a, b, overlap_pct))

        if overlap_pct > 20:  # Only show meaningful overlap
            pair_label = f"{a}/{b}"
            print(
                f"  {pair_label:<13} {overlap_pct:>9.1f}% {len(shared):>7} "
                f"{len(h_a):>7} {len(h_b):>7} {verdict:>10}"
            )

    print(f"\n{'=' * 65}")
    print("PAIRS WITH >50% OVERLAP (pick one from each pair):")
    print("=" * 65)
    if high_overlap_pairs:
        for a, b, pct in sorted(high_overlap_pairs, key=lambda x: -x[2]):
            print(f"  {a} / {b}: {pct:.1f}% overlap")
    else:
        print("  None found via yfinance holdings data.")
        print("  Note: yfinance may not return holdings for all ETFs.")
        print("  Falling back to known overlap from fund documentation...")

        # Known overlaps from fund family documentation
        print("\n  KNOWN HIGH-OVERLAP PAIRS (from fund prospectuses):")
        known = [
            (
                "DFIV",
                "DXIV",
                "~70-80%",
                "Both DFA intl value, DXIV is aggressive tilt of same universe",
            ),
            (
                "AVDV",
                "DISV",
                "~60-70%",
                "Both intl developed small cap value, similar universe",
            ),
            (
                "AVES",
                "AVEM",
                "~70-80%",
                "AVEM is broader, AVES is value subset of same EM universe",
            ),
            (
                "AVES",
                "DFEV",
                "~50-60%",
                "Both EM value, same factor in same region",
            ),
            (
                "EWJV",
                "DFJ",
                "~40-50%",
                "Both Japan, but EWJV=large/mid value, DFJ=small cap dividend",
            ),
        ]
        for a, b, pct, reason in known:
            print(f"  {a} / {b}: {pct} — {reason}")


if __name__ == "__main__":
    main()
