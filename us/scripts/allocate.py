"""Momentum-weighted US portfolio allocation."""
import click
import pandas as pd
import numpy as np
import yfinance as yf

CATS = {
    'Platinum': ['PPLT'],  # Physical platinum
    'Silver': ['WPM'],  # Wheaton silver/gold streamer
    'Gold': ['FNV'],  # Franco-Nevada gold royalty/streamer
    'Copper': ['COPX'],  # Copper miners ETF (40+ miners)
    'BaseMtl': ['VALE'],  # Vale nickel/iron/copper
    'Oil_Gas': ['XOM', 'CVX', 'SU', 'CNQ', 'VLO', 'MPC', 'PSX', 'OIH', 'XLE', 'XOP'],  # Oil majors, Canadian, refiners, ETFs
    'NatGas': ['FCG', 'LNG', 'AR', 'EQT'],  # Nat gas producers
    'Uranium': ['URNM', 'URA', 'NLR'],  # Uranium/nuclear
    'ExUS': ['AVDV'],  # Ex-US Small Value
    'LATAM': ['ILF'],  # LATAM 40 (Brazil+Mexico+Chile)
    'IntlMom': ['IMTM'],  # International momentum
}
TICKERS = [t for ts in CATS.values() for t in ts]


def fetch(tickers: list[str], period: str = '3y') -> pd.DataFrame:
    """Fetch total return prices (reinvested dividends)."""
    dfs = []
    for t in tickers:
        h = yf.Ticker(t).history(period=period)
        if h.empty:
            continue
        c, d = h['Close'], h['Dividends']
        tr = c * (1 + (d / c.shift(1)).fillna(0).cumsum())
        dfs.append(tr.rename(t))
    return pd.concat(dfs, axis=1).dropna()


def allocate(capital: int, top_n: int, min_w: float, max_w: float) -> tuple[pd.Series, pd.DataFrame]:
    """Select top N by weighted momentum score, allocate by 12w-2w momentum."""
    prices = fetch(TICKERS)
    ret = prices.pct_change().dropna()

    # 12-1 momentum: 12 month return excluding most recent month
    mom_12_1 = prices.iloc[-21] / prices.iloc[-252] - 1
    # 6-1 momentum: 6 month return excluding most recent month
    mom_6_1 = prices.iloc[-21] / prices.iloc[-126] - 1
    # 12w-2w momentum: 12 week return excluding most recent 2 weeks
    mom_12w_2w = prices.iloc[-10] / prices.iloc[-60] - 1
    # Weighted average for selection
    mom_avg = (mom_12_1 + mom_6_1 + mom_12w_2w) / 3
    dvol = ret.apply(lambda x: x[x < 0].std() * np.sqrt(252))
    score = mom_avg / dvol

    # Store all momentum scores
    scores = pd.DataFrame({
        '12-1': mom_12_1 * 100,
        '6-1': mom_6_1 * 100,
        '12w-2w': mom_12w_2w * 100,
        'Avg': mom_avg * 100,
        'Score': score,
    })

    # Select top N by weighted score
    top_tickers = score.nlargest(top_n).index
    # Allocate by 12w-2w momentum (positive only)
    alloc_mom = mom_12w_2w[top_tickers].clip(lower=0)
    alloc = (alloc_mom / alloc_mom.sum()) * capital

    for _ in range(10):
        alloc[alloc < capital * min_w] = capital * min_w
        alloc[alloc > capital * max_w] = capital * max_w
        alloc *= capital / alloc.sum()

    return (alloc / 1000).round() * 1000, scores


def cat_of(t: str) -> str:
    return next((c for c, ts in CATS.items() if t in ts), '?')


THESIS = {
    'PPLT': 'Physical platinum',
    'WPM': 'Silver/gold streamer',
    'FNV': 'Gold royalty/streamer',
    'COPX': 'Copper miners ETF',
    'VALE': 'Base metals (Ni/Fe/Cu)',
    'XOM': 'Exxon Mobil',
    'CVX': 'Chevron',
    'SU': 'Suncor Canadian',
    'CNQ': 'Canadian Natural',
    'VLO': 'Valero refiner',
    'MPC': 'Marathon refiner',
    'PSX': 'Phillips 66',
    'OIH': 'Oil services ETF',
    'XLE': 'Energy Select ETF',
    'XOP': 'Oil & Gas E&P ETF',
    'FCG': 'Nat gas ETF',
    'LNG': 'Cheniere Energy',
    'AR': 'Antero Resources',
    'EQT': 'EQT Corporation',
    'URNM': 'Uranium miners ETF',
    'URA': 'Global uranium ETF',
    'NLR': 'Uranium + nuclear ETF',
    'AVDV': 'Ex-US Small Value',
    'ILF': 'LATAM 40',
    'IMTM': 'Intl Momentum',
}


@click.command()
@click.option('-c', '--capital', default=73296, help='Total capital')
@click.option('-n', '--top-n', default=9, help='Number of top positions to select')
@click.option('-m', '--min-w', default=0.05, help='Min position weight')
@click.option('-M', '--max-w', default=0.30, help='Max position weight')
def main(capital: int, top_n: int, min_w: float, max_w: float):
    alloc, scores = allocate(capital, top_n, min_w, max_w)

    print(f'US ALLOCATION (${capital:,})\n')
    print(f'{"Tick":<5} {"$":>7} {"%":>5} {"12-1":>6} {"6-1":>6} {"12w2w":>6} {"Score":>6}  {"Thesis":<25}')
    print('-' * 80)

    for t in alloc[alloc > 0].sort_values(ascending=False).index:
        pct = alloc[t] / capital * 100
        s = scores.loc[t]
        print(f'{t:<5} {alloc[t]:>7,.0f} {pct:>4.0f}% {s["12-1"]:>5.0f}% {s["6-1"]:>5.0f}% {s["12w-2w"]:>5.0f}% {s["Score"]:>6.2f}  {THESIS.get(t, ""):<25}')
    print(f'{"TOTAL":<5} {alloc.sum():>7,.0f}')

    print(f'\nWEEKLY DCA (12 weeks):')
    for t in alloc[alloc > 0].sort_values(ascending=False).index:
        weekly = max(100, int(alloc[t] / 12 / 100) * 100)
        print(f'  {t}: ${weekly:,}/wk')


if __name__ == '__main__':
    main()
