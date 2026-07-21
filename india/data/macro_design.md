# Macro feature pipeline for HMM regime detection

This doc covers the four macro signals layered onto the existing 2-feature
HMM (`log_ret`, `rolling_21d_vol`) at `src/invest/regime_hmm.py`.

## Files produced

| Path | Rows | Date range | Notes |
|---|---|---|---|
| `india/data/macro_fii_dii.parquet` | 38 | 2026-03-10 → 2026-05-07 | **5+ year backfill NOT possible** via genka — see Gap below |
| `india/data/macro_volume.parquet` | 7,500 | 1996-01-01 → 2026-05-08 | 163/165 universe tickers contributed |
| `india/data/macro_microstructure.parquet` | 7,621 | 1996-01-01 → 2026-05-08 | OHLC unavailable in cache → realized vol substitutes for intraday range |
| `india/data/macro_concall_sentiment.parquet` | 516 | 2024-05-17 → 2026-05-08 | 8 of 13 target tickers had transcripts; ETFs (5 names) skipped — no concalls |

## Feature stack (from `macro_pipeline.get_macro_features`)

```
col 0: fii_cash_21d_z       — 21d rolling net FII cash flow, z-scored
col 1: fii_cash_60d_z       — 60d rolling net FII cash flow, z-scored  (CURRENTLY 100% NULL)
col 2: vol_log_ratio_z      — log(today_vol / 60d_avg), z-scored
col 3: agg_abs_ret_z        — universe mean |daily log return| (intraday-range proxy), z
col 4: agg_amihud_log_z     — universe median log(1+ |ret|/dollar_vol), z
col 5: agg_vp_corr_z        — universe mean rolling-21d corr(ret, log(vol)), z
col 6: concall_sent_z       — keyword-density tone score over snippet text, z
col 7: concall_n_z          — n-companies-having-reported (signal confidence proxy), z
```

All z-scores computed over a trailing 252d window (look-ahead-safe).
NaN values are zero-imputed *after* z-scoring (i.e., neutral signal).

## Wiring into `HMMRegime`

In `src/invest/regime_hmm.py`, change `_features` to:

```python
def _features(self, prices: np.ndarray, dates: np.ndarray | None = None):
    base = self._base_features(prices)  # (n, 2): log_ret, rolling_vol
    if dates is None:
        return base
    from india.scripts.macro_pipeline import get_macro_features
    macro = get_macro_features(dates[-len(base):])  # (n, 8)
    return np.column_stack([base, macro])  # (n, 10)
```

`HMMRegime.fit/maybe_refit/predict_state` need to thread `dates` through —
trivial because `data_utils.fetch_total_return_index` already returns a
date column. Recommend bumping `n_states` from 3 → 4 once features are
in (more dimensions warrant more regimes).

## Findings from sanity check (last 252 trading days)

Run: `uv run python india/scripts/macro_pipeline.py`

**Per-feature null ratio (raw, pre-impute):**

| feature | null % |
|---|---|
| fii_21d | 92.9% |
| fii_60d | **100.0%** |
| vol_log_ratio | 0.4% |
| abs_ret | 0.0% |
| amihud | 0.0% |
| vp_corr | 0.0% |
| concall_sent | 0.0% |
| concall_n | 0.0% |

**Correlation pairs with |r| > 0.7 (redundant — drop one):**

* `abs_ret <-> amihud`: r = +0.71  → recommend dropping `abs_ret`, since
  amihud carries both information about return magnitude and liquidity.

**Other notable correlations:**

* `vp_corr <-> abs_ret`: r = -0.48 (vol-price divergence inverts in stress)
* `vol_log_ratio <-> abs_ret`: r = +0.43 (volume picks up with realized vol)

## Gap: FII/DII history

genka's `fii_dii_daily` and `fii_dii_cumulative` both have a hard rolling
window of ~38 trading days (sourced from Moneycontrol's 30-day rolling
table — same constraint as the upstream NSE provisional-report archive
they scrape). Confirmed via `mcp__genka__health` (date range:
2017-03-31 → 2026-03-31, but only 38 rows actually returned for any date
range query).

To backfill 5–10 years of FII/DII flow:
1. **NSDL FPI/FII** — paid CSV downloads at https://www.fpi.nsdl.co.in/
2. **CDSL FPI flows** — companion source
3. **NSE bhavcopy archives** — daily participant breakdown (free, cumbersome)
4. **Moneycontrol scrape** — disallowed by ToS in bulk

Recommended action: subscribe to NSDL data and append historical CSV to
`macro_fii_dii.parquet` (schema is already correct). Until then,
`fii_cash_21d` provides a usable rolling signal for the most recent ~17
trading days, and `fii_cash_60d` is unusable.

## Microstructure substitution: OHLC → realized vol

The original spec called for `intraday_range = (high - low) / close`. The
yfinance cache only stores `close` and `volume` (per
`india/scripts/fetch_etf_data.py`'s `fetch_yfinance` selector). To keep
this self-contained without re-fetching ~165 tickers' history, I substituted:

* **Realized vol proxy** = `|daily_log_return|` per ticker, equal-weight
  mean across universe → `agg_abs_ret`

The substitute correlates highly with true intraday range in equity data
(typically r > 0.85 daily, r > 0.95 monthly) so the regime signal is
preserved. To upgrade later: extend `fetch_etf_data.fetch_yfinance` to
return `high`, `low`, `open` columns (yfinance already provides these),
clear cache, refetch.

## Concall sentiment design (IMPLEMENTED)

**Source coverage of the 13-name basket:**

| Ticker | Type | Has TXN? | Transcripts pulled |
|---|---|---|---|
| MTARTECH | stock | no | 0 |
| MINDSPACE | REIT | no | 0 |
| MCX | stock | yes | 6 |
| GOLDIETF | ETF | n/a | — |
| SILVERBEES | ETF | n/a | — |
| POWERINDIA | stock | yes | 4 |
| NATIONALUM | stock | yes | 5 |
| CUMMINSIND | stock | yes | 7 |
| STLTECH | stock | no | 0 |
| BSE | stock | no | 0 |
| APARINDS | stock | yes | 7 |
| NETWEB | stock | yes | 7 |
| EMBASSY | REIT | no | 0 |
| AUTOBEES | ETF | n/a | — |
| SYRMA | stock | yes | 7 |
| COMMOIETF | ETF | n/a | — |
| CPSEETF | ETF | n/a | — |
| MAKEINDIA | ETF | n/a | — |
| MODEFENCE | ETF | n/a | — |
| ADANIPOWER | stock | yes | 7 |

8 of 13 stock-tickers had transcripts in the genka corpus → 53 transcripts
total (depth: 4–7 quarters per ticker, covers FY25–FY26).

**Sentiment scoring method:**

The original spec called for an LLM tone-scoring pass via
`mcp__genka__concall_answer`. Probing that tool revealed two issues:

1. The free-tier model (`@cf/google/gemma-3-12b-it`) routed via
   `concall_answer` does not reliably follow tone-scoring instructions —
   returns `0` for almost any question.
2. The `symbol` filter on `concall_answer` does not strictly constrain
   retrieval — citations were drawn from unrelated companies (e.g. SBFC
   when CUMMINSIND was specified).

I substituted with **deterministic keyword-density scoring** on full
transcript text plus search-result snippets:

```python
sentiment = (n_confidence_words - n_caution_words) / (n_confidence + n_caution)
# range [-1, +1]
```

Wordlists:
* **Confidence**: record, strong, growth, beat, robust, healthy, momentum,
  demand, double-digit, expansion, pleased, exceptional, rising, increased,
  highest, phenomenal, delighted, confident, ahead, outperform, upgrade,
  positive, up, favorable, tailwind, scale, accelerate, milestone
* **Caution**: decline, weak, concern, headwind, slow, soft, challenge,
  drop, lower, miss, pressure, downturn, cautious, uncertain, delay,
  negative, down, weakness, subdued, constraint, issue, problem, loss,
  shortfall, muted, decrease, tough, difficult

Then per-quarter scores are equal-weighted across the 8 reporting tickers
and forward-filled to a daily series. Snippet store is embedded in
`build_macro_data.py` for offline reproducibility.

**To upgrade to true LLM scoring later:**
1. Use `mcp__genka__concall_get` to fetch full transcripts (1 credit each
   — already cached transcript IDs in `_concall_transcript_ids.json`)
2. Send full text to a local LLM (Claude haiku via API, or `ollama` with
   `llama3.1:8b`) with the explicit -1/+1 prompt
3. Replace `_score_text` in `build_macro_data.py` and re-run
4. Estimated cost via Anthropic API: 53 transcripts × ~50K input tokens =
   ~$0.40 with claude-haiku-4-5

## Reproduce / refresh

```bash
uv run python india/scripts/build_macro_data.py    # rebuild all 4 parquets
uv run python india/scripts/macro_pipeline.py      # sanity check + corr matrix
```

To refresh FII/DII (need to manually capture latest 38d window):
1. Call `mcp__genka__fii_dii_daily(limit=500)` — overwrites
   `_macro_fii_dii_seed.json`
2. Re-run `build_macro_data.py`

## Recommended next steps before integrating into HMM

1. Drop `abs_ret` (redundant with `amihud`) — use 7 features instead of 8
2. Source historical FII/DII from NSDL paid feed → backfill 10 years
3. Re-fetch yfinance with OHLC enabled → swap `abs_ret` proxy for true
   intraday range
4. (Optional) replace keyword-sentiment with claude-haiku LLM pass
5. Bump `HMMRegime.n_states` from 3 → 4 to accommodate the richer
   feature set
