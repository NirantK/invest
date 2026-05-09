"""
Shared momentum scoring — used by both US (us_portfolio_allocation, backtest) and
India (ai_infra_momentum, fetch_etf_data) screeners.

Pure numpy in/out. No universe lookups. No platform-specific assumptions.

Score variants reported:
  score_pricemom    - pure (wt_mom * smoothness) / dn_vol
  score_sortino     - score_pricemom * vol_factor * high_factor (legacy default)
  score_martin      - martin (wt_mom / ulcer) * smoothness * vol_factor * high_factor
  score             - alias for score_martin (current default)
  score_12_1        - (mom_12m * smoothness) / dn_vol  (Asness/Moskowitz academic)
  score_wtmf        - WisdomTree Managed Futures composite-sign signal, vol-adjusted
  score_baltas      - Baltas-Kosowski trend-fit slope, t-stat gated

Closes/dvols are optional — when None, vol_factor=1, high_factor=1 (US-style boosts disabled).
"""

from __future__ import annotations

import numpy as np

# Lookback windows (trading days)
SKIP_1M = 21
LOOKBACK_1M = 20
LOOKBACK_3M = 63
LOOKBACK_6M = 126
LOOKBACK_12M = 252


def score_one(
    ticker: str,
    prices: np.ndarray,
    returns: np.ndarray,
    closes: np.ndarray | None = None,
    dvols: np.ndarray | None = None,
) -> dict | None:
    """Compute full momentum metric set for a single ticker.

    Args:
      ticker: identifier (returned in the dict for downstream join)
      prices: total-return adjusted price series (1d ndarray)
      returns: simple daily returns derived from prices (1d ndarray)
      closes: raw (unadjusted) close prices for 52WH distance (optional)
      dvols:  daily dollar/rupee volume (close × volume) for ADV + slope (optional)

    Returns dict, or None if insufficient history.
    """
    n = len(prices)
    if n < LOOKBACK_3M + SKIP_1M:
        return None

    def mom(lookback: int) -> float:
        if n < lookback + SKIP_1M:
            return 0.0
        end_idx = n - SKIP_1M
        start_idx = end_idx - lookback
        return float((prices[end_idx - 1] / prices[start_idx]) - 1)

    mom_1m = mom(LOOKBACK_1M)
    mom_3m = mom(LOOKBACK_3M)
    mom_6m = mom(LOOKBACK_6M)
    mom_12m = mom(LOOKBACK_12M)
    wt_mom = 0.2 * mom_3m + 0.4 * mom_6m + 0.4 * mom_12m

    # Downside vol (annualised)
    neg = returns[returns < 0]
    dn_vol = float(neg.std() * np.sqrt(252)) if len(neg) > 0 else 1e-4

    # Quality (R² of log-price linear fit) over 12M-1M window
    end_idx = n - SKIP_1M if SKIP_1M > 0 else n
    start_idx = max(0, end_idx - LOOKBACK_12M)
    window = prices[start_idx:end_idx]
    if len(window) < 20:
        quality = 0.0
        baltas_slope = baltas_tstat = baltas_signal = 0.0
    else:
        log_w = np.log(window)
        x = np.arange(len(log_w))
        slope, intercept = np.polyfit(x, log_w, 1)
        fitted = slope * x + intercept
        ss_res = np.sum((log_w - fitted) ** 2)
        ss_tot = np.sum((log_w - log_w.mean()) ** 2)
        quality = max(1 - (ss_res / ss_tot), 0.0) if ss_tot > 0 else 0.0

        # Baltas-Kosowski trend-fit signal
        baltas_slope = float(slope * 252)
        residuals = log_w - fitted
        se_slope = np.sqrt(np.sum(residuals ** 2) / (len(x) - 2)) / np.sqrt(
            np.sum((x - x.mean()) ** 2)
        )
        baltas_tstat = float(slope / se_slope) if se_slope > 0 else 0.0
        baltas_signal = baltas_slope if abs(baltas_tstat) > 1.5 else 0.0

    # Frog-In-the-Pan: fraction of positive daily returns in window
    fip_returns = returns[start_idx:end_idx]
    fip = float(np.mean(fip_returns > 0)) if len(fip_returns) > 0 else 0.5
    smoothness = float((quality * fip) ** 0.5)

    # Core scores
    score_pricemom = (wt_mom * smoothness) / dn_vol if dn_vol > 0 else 0.0
    score_12_1 = (mom_12m * smoothness) / dn_vol if dn_vol > 0 else 0.0
    score_baltas = (baltas_signal * quality) / dn_vol if dn_vol > 0 else 0.0

    # WTMF composite-sign signal
    m3_sign = 1.0 if mom_3m > 0 else (-1.0 if mom_3m < 0 else 0.0)
    m6_sign = 1.0 if mom_6m > 0 else (-1.0 if mom_6m < 0 else 0.0)
    m12_sign = 1.0 if mom_12m > 0 else (-1.0 if mom_12m < 0 else 0.0)
    wtmf_composite = m3_sign + m6_sign + m12_sign
    wtmf_weight = abs(wtmf_composite) / 3.0
    wtmf_mom = wtmf_weight * wt_mom
    score_wtmf = (wtmf_mom * smoothness) / dn_vol if dn_vol > 0 else 0.0

    # Drawdowns
    running_max = np.maximum.accumulate(prices)
    drawdown = (prices - running_max) / running_max
    max_dd = float(drawdown.min())
    current_dd = float(drawdown[-1])

    if n >= LOOKBACK_12M:
        last_year = prices[-LOOKBACK_12M:]
        rmax_1y = np.maximum.accumulate(last_year)
        dd_1y = (last_year - rmax_1y) / rmax_1y
        ulcer_1y = float(np.sqrt(np.mean(dd_1y ** 2)))
        max_dd_1y = float(dd_1y.min())
    else:
        ulcer_1y = float(np.sqrt(np.mean(drawdown ** 2)))
        max_dd_1y = max_dd

    martin = (wt_mom / ulcer_1y) if ulcer_1y > 0.001 else 0.0

    # DD durations
    in_dd = drawdown < 0
    periods = []
    start = None
    for i in range(len(in_dd)):
        if in_dd[i] and start is None:
            start = i
        elif not in_dd[i] and start is not None:
            periods.append(i - start)
            start = None
    if start is not None:
        periods.append(len(in_dd) - start)
    max_dd_dur = max(periods) if periods else 0
    avg_dd_dur = float(np.mean(periods)) if periods else 0.0

    # Worst rolling-3M DD
    worst_3m_dd = max_dd
    win = 63
    if len(prices) > win:
        rolling = []
        for i in range(win, len(prices)):
            w = prices[i - win : i]
            wmax = np.maximum.accumulate(w)
            rolling.append(((w - wmax) / wmax).min())
        worst_3m_dd = float(min(rolling)) if rolling else max_dd

    # Volume + level boosts (require closes/dvols)
    if closes is not None and len(closes) >= LOOKBACK_12M:
        max_252 = float(np.nanmax(closes[-LOOKBACK_12M:]))
        last_close = float(closes[-1])
        dist52 = 1.0 - (last_close / max_252) if max_252 > 0 else 1.0
    else:
        dist52 = float("nan")

    if dvols is not None and len(dvols) >= LOOKBACK_3M:
        dvw = dvols[-LOOKBACK_3M:]
        dvw = dvw[np.isfinite(dvw) & (dvw > 0)]
        if len(dvw) >= 30:
            log_dv = np.log(dvw)
            xd = np.arange(len(log_dv))
            dv_slope = float(np.polyfit(xd, log_dv, 1)[0]) * 252
        else:
            dv_slope = 0.0
    else:
        dv_slope = 0.0

    if dvols is not None and len(dvols) >= 60:
        adv60 = float(np.nanmean(dvols[-60:]))
    else:
        adv60 = 0.0

    vol_factor = float(np.clip(1.0 + 0.15 * dv_slope, 0.7, 1.3)) if dvols is not None else 1.0

    if not np.isnan(dist52):
        if dist52 < 0.10:
            high_factor = 1.10
        elif dist52 < 0.25:
            high_factor = 1.00
        else:
            high_factor = max(0.85, 1.00 - 0.50 * (dist52 - 0.25))
    else:
        high_factor = 1.0

    score_sortino = score_pricemom * vol_factor * high_factor
    score_martin = martin * smoothness * vol_factor * high_factor
    # Default reported score: Martin
    score = score_martin

    return {
        "ticker": ticker,
        "mom_1m": mom_1m,
        "mom_3m": mom_3m,
        "mom_6m": mom_6m,
        "mom_12m": mom_12m,
        "wt_mom": wt_mom,
        "quality": quality,
        "fip": fip,
        "smoothness": smoothness,
        "dn_vol": dn_vol,
        "score": score,
        "score_pricemom": score_pricemom,
        "score_sortino": score_sortino,
        "score_martin": score_martin,
        "score_12_1": score_12_1,
        "wtmf_composite": wtmf_composite,
        "score_wtmf": score_wtmf,
        "baltas_slope": baltas_slope,
        "baltas_tstat": baltas_tstat,
        "score_baltas": score_baltas,
        "ulcer_1y": ulcer_1y,
        "max_dd_1y": max_dd_1y,
        "martin": martin,
        "max_dd": max_dd,
        "max_dd_dur": max_dd_dur,
        "avg_dd_dur": avg_dd_dur,
        "current_dd": current_dd,
        "worst_3m_dd": worst_3m_dd,
        "dist52": dist52,
        "dv_slope": dv_slope,
        "adv60": adv60,
        "vol_factor": vol_factor,
        "high_factor": high_factor,
        "latest_price": float(prices[-1]),
    }
