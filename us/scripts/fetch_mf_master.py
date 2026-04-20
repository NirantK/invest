"""Fetch all MF schemes from mfapi.in, dedup to Direct Growth only, save as parquet."""

from pathlib import Path

import httpx
import polars as pl
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

MFAPI_BASE = "https://api.mfapi.in/mf"
OUTPUT = Path(__file__).parent.parent / "data" / "mf_schemes_direct_growth.parquet"

EXCLUDE_KEYWORDS = [
    "idcw", "dividend", "regular plan", "bonus", "payout",
    "institutional", "segregated", "annual", "monthly",
    "quarterly", "weekly", "reinvestment",
]


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.HTTPStatusError,
    )),
    reraise=True,
)
def _fetch_all_schemes() -> list[dict]:
    resp = httpx.get(MFAPI_BASE, timeout=60)
    resp.raise_for_status()
    return resp.json()


def main():
    print("Fetching all schemes from mfapi.in...")
    all_schemes = _fetch_all_schemes()
    print(f"Total schemes: {len(all_schemes)}")

    df = pl.DataFrame(all_schemes).rename(
        {"schemeCode": "scheme_code", "schemeName": "scheme_name"}
    )
    name_lower = pl.col("scheme_name").str.to_lowercase()
    df = df.with_columns(name_lower.alias("name_lower"))

    # Must contain "direct" AND ("growth" or end with " gr")
    df = df.filter(
        pl.col("name_lower").str.contains("direct")
        & (
            pl.col("name_lower").str.contains("growth")
            | pl.col("name_lower").str.ends_with(" gr")
        )
    )
    print(f"After direct+growth filter: {len(df)}")

    # Exclude IDCW, dividend, regular, bonus, etc.
    for kw in EXCLUDE_KEYWORDS:
        df = df.filter(~pl.col("name_lower").str.contains(kw))
    print(f"After exclude filter: {len(df)}")

    # Drop helper columns, keep only scheme_code and scheme_name
    df = df.select("scheme_code", "scheme_name")

    # Save parquet
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(OUTPUT)
    print(f"Saved {len(df)} schemes to {OUTPUT}")

    # Build MF name cache (avoids API calls during report generation)
    import json
    name_cache = {}
    for row in df.iter_rows(named=True):
        name = row["scheme_name"]
        for drop in [" - Direct Plan", " Direct Plan", "-Direct Plan",
                     " - Growth Option", " - Growth", "-Growth",
                     " Growth", " Option", " Fund"]:
            name = name.replace(drop, "")
        name_cache[str(row["scheme_code"])] = name[:45]
    names_file = OUTPUT.parent / "mf_scheme_names.json"
    names_file.write_text(json.dumps(name_cache, indent=2, sort_keys=True))
    print(f"Saved {len(name_cache)} scheme names to {names_file}")


if __name__ == "__main__":
    main()
