"""Macro feature pipeline for HMM regime detection.

Loads four cached parquets (built by build_macro_data.py) and exposes
`get_macro_features(date_array)` returning an aligned (n_dates, 8) numpy
array of z-score normalized macro features.

Wire into invest.regime_hmm.HMMRegime by concatenating with the existing
2-feature stack (log_ret, rolling_vol):

    from india.scripts.macro_pipeline import get_macro_features
    macro_x = get_macro_features(price_dates_iso)  # (n, 8)
    full_x = np.column_stack([base_features, macro_x])  # (n, 10)

Feature columns (in order):
    0: fii_cash_21d_z       — rolling 21d net FII cash flow, z-scored
    1: fii_cash_60d_z       — rolling 60d net FII cash flow, z-scored
    2: vol_log_ratio_z      — log(today_vol / 60d_avg), z-scored
    3: agg_abs_ret_z        — universe mean |daily log return| (intraday-range proxy), z
    4: agg_amihud_log_z     — universe median log(1+amihud), z-scored
    5: agg_vp_corr_z        — universe mean rolling-21d corr(ret, log_vol), z
    6: concall_sent_z       — keyword-derived management tone, z
    7: concall_n_z          — n companies that have reported, z (confidence proxy)

All z-scores are computed over a trailing 252d window per call; missing
values are zero-imputed AFTER z-scoring (i.e. neutral signal).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "india/data"

FII_DII_PARQUET = DATA / "macro_fii_dii.parquet"
VOLUME_PARQUET = DATA / "macro_volume.parquet"
MICRO_PARQUET = DATA / "macro_microstructure.parquet"
CONCALL_PARQUET = DATA / "macro_concall_sentiment.parquet"

ZSCORE_WINDOW = 252


def _rolling_zscore(x: np.ndarray, window: int = ZSCORE_WINDOW) -> np.ndarray:
    """Z-score each point against a trailing window (look-ahead-safe).

    For points with fewer than `window` history, uses expanding stats.
    NaNs in `x` are preserved as NaN in output (caller imputes).
    """
    n = len(x)
    out = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - window + 1)
        chunk = x[lo: i + 1]
        valid = chunk[~np.isnan(chunk)]
        if len(valid) < 5:
            continue
        mu = valid.mean()
        sd = valid.std(ddof=0)
        if sd == 0:
            continue
        out[i] = (x[i] - mu) / sd if not np.isnan(x[i]) else np.nan
    return out


def _load_aligned(date_array: np.ndarray) -> dict[str, np.ndarray]:
    """For each parquet, build a numpy array aligned to `date_array` (ISO strings)."""
    cal = pl.DataFrame({"date": list(date_array)})

    # FII/DII
    fii = pl.read_parquet(FII_DII_PARQUET).select(
        "date", "fii_cash_21d", "fii_cash_60d"
    )
    fii_aln = cal.join(fii, on="date", how="left")

    # Volume
    vol = pl.read_parquet(VOLUME_PARQUET).select("date", "vol_log_ratio")
    vol_aln = cal.join(vol, on="date", how="left")

    # Microstructure
    micro = pl.read_parquet(MICRO_PARQUET).select(
        "date", "agg_abs_ret", "agg_amihud_log", "agg_vp_corr"
    )
    micro_aln = cal.join(micro, on="date", how="left")

    # Concall
    concall = pl.read_parquet(CONCALL_PARQUET).select(
        "date", "sentiment_score", "n_companies_reporting"
    )
    concall_aln = cal.join(concall, on="date", how="left")

    return {
        "fii_21d": fii_aln["fii_cash_21d"].to_numpy().astype(float),
        "fii_60d": fii_aln["fii_cash_60d"].to_numpy().astype(float),
        "vol_log_ratio": vol_aln["vol_log_ratio"].to_numpy().astype(float),
        "abs_ret": micro_aln["agg_abs_ret"].to_numpy().astype(float),
        "amihud": micro_aln["agg_amihud_log"].to_numpy().astype(float),
        "vp_corr": micro_aln["agg_vp_corr"].to_numpy().astype(float),
        "concall_sent": concall_aln["sentiment_score"].to_numpy().astype(float),
        "concall_n": concall_aln["n_companies_reporting"].to_numpy().astype(float),
    }


def get_macro_features(date_array: np.ndarray | list) -> np.ndarray:
    """Return (n_dates, 8) z-scored macro feature matrix aligned to date_array.

    Parameters
    ----------
    date_array : array-like of ISO date strings (YYYY-MM-DD).

    Returns
    -------
    np.ndarray, shape (len(date_array), 8). NaNs are zero-imputed (neutral).
    """
    date_array = np.asarray(date_array)
    raw = _load_aligned(date_array)
    cols = []
    for key in ["fii_21d", "fii_60d", "vol_log_ratio", "abs_ret",
                "amihud", "vp_corr", "concall_sent", "concall_n"]:
        z = _rolling_zscore(raw[key])
        z = np.nan_to_num(z, nan=0.0)
        cols.append(z)
    return np.column_stack(cols)


def feature_null_ratios(date_array: np.ndarray | list) -> dict[str, float]:
    """Return per-feature null ratio over the requested date range (pre-zscore)."""
    date_array = np.asarray(date_array)
    raw = _load_aligned(date_array)
    return {k: float(np.isnan(v).mean()) for k, v in raw.items()}


def feature_correlation(date_array: np.ndarray | list) -> tuple[list[str], np.ndarray]:
    """Return (feature_names, 8x8 corr matrix) on z-scored features (post-impute)."""
    feats = get_macro_features(date_array)
    names = ["fii_21d", "fii_60d", "vol_log_ratio", "abs_ret",
             "amihud", "vp_corr", "concall_sent", "concall_n"]
    return names, np.corrcoef(feats.T)


# ---------------------------------------------------------------------------
# CLI sanity check
# ---------------------------------------------------------------------------

def main() -> None:
    """Print null-ratios + correlation matrix over last 252 trading days."""
    vol = pl.read_parquet(VOLUME_PARQUET).select("date").sort("date")
    recent_dates = vol["date"].tail(252).to_numpy()
    print(f"Sanity check on last {len(recent_dates)} dates: "
          f"{recent_dates[0]} → {recent_dates[-1]}\n")

    nulls = feature_null_ratios(recent_dates)
    print("Per-feature null ratios (raw, pre z-score, pre-impute):")
    for k, v in nulls.items():
        print(f"  {k:18s}  {v:6.1%}")

    names, corr = feature_correlation(recent_dates)
    print("\nFeature correlation matrix (after z-score + zero-impute):")
    print("              " + "  ".join(f"{n[:8]:>8}" for n in names))
    for i, n in enumerate(names):
        row = "  ".join(f"{corr[i, j]:+.2f}   " for j in range(len(names)))
        print(f"  {n[:12]:12s}  {row}")

    # Flag redundancies
    print("\nPairs with |corr| > 0.7 (likely redundant):")
    found = False
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if abs(corr[i, j]) > 0.7:
                print(f"  {names[i]:18s} <-> {names[j]:18s}  r={corr[i, j]:+.2f}")
                found = True
    if not found:
        print("  (none)")

    feats = get_macro_features(recent_dates)
    print(f"\nFeature matrix shape: {feats.shape}")
    print(f"Last row: {feats[-1].round(2)}")


if __name__ == "__main__":
    main()
