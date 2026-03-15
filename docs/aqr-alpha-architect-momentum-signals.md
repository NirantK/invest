# Executive Summary

Momentum and trend-following strategies, as implemented by AQR, Alpha Architect, and in academic research, primarily revolve around systematic approaches to signal construction, portfolio formation, and risk management. AQR's approach is twofold: 1) A cross-sectional 'Value and Momentum Everywhere' (VME) strategy that ranks assets based on their relative performance over the past 12 months, skipping the most recent month (a '12-2' lookback), and forms long-short portfolios with rank-based weights. 2) A time-series or 'trend' momentum (TSMOM) strategy that takes long or short positions in assets based on the sign of their own past absolute returns (e.g., over 1, 3, and 12 months). A core feature of AQR's implementation is rigorous risk management through volatility scaling, where individual positions are sized to a target volatility (e.g., 40% annualized) and the overall portfolio is scaled to a constant volatility target (e.g., 10% annualized). Alpha Architect builds on the standard 12-2 momentum signal by focusing on 'momentum quality' to improve robustness. Their key innovations include the 'Frog-in-the-Pan' (FIP) or 'ID' metric, which penalizes stocks with choppy, discrete return paths in favor of those with smoother, more continuous trends. They also employ filters like requiring a minimum number of positive months (e.g., 8 of the last 12) and exploit momentum seasonality by rebalancing in quarter-ending months (Feb, May, Aug, Nov). Foundational academic research underpins these strategies, from Jegadeesh and Titman's original work on 12-1 momentum to modern refinements. Notably, research by Barroso & Santa-Clara and Moreira & Muir demonstrates that scaling momentum portfolio exposure by its inverse realized volatility can significantly improve risk-adjusted returns and mitigate the severe drawdowns, or 'crashes,' to which momentum is prone. Further research by Daniel & Moskowitz identifies the specific conditions for these crashes—typically following a prolonged bear market and during a sharp market rebound—and proposes dynamic risk management overlays to navigate these periods.

# Aqr Value And Momentum Everywhere Details

## Signal Construction

The core signal is a cross-sectional momentum score based on the past 12-month return, excluding the most recent month (a '12-2' lookback). For each security 'i' at time 't', a momentum score 'S_it' is calculated. These scores are then ranked across the entire universe of securities to determine their relative strength.

## Portfolio Weighting

Portfolio weights are determined using a rank-based system. The weight for each security is proportional to its rank minus the average rank across all securities. This is formally expressed as w_it = c_t * (rank(S_it) - mean(rank)). A scaling factor, c_t, is applied to ensure the final portfolio is dollar-neutral, with one dollar in long positions and one dollar in short positions.

## Volatility Scaling

To ensure that different asset classes contribute similarly to the overall portfolio risk, the strategy employs volatility scaling. Each asset class sleeve (e.g., equities, bonds, commodities) is scaled by the inverse of its realized volatility, which is calculated over the full historical sample period. This method equalizes the ex-post volatility contribution from each asset class.

## Asset Classes Covered

The strategy is designed to be applied 'everywhere,' meaning it is implemented across a diverse set of global markets and asset classes. This includes individual stocks, country equity indices, currencies, commodities, and government bonds. The methodology is applied within each asset class and then aggregated.


# Aqr Time Series Momentum Details

## Signal Definition

The core signal for Time Series Momentum (TSMOM), also known as trend following, is the sign of an asset's excess return over a specific lookback period. If the asset's excess return over the past 'k' months is positive, the strategy takes a long position. If the excess return is negative, it takes a short position. The position is binary (long or short) and is based on the asset's own past performance, not its performance relative to other assets.

## Lookback Periods Tested

The AQR research on TSMOM explicitly tests and often combines several lookback horizons to create a more robust, diversified trend signal. The primary lookback periods considered are 1 month, 3 months, and 12 months. A diversified strategy would average the signals or returns from strategies based on each of these three horizons.

## Position Sizing Method

A constant volatility sizing methodology is a key feature of the strategy. Each individual position, whether long or short, is sized to target a specific ex-ante annualized volatility, which is set at 40%. The position size is calculated as 40% divided by the asset's estimated ex-ante volatility (σ_t-1). This ensures that each asset contributes an equal amount of risk to the portfolio before accounting for correlations.

## Portfolio Rebalancing Frequency

The portfolio is typically rebalanced on a monthly basis. At the end of each month, the trend signal (sign of past return) is recalculated for each asset, and the ex-ante volatility is re-estimated to adjust position sizes for the upcoming month. The provided context also notes the possibility of a weekly rebalance for robustness testing.


# Aqr Managed Futures Approach

## Volatility Estimation Method

The strategy uses an exponentially weighted moving average (EWMA) of past squared daily returns to estimate the ex-ante volatility for each instrument. This method places more weight on recent returns, making the volatility estimate more responsive to changes in market conditions. The formula is given as (σ^s_t)^2 = 261 * Σ(1−δ)δ^i * (r^s_{t−1−i} − r̄^s_t)^2, where 261 annualizes the daily variance.

## Ewma Parameter

The specific parameter used for the exponentially weighted moving average (EWMA) volatility calculation is a 'center of mass' of 60 days. This defines the decay factor (δ) in the EWMA formula, determining how much weight is given to recent versus older data in the volatility forecast.

## Portfolio Volatility Target

After sizing individual positions to a 40% volatility target, the overall combined portfolio is scaled to a more conservative ex-ante annualized volatility target of 10%. This scaling is performed monthly using an estimated variance-covariance matrix of the underlying positions to manage the total risk of the aggregated strategy.

## Diversification Approach

Diversification is a cornerstone of the approach and is achieved in two primary ways. First, the strategy is applied across a wide range of uncorrelated assets and markets globally (equities, bonds, currencies, commodities). Second, it diversifies across different trend-following horizons by combining signals from short-term (1-month), medium-term (3-month), and long-term (12-month) lookback periods into a single composite portfolio.


# Alpha Architect Quantitative Momentum Process

## Step 1 Universe Definition

The initial universe is established by applying filters for liquidity and size. The process begins with a broad set of stocks and then applies screens such as requiring a minimum average daily trading volume (e.g., $2M ADV) and potentially excluding microcaps to ensure the included securities are tradable and to avoid issues associated with smaller, less liquid stocks.

## Step 2 Outlier Removal

Before applying the primary momentum screen, the process involves an outlier removal step to enhance the robustness of the signal. Specifically, the strategy eliminates firms that fall into the lowest 5% of the universe based on either their 6-month momentum or their 9-month momentum. This screen is designed to remove stocks that may appear strong on the primary 12-month metric but show signs of weakness over other, shorter timeframes.

## Step 3 Primary Momentum Screen

The core of the process is the primary momentum screen, which identifies the top-performing stocks. This is done by ranking stocks based on their intermediate-term momentum, calculated as the cumulative total return over the past 12 months, excluding the most recent month (known as '2-12' or '12-2' momentum). The strategy then selects the top decile or a fixed number of stocks (e.g., top 100) from this ranking to form the initial high-momentum portfolio.

## Step 4 Momentum Quality Screen

After identifying the high-momentum stocks, a final screening layer is applied to select for 'high-quality' momentum. This step aims to create a more concentrated and robust portfolio (e.g., 50 stocks) by filtering the high-momentum candidates using metrics designed to identify smoother, more persistent trends. The primary quality metric used is the 'Frog-in-the-Pan' (FIP) or Information Discreteness (ID) score, which penalizes stocks with erratic, jumpy returns. Other quality metrics like the consistency of returns (e.g., requiring at least 8 of the past 11 months to have positive returns) are also used to refine the selection and construct the final equal-weighted portfolio.


# Alpha Architect Intermediate Momentum Signal

Alpha Architect's core momentum signal is the intermediate-term momentum, specifically calculated as the total return over the past 12 months while excluding the most recent month's return. This is commonly referred to as '2-12' or '12-2' momentum. The formula is S_i = Π_{m=2}^{12}(1+R_{i,t−m}) − 1, where R is the monthly total return for stock i at time t. The exclusion of the most recent month (t-1) is a critical feature designed to mitigate the effects of the short-term reversal phenomenon, where stocks that perform very well in the most recent month tend to underperform in the subsequent month. This '2-12' signal forms the basis for their primary stock ranking before quality screens are applied.

# Alpha Architect Frog In The Pan Details

## Metric Name

Frog-in-the-Pan (FIP), also referred to as Information Discreteness (ID).

## Formula

The Information Discreteness (ID) is calculated using the returns from the intermediate momentum lookback period (months t-2 to t-12). The formula is: ID = sign(PRET) × (% negative return periods − % positive return periods). Here, PRET is the past return over the 11-month period (2-12 momentum), '%negative' is the count of months with negative returns divided by 11, and '%positive' is the count of months with positive returns divided by 11.

## Interpretation

The metric is interpreted as a measure of momentum quality or path smoothness. A lower, more negative value for ID is considered better, as it indicates 'continuous information' or high-quality momentum. A negative ID means that a stock with positive overall momentum achieved its gains through a higher percentage of positive-return months than negative-return months, suggesting a smoother, more consistent trend. Conversely, a high positive ID suggests 'discrete information,' where a stock's momentum is driven by a few large, jumpy positive months, which is considered lower quality and less persistent.

## Purpose

The primary purpose of using the FIP/ID metric is to differentiate between high-momentum stocks and identify those with more persistent, less erratic, and therefore higher-quality price trends. By filtering for stocks with low (negative) ID scores, the strategy aims to avoid stocks whose strong performance is due to a few discrete information events (e.g., a single large price jump) and instead focus on stocks exhibiting a steady, continuous uptrend. This is believed to account for a significant portion of the momentum premium and helps in constructing a more robust portfolio that is less susceptible to momentum crashes.


# Alpha Architect Other Quality Metrics

In addition to the Frog-in-the-Pan (FIP) metric, Alpha Architect employs other measures to identify 'high-quality' momentum stocks. These include:

1.  **Consistency of Returns (Sign-Count):** This metric, inspired by Grinblatt & Moskowitz, assesses the consistency of a stock's performance. A common implementation requires that for a stock to be considered high quality, it must have had positive returns in at least 8 of the past 12 months (specifically, the 11-month period from t-2 to t-12 used for the momentum calculation). This filter ensures that the momentum is not the result of one or two outlier months but is instead built on a more consistent pattern of positive performance.

2.  **Trend Clarity (R-squared):** This metric measures the 'clarity' or linearity of a stock's price trend. It is calculated by performing a time-series regression of the stock's daily log prices against a time trend over the prior 12 months (approximately 252 trading days). The R-squared value from this regression indicates how well a straight line fits the price path. A higher R-squared value suggests a clearer, more defined trend. Within a pool of high-momentum stocks, those with the highest R-squared values are considered to have higher quality momentum.

# Alpha Architect Seasonal Momentum

## Key Finding

The core finding, based on academic research by Sias (2007), is that the returns to momentum strategies exhibit strong seasonality. Specifically, the average monthly return for a momentum strategy is significantly higher in quarter-ending months compared to non-quarter-ending months. The provided text quantifies this by noting an average of 310 basis points for quarter-ending months versus only 59 basis points for other months.

## Strongest Months

The seasonal effect is most pronounced in the months that conclude a calendar quarter. The strategy specifically focuses on rebalancing at the end of February, May, August, and November. The effect is noted as being particularly strong in December.

## Proposed Cause

The hypothesized reason for this seasonality is linked to the behavior of institutional investors. Two main drivers are proposed: 1) 'Window-dressing,' where fund managers buy recent winners towards the end of a reporting period (quarter-end) to make their portfolios look better. 2) Tax-loss selling, which can affect asset prices around year-end and subsequently influence momentum patterns, particularly in December and January.

## Implementation Timing

The practical application of this finding is to align the portfolio's rebalancing schedule with this seasonal pattern. Alpha Architect's Quantitative Momentum system implements this by rebalancing the portfolio at the close of the last trading day of the strong seasonal months: February, May, August, and November. This timing is designed to capture the heightened momentum premium observed during these specific periods.


# Academic Jegadeesh Titman Momentum

The foundational cross-sectional momentum strategy, as pioneered by Jegadeesh and Titman (1993), involves ranking securities based on their past returns over a specific lookback period and constructing a portfolio that goes long the top performers ('winners') and short the bottom performers ('losers'). The portfolio is typically rebalanced on a monthly basis. 

Key parameterizations define the lookback period and the 'skip' period. The most common is the '12-2' or '12-1' momentum (the original paper used '12-1', but subsequent research, including AQR's, often uses a skip month). This involves:
1.  **Lookback Period (J):** Calculating the cumulative return for each stock over the past J months. Common values are J=12, 9, or 6.
2.  **Skip Period (K):** Excluding the most recent K months from the calculation to mitigate the effects of short-term reversals. A typical value is K=1, meaning the return from month t-1 is ignored. The signal is thus calculated over months t-12 to t-2.

Standard implementations include:
*   **'12-2' Momentum:** For each stock at the end of month 't', calculate the cumulative total return from the start of month 't-12' to the end of month 't-2'. This is the most widely cited academic and practitioner standard.
*   **'6-2' Momentum:** A shorter-term variant calculating cumulative returns from month 't-6' to 't-2'.
*   **'12-1' Momentum (No Skip):** The original formulation that calculates the cumulative return over the past 12 months, including the most recent month (t-12 to t-1). This is noted to be noisier due to short-term reversal effects.

**Portfolio Construction:**
After calculating the momentum score for all stocks in the universe, they are ranked. A long-short portfolio is then formed by:
*   **Long Leg:** Buying the top decile or quintile of stocks (the 'winners').
*   **Short Leg:** Shorting the bottom decile or quintile of stocks (the 'losers').
Positions within each leg are often equally weighted, though practitioners like AQR use rank-based weighting where weights are proportional to the rank of the momentum score.

# Academic Dual Momentum Details

## Relative Momentum Component

The first component is relative, or cross-sectional, momentum. This involves comparing the performance of assets within a defined universe against each other. For an equity strategy, this means ranking all stocks in the universe based on their past performance over a specified lookback period (e.g., the past 12 months, skipping the most recent month, known as '12-2' momentum). The strategy then selects the top-performing stocks from this ranking, for example, the top decile, to form the potential long portfolio.

## Absolute Momentum Component

The second component is an absolute momentum filter, also known as a trend filter. After an asset or a basket of assets has been selected via the relative momentum rule, its own past performance is checked against a neutral benchmark, typically a risk-free asset like T-bills. The rule is to check if the asset's total return over the lookback period (e.g., the past 12 months) is positive. If the return is greater than zero (or greater than the T-bill return), the trend is considered positive.

## Switching Rule

The switching rule combines the relative and absolute components to make the final allocation decision. If the asset(s) selected by the relative momentum component also pass the absolute momentum filter (i.e., their trend is positive), the strategy invests in them. However, if the absolute momentum filter is negative (i.e., the asset's return is less than or equal to zero), the strategy switches out of the risky asset and allocates the capital to a safe-haven or 'risk-off' asset, such as aggregate bonds or cash. This rule is designed to avoid holding assets that are strong relative to peers but are still in an overall downtrend.

## Lookback Period

The typical lookback period used for both the relative and absolute momentum calculations in the Antonacci-style dual momentum strategy is 12 months. For the relative component, it is common to use the '12-2' convention (past 12 months of returns, skipping the most recent month) to select the top assets. For the absolute momentum filter, the total return over the past 12 months ('12-1') is typically used to determine if the trend is positive or negative.


# Academic Idiosyncratic Momentum Details

Idiosyncratic Momentum, also known as Residual Momentum, is a refined momentum strategy proposed by Blitz, Huij, and Martens (2011). It aims to isolate the portion of a stock's momentum that is not explained by common risk factors like market, size, and value, and is therefore 'idiosyncratic' to the firm itself. The core idea is that this residual momentum is more persistent and less prone to the 'crashes' that can affect standard total return momentum.

The process for calculating it involves two main steps:
1.  **Calculate Residual Returns:** First, each stock's historical returns (e.g., over the past 36-60 months) are regressed against a multi-factor asset pricing model. Common models used are the Fama-French 3-Factor model (which includes market, size (SMB), and value (HML) factors) or the Carhart 4-Factor model (which adds the standard momentum factor, WML). The unexplained portion of the returns from this regression, known as the residuals (epsilon, ε), represents the stock's idiosyncratic returns.

2.  **Apply Momentum Strategy to Residuals:** A standard cross-sectional momentum strategy is then applied not to the total returns, but to the series of calculated residual returns. For example, a '12-2' momentum score is computed using the cumulative idiosyncratic returns from months t-12 to t-2. The resulting residual momentum scores are often standardized by the volatility (standard deviation) of the stock's own residual returns over the lookback period. Stocks are then ranked based on this standardized residual momentum, and a long-short portfolio is formed by buying the top-ranked stocks and shorting the bottom-ranked ones.

# Risk Overlay Volatility Scaling Details

## Objective

The primary goal of a volatility scaling overlay is to manage risk by maintaining a more constant level of portfolio volatility over time. This approach aims to improve risk-adjusted returns (Sharpe ratio) and, crucially, to mitigate the impact of the severe, periodic drawdowns known as 'momentum crashes' by systematically reducing exposure when volatility is high and increasing it when volatility is low.

## Scaling Formula

The portfolio's exposure is adjusted by scaling the position size by the inverse of its recently realized volatility. A common implementation is to set the position weight proportional to a target volatility divided by the measured realized volatility (e.g., weight = target_vol / realized_vol). For a factor portfolio, this can be implemented by scaling the next period's return by the inverse of the realized variance from the prior period (e.g., r_vm,t+1 = r_t+1 / σ̂_t^2), as proposed by Moreira & Muir.

## Volatility Measurement Period

The lookback period for calculating realized volatility varies across different research. Common examples include using the daily returns from the previous month (e.g., 22 trading days, as in Moreira & Muir), the standard deviation of returns over the prior 6 months (or 126 trading days, as in Barroso & Santa-Clara), or an Exponentially Weighted Moving Average (EWMA) of daily returns with a center-of-mass of 60 days (as used by AQR for individual instruments). For portfolio-level scaling, a longer lookback, such as a 36-month rolling covariance matrix, may be used.

## Source Research

The foundational academic research for this risk management technique includes 'Momentum has its moments' by Barroso & Santa-Clara (2015) and 'Volatility-Managed Portfolios' by Moreira & Muir (2017). These papers demonstrate that systematically managing a momentum portfolio's volatility can dramatically improve its performance and reduce tail risk.


# Risk Overlay Momentum Crash Protection

Research by Daniel & Moskowitz (2016) provides a detailed analysis of momentum crashes, identifying the specific market environments in which they are most probable. Crashes are not random but tend to occur following a prolonged bear market (e.g., when the market's return over the prior two years is negative) and during a subsequent sharp market rebound. In these scenarios, the 'loser' stocks that momentum strategies are shorting are often highly distressed, high-beta firms that rebound violently when market sentiment turns, causing massive losses for the momentum factor. The research suggests that these crash periods can be predicted to some extent, allowing for dynamic risk management. Potential timing signals include monitoring the state of the market (e.g., a negative 24-month lagged market return) combined with high ex-ante volatility. A practical overlay based on this research would involve reducing or hedging momentum exposure when these specific conditions are met. For example, an investor might cut momentum exposure in half when the market's past 24-month return is negative and the current month's market return is strongly positive (e.g., > +5%). Daniel & Moskowitz show that such a dynamic strategy, which adjusts exposure based on these conditional forecasts, significantly outperforms static momentum strategies and even constant-volatility strategies.

# Generic Trend Following Signals

Beyond academic time-series momentum (which is based on the sign of past total returns), a variety of other signals are commonly used in trend-following strategies. These signals are often based on price levels and their relationship to historical prices or moving averages.

1.  **Moving Average (MA) Crossover Systems:** These signals generate buy or sell orders based on the relationship between two moving averages of different lengths, or between the price and a single moving average.
    *   **Golden Cross / Death Cross:** This is a widely followed signal using a short-term MA (e.g., 50-day) and a long-term MA (e.g., 200-day). A 'Golden Cross' occurs when the short-term MA crosses above the long-term MA, generating a buy signal. A 'Death Cross' is the opposite, with the short-term MA crossing below the long-term MA, generating a sell or short signal. For monthly data, proxies like a 10-month and 40-month SMA can be used.
    *   **Dual MA Systems:** Similar to the above, but can use different periods, such as a 5-month vs. 10-month SMA crossover, to capture trends of varying speeds.
    *   **Price vs. MA:** A simpler rule is to be long when the current price is above a long-term moving average (e.g., 200-day or 10-month SMA) and flat or short when the price is below it.

2.  **Price Breakout Signals (Donchian Channels):** These signals are based on the idea that a price movement exceeding a recent high or low indicates the start of a new trend.
    *   **N-Period High/Low:** A common implementation is to buy when the current price exceeds the highest price over the past N periods (e.g., 52 weeks or 12 months). Conversely, a sell or short signal is generated when the price falls below the lowest price over a certain period (e.g., 6 months). This is often called a 'Donchian Channel' breakout.

# Momentum Signal Ideas Database

## Signal Id

1

## Signal Name

Jegadeesh-Titman 12-2 Total Return Momentum

## Source Research

Jegadeesh & Titman 1993

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S_i = Σ_{m=2}^{12}(1+R_{i,t−m}) − 1, where R is the monthly total return.

## Parameter Variations

Lookback: 11 months (months t-12 to t-2). Skip: 1 month (month t-1). Holding Period: 1 month.

## Portfolio Construction Notes

Rank stocks based on the score S_i. Form a long-short portfolio by going long the top decile and short the bottom decile. Stocks within deciles can be equal-weighted or rank-weighted.

## Risk Management Notes

The 1-month skip is a basic risk management technique to avoid the short-term reversal effect. No other explicit risk management is part of the base signal.

## Signal Id

2

## Signal Name

Jegadeesh-Titman 6-2 Momentum

## Source Research

Jegadeesh & Titman 1993

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S_i = Σ_{m=2}^{6}(1+R_{i,t−m}) − 1.

## Parameter Variations

Lookback: 5 months (months t-6 to t-2). Skip: 1 month (month t-1). Holding Period: 1 month.

## Portfolio Construction Notes

Long top decile, short bottom decile, based on the 6-2 momentum score.

## Risk Management Notes

Uses a shorter lookback period to test intermediate-term momentum. Includes the standard 1-month skip.

## Signal Id

3

## Signal Name

Jegadeesh-Titman 3-2 Momentum

## Source Research

Jegadeesh & Titman 1993

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S_i = Σ_{m=2}^{3}(1+R_{i,t−m}) − 1.

## Parameter Variations

Lookback: 2 months (months t-3 to t-2). Skip: 1 month (month t-1). Holding Period: 1 month.

## Portfolio Construction Notes

Long top decile, short bottom decile. Used to test shorter-term intermediate momentum effects.

## Risk Management Notes

Very short lookback, may be more sensitive to noise. Includes the standard 1-month skip.

## Signal Id

4

## Signal Name

Jegadeesh-Titman 9-2 Momentum

## Source Research

Jegadeesh & Titman 1993

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S_i = Σ_{m=2}^{9}(1+R_{i,t−m}) − 1.

## Parameter Variations

Lookback: 8 months (months t-9 to t-2). Skip: 1 month (month t-1). Holding Period: 1 month.

## Portfolio Construction Notes

Long top decile, short bottom decile, based on the 9-2 momentum score.

## Risk Management Notes

Standard cross-sectional momentum with a 1-month skip.

## Signal Id

5

## Signal Name

12-1 Momentum (No Skip)

## Source Research

Jegadeesh & Titman 1993

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S_i = Σ_{m=1}^{12}(1+R_{i,t−m}) − 1.

## Parameter Variations

Lookback: 12 months (months t-12 to t-1). Skip: 0 months. Holding Period: 1 month.

## Portfolio Construction Notes

Long top decile, short bottom decile. This variant is used to test the impact of the short-term reversal effect by not skipping the most recent month.

## Risk Management Notes

Expected to have higher turnover and be more susceptible to noise from short-term reversal compared to the 12-2 version.

## Signal Id

6

## Signal Name

6-1 Momentum (No Skip)

## Source Research

Jegadeesh & Titman 1993

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S_i = Σ_{m=1}^{6}(1+R_{i,t−m}) − 1.

## Parameter Variations

Lookback: 6 months (months t-6 to t-1). Skip: 0 months. Holding Period: 1 month.

## Portfolio Construction Notes

Long top decile, short bottom decile. Tests the impact of including the most recent month's return in a shorter lookback period.

## Risk Management Notes

Susceptible to short-term reversal effects due to the lack of a skip month.

## Signal Id

7

## Signal Name

12-3 Momentum (2-Month Skip)

## Source Research

Generic Variation

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S_i = Σ_{m=3}^{12}(1+R_{i,t−m}) − 1.

## Parameter Variations

Lookback: 10 months (months t-12 to t-3). Skip: 2 months (t-1, t-2). Holding Period: 1 month.

## Portfolio Construction Notes

Long top decile, short bottom decile. Tests the effect of a longer skip period to further mitigate short-term reversal.

## Risk Management Notes

A longer skip period may reduce exposure to short-term reversal but could also lead to slower signal adaptation.

## Signal Id

8

## Signal Name

12-4 Momentum (3-Month Skip)

## Source Research

Generic Variation

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S_i = Σ_{m=4}^{12}(1+R_{i,t−m}) − 1.

## Parameter Variations

Lookback: 9 months (months t-12 to t-4). Skip: 3 months (t-1, t-2, t-3). Holding Period: 1 month.

## Portfolio Construction Notes

Long top decile, short bottom decile. An even more conservative approach to avoiding short-term reversal.

## Risk Management Notes

Extends the skip period to three months, potentially creating a more stable but lagging signal.

## Signal Id

11

## Signal Name

AQR VME Rank-Weighted Momentum

## Source Research

Asness, Moskowitz, Pedersen (2013)

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Compute momentum score S_i (e.g., 12-2). Weight w_i = c_t * (rank(S_i) - mean(rank)), where c_t is a scaling factor.

## Parameter Variations

Lookback: 12-2 is standard. Holding Period: 1 month.

## Portfolio Construction Notes

Weights are proportional to the deviation from the average rank. The portfolio is scaled to be dollar-neutral ($1 long, $1 short). This provides more granular weighting than simple decile sorts.

## Risk Management Notes

Dollar-neutral construction hedges out broad market movements. The rank-based weighting reduces the influence of extreme outliers in momentum scores.

## Signal Id

13

## Signal Name

Volatility-Normalized Momentum Score

## Source Research

Generic Variation

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S'_i = S_i / σ_i,12m, where S_i is a standard momentum score (e.g., 12-2) and σ_i,12m is the stock's 12-month realized volatility.

## Parameter Variations

Momentum Lookback: 12-2. Volatility Lookback: 12 months. Holding Period: 1 month.

## Portfolio Construction Notes

Rank stocks based on the volatility-normalized score S'_i. This prioritizes stocks with higher risk-adjusted momentum.

## Risk Management Notes

This is a form of risk management at the signal level, penalizing stocks that achieved high momentum with excessively high volatility.

## Signal Id

17

## Signal Name

Industry-Neutral Momentum

## Source Research

Generic Variation

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Within each industry (e.g., GICS sector), calculate a standard momentum score (e.g., 12-2) and rank stocks relative to their industry peers.

## Parameter Variations

Lookback: 12-2. Holding Period: 1 month.

## Portfolio Construction Notes

Form a portfolio by going long the top quantile and short the bottom quantile within each industry. The combined portfolio is industry-neutral, avoiding large industry bets.

## Risk Management Notes

Neutralizes exposure to industry-wide momentum, isolating stock-specific momentum. Often combined with sector weight caps (e.g., max 20% per sector) as an additional risk control.

## Signal Id

21

## Signal Name

Log-Return Sum Momentum

## Source Research

Generic Variation

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S_i = Σ_{m=2}^{12} ln(1+R_{i,t−m}).

## Parameter Variations

Lookback: 11 months (t-12 to t-2). Skip: 1 month. Holding Period: 1 month.

## Portfolio Construction Notes

Rank stocks based on the sum of their log returns. This method is less sensitive to the effects of large positive returns compared to cumulative arithmetic returns.

## Risk Management Notes

Using log returns naturally dampens the impact of extreme positive outliers in the lookback period.

## Signal Id

25

## Signal Name

Triple-Horizon Blended Momentum

## Source Research

Generic Variation

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S_i = (1/3) * (3-2 return) + (1/3) * (6-2 return) + (1/3) * (12-2 return).

## Parameter Variations

Lookbacks: 3-2, 6-2, and 12-2. Skip: 1 month. Holding Period: 1 month.

## Portfolio Construction Notes

Rank stocks based on the blended score. This creates a more robust signal by diversifying across different momentum lookback periods.

## Risk Management Notes

Diversifying across horizons can improve consistency as the optimal momentum lookback period can change over time.

## Signal Id

34

## Signal Name

Residual Momentum (Blitz-Huij-Martens)

## Source Research

Blitz, Huij, Martens (2011)

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

1. Estimate a factor model (e.g., Fama-French 3-factor) over a 36-60 month period to get residual returns ε_i,t. 2. Compute a momentum score on these residuals, e.g., 12-2 residual momentum. 3. Standardize the score by the standard deviation of the residuals over the lookback period.

## Parameter Variations

Factor Model Lookback: 36-60 months. Momentum Lookback: 12-2 on residuals. Holding Period: 1 month.

## Portfolio Construction Notes

Rank stocks based on the standardized residual momentum score. This isolates idiosyncratic momentum from common factor exposures.

## Risk Management Notes

The resulting momentum factor is shown to be more stable and less prone to crashes than total return momentum because it strips out market, value, and size effects.

## Signal Id

41

## Signal Name

Time-Series Momentum (12-Month Sign)

## Source Research

Moskowitz, Ooi, Pedersen (2012)

## Strategy Category

Time-Series Momentum

## Signal Construction Formula

For each stock i, signal s_i = sign(Σ_{m=1}^{12}(1+R_{i,t−m}) − 1). This is the sign of the past 12-month total return.

## Parameter Variations

Lookback: 12 months (no skip). Holding Period: 1 month.

## Portfolio Construction Notes

For each stock, go long if the signal is positive. Go flat (for long-only) or short (for long-short) if the signal is negative. This is an absolute, not relative, signal.

## Risk Management Notes

This signal inherently de-risks by moving to cash/flat positions when an asset's own trend is negative. Often combined with volatility scaling.

## Signal Id

48

## Signal Name

Price vs. 12-Month Simple Moving Average (SMA)

## Source Research

Generic Trend Following

## Strategy Category

Time-Series Momentum

## Signal Construction Formula

Signal is long if P_{i,t} > SMA_{12}(P_i), where P is the price and SMA_12 is the 12-month simple moving average.

## Parameter Variations

Lookback: 12 months for SMA. Holding Period: 1 month.

## Portfolio Construction Notes

For each stock, go long if its current price is above its 12-month SMA. Otherwise, go flat or short.

## Risk Management Notes

A classic trend-following rule that exits positions when the long-term trend, as defined by the SMA, is broken.

## Signal Id

49

## Signal Name

Faber-Style 10-Month SMA Trend

## Source Research

Meb Faber

## Strategy Category

Time-Series Momentum

## Signal Construction Formula

Signal is long if P_{i,t} > SMA_{10}(P_i).

## Parameter Variations

Lookback: 10 months for SMA. Holding Period: 1 month.

## Portfolio Construction Notes

For each stock, go long if its price is above its 10-month SMA. Otherwise, go flat or short. This is a common rule in tactical asset allocation applied here to single stocks.

## Risk Management Notes

Similar to the 12-month SMA rule, this acts as a trend filter to avoid holding assets in a downtrend.

## Signal Id

50

## Signal Name

Dual MA Crossover (5/10 Months)

## Source Research

Generic Trend Following

## Strategy Category

Time-Series Momentum

## Signal Construction Formula

Signal is long if SMA_5(P_i) > SMA_10(P_i).

## Parameter Variations

Lookbacks: 5-month SMA and 10-month SMA. Holding Period: 1 month.

## Portfolio Construction Notes

Go long when the shorter-term moving average crosses above the longer-term moving average. Exit when it crosses below.

## Risk Management Notes

MA crossover systems are designed to capture trends and avoid prolonged drawdowns, but can be prone to whipsaws in sideways markets.

## Signal Id

53

## Signal Name

Donchian 12-Month Breakout

## Source Research

Generic Trend Following

## Strategy Category

Time-Series Momentum

## Signal Construction Formula

Signal is long if P_{i,t} ≥ max(P_{i,t−1...t−12}).

## Parameter Variations

Lookback: 12 months for high. Holding Period: 1 month (or until exit rule is met).

## Portfolio Construction Notes

Go long when the price reaches a new 12-month high. A common exit rule is to sell when the price breaks a 6-month low.

## Risk Management Notes

A classic breakout strategy. The exit rule (e.g., breaking a 6-month low) is a critical risk management component to lock in profits or cut losses.

## Signal Id

61

## Signal Name

Alpha Architect Core Momentum (2-12)

## Source Research

Alpha Architect

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S_i = Σ_{m=2}^{12}(1+R_{i,t−m}) − 1.

## Parameter Variations

Lookback: 11 months (t-12 to t-2). Skip: 1 month. Holding Period: 1 month or 3 months (quarterly rebalance).

## Portfolio Construction Notes

Rank stocks on the 2-12 momentum score. Select the top N (e.g., 50-100) stocks for a long-only, equal-weighted portfolio. Often combined with quality filters.

## Risk Management Notes

Uses the standard 1-month skip. The strategy is often layered with liquidity screens, quality filters (FIP, 8-of-12), and industry caps.

## Signal Id

62

## Signal Name

Alpha Architect '8-of-12' Positive Months Filter

## Source Research

Alpha Architect

## Strategy Category

Momentum Quality

## Signal Construction Formula

Quality_flag = 1 if count({R_{i,t−m}>0 for m=2..12}) ≥ 8, else 0.

## Parameter Variations

Lookback: 11 months (t-12 to t-2).

## Portfolio Construction Notes

Used as a filter. After identifying high momentum stocks (e.g., top decile on 2-12 score), only keep those where Quality_flag = 1.

## Risk Management Notes

This is a quality filter designed to ensure the momentum was achieved with some consistency ('smoothness') rather than one or two large price jumps. It helps avoid 'lottery-like' stocks.

## Signal Id

63

## Signal Name

Alpha Architect FIP/ID Quality Metric

## Source Research

Alpha Architect

## Strategy Category

Momentum Quality

## Signal Construction Formula

PRET = Σ_{m=2}^{12}(1+R_{i,t−m}) − 1; pos% = count(R>0)/11; neg% = count(R<0)/11; ID = sign(PRET) × (neg% − pos%).

## Parameter Variations

Lookback: 11 months (t-12 to t-2).

## Portfolio Construction Notes

Lower (more negative) ID scores are better, indicating 'continuous' or high-quality momentum. Used as a secondary sort within a high momentum universe to select the highest quality names.

## Risk Management Notes

The 'Frog-in-the-Pan' (FIP) or 'Information Discreteness' (ID) metric is a risk filter to identify stocks with smooth, consistent trends versus those with discrete, jumpy returns, which are more prone to crashing.

## Signal Id

65

## Signal Name

Alpha Architect Trend Clarity (R^2) Filter

## Source Research

Alpha Architect

## Strategy Category

Momentum Quality

## Signal Construction Formula

Regress daily log price on a time trend over the prior 12 months (approx. 252 days). The R^2 of this regression is the trend clarity score.

## Parameter Variations

Lookback: 12 months of daily data.

## Portfolio Construction Notes

Within a universe of high momentum stocks, select those with the highest R^2 scores (e.g., top quintile of R^2). A higher R^2 indicates a smoother, more linear trend.

## Risk Management Notes

Similar to FIP/ID, this is a quality filter that favors stocks with less erratic price paths, which is a form of risk management.

## Signal Id

68

## Signal Name

Alpha Architect Seasonal Rebalance Timing

## Source Research

Alpha Architect

## Strategy Category

Portfolio Construction

## Signal Construction Formula

N/A - This is a timing rule, not a signal formula.

## Parameter Variations

Rebalance Frequency: Quarterly.

## Portfolio Construction Notes

Execute portfolio rebalances only at the month-ends of February, May, August, and November. This aligns with research showing stronger momentum effects in quarter-ending months.

## Risk Management Notes

Reduces turnover compared to monthly rebalancing. Aims to capture a documented seasonal anomaly in momentum returns.

## Signal Id

70

## Signal Name

January Effect Momentum Adjustment

## Source Research

Alpha Architect

## Strategy Category

Risk Overlay

## Signal Construction Formula

N/A - This is a portfolio weighting rule.

## Parameter Variations

Timing: Applies only in January.

## Portfolio Construction Notes

In the month of January, reduce the weight of the long momentum portfolio (e.g., by 50%) and allocate the difference to cash or another strategy.

## Risk Management Notes

This is a tactical adjustment to mitigate the 'January effect,' where momentum strategies have historically underperformed.

## Signal Id

74

## Signal Name

AQR VME Cross-Sectional Momentum

## Source Research

Asness, Moskowitz, Pedersen (2013)

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Weight w_i = c_t * (rank(S_i) - mean(rank)), where S_i is the 12-2 momentum score.

## Parameter Variations

Lookback: 12-2. Holding Period: 1 month.

## Portfolio Construction Notes

Construct a dollar-neutral long-short portfolio where weights are based on normalized ranks. The scaling factor c_t ensures the portfolio is $1 long and $1 short.

## Risk Management Notes

The rank-based weighting scheme prevents extreme outliers from dominating the portfolio. Dollar-neutral construction provides a hedge against market-wide movements.

## Signal Id

76

## Signal Name

AQR Time-Series Momentum (12m) with 40% Volatility Target

## Source Research

Moskowitz, Ooi, Pedersen (2012)

## Strategy Category

Time-Series Momentum

## Signal Construction Formula

Position direction = sign(Past 12-month excess return). Position size w_i ∝ 0.40 / σ̂_i, where σ̂_i is the ex-ante annualized volatility.

## Parameter Variations

Lookback: 12 months. Volatility Lookback: EWMA with 60-day center of mass on daily returns.

## Portfolio Construction Notes

For each asset, take a long or short position based on its own past 12-month trend. The size of the position is scaled to target a 40% annualized volatility for that specific instrument.

## Risk Management Notes

This is a core risk management technique in trend following. Each position is sized to contribute a similar amount of risk, and the overall portfolio volatility can then be managed.

## Signal Id

79

## Signal Name

AQR Diversified TSMOM Across Horizons

## Source Research

Hurst, Ooi, Pedersen (2013)

## Strategy Category

Time-Series Momentum

## Signal Construction Formula

Create three separate TSMOM strategies with different lookbacks (1-month, 3-month, 12-month). The final signal is the average of the signals/returns from these three strategies.

## Parameter Variations

Lookbacks: 1 month, 3 months, 12 months.

## Portfolio Construction Notes

Average the positions from the three different horizon-based strategies. This creates a more robust trend signal that is less dependent on a single lookback period.

## Risk Management Notes

Diversifying across signal speeds (horizons) improves the strategy's robustness and consistency through different market regimes.

## Signal Id

80

## Signal Name

AQR Portfolio Volatility Targeting (10%)

## Source Research

Hurst, Ooi, Pedersen (2014)

## Strategy Category

Risk Overlay

## Signal Construction Formula

After constructing the portfolio (e.g., from TSMOM signals), estimate the portfolio's ex-ante annualized volatility (σ̂_p) using a covariance matrix. The final portfolio leverage is scaled by (10% / σ̂_p).

## Parameter Variations

Volatility Target: 10% annualized. Covariance Lookback: Typically 36 months of monthly returns.

## Portfolio Construction Notes

This is an overlay applied to the entire portfolio. The gross exposure of the portfolio is dynamically adjusted each month to maintain a constant level of target risk.

## Risk Management Notes

This is a key risk management technique that aims to provide a stable risk profile for the overall strategy, reducing exposure during volatile periods and increasing it during calm periods.

## Signal Id

81

## Signal Name

AQR EWMA(60d) Volatility Estimator

## Source Research

Hurst, Ooi, Pedersen (2013)

## Strategy Category

Risk Management

## Signal Construction Formula

σ̂^2_t = 261 * Σ_{i=0 to ∞} (1−δ)δ^i * (r_{t−1−i} − r̄_t)^2, with parameters chosen such that the center of mass is 60 trading days.

## Parameter Variations

Center of Mass: 60 days.

## Portfolio Construction Notes

This formula is used to calculate the ex-ante volatility (σ̂_i) for individual assets, which is then used in the denominator for position sizing (e.g., to hit a 40% per-instrument vol target).

## Risk Management Notes

The exponentially weighted moving average (EWMA) puts more weight on recent data, making the volatility estimate more responsive to changes in the market environment.

## Signal Id

85

## Signal Name

Barroso-Santa-Clara Constant-Volatility Momentum

## Source Research

Barroso & Santa-Clara (2015)

## Strategy Category

Risk Overlay

## Signal Construction Formula

Construct a standard momentum factor portfolio (WML - Winners-Minus-Losers). Scale the monthly position in WML by k / σ̂_{WML, 6m}, where σ̂ is the realized volatility of the WML portfolio over the prior 6 months.

## Parameter Variations

Volatility Lookback: 6 months (approx. 126 trading days). Target Volatility: k is chosen to set a target, e.g., 12% annualized.

## Portfolio Construction Notes

Instead of holding a static $1 long/$1 short momentum portfolio, the total exposure is dynamically adjusted to maintain a constant level of risk.

## Risk Management Notes

This method was shown to significantly reduce the severity of momentum crashes by de-levering the strategy during periods of high momentum volatility.

## Signal Id

88

## Signal Name

Moreira-Muir Volatility-Managed Portfolio (1/var scaling)

## Source Research

Moreira & Muir (2017)

## Strategy Category

Risk Overlay

## Signal Construction Formula

Scale the return of a factor portfolio (r_{t+1}) by the inverse of its realized variance from the prior month (σ̂^2_t). Managed return r_vm,t+1 = r_{t+1} / (c * σ̂^2_t).

## Parameter Variations

Volatility Lookback: 1 month (approx. 22 trading days) of daily returns to calculate variance.

## Portfolio Construction Notes

This is an aggressive form of volatility timing that scales exposure by inverse variance (rather than inverse volatility). The constant c is chosen to target a desired average level of volatility.

## Risk Management Notes

Significantly improves the Sharpe ratio of various factors, including momentum, by aggressively cutting risk when volatility spikes.

## Signal Id

90

## Signal Name

Daniel-Moskowitz Momentum Crash Protection Overlay

## Source Research

Daniel & Moskowitz (2016)

## Strategy Category

Risk Overlay

## Signal Construction Formula

Identify a 'crash state' when two conditions are met: 1) The market is in a bear state (past 24-month market return < 0), and 2) The market is rebounding sharply (high contemporaneous market return).

## Parameter Variations

Bear Market Lookback: 24 months.

## Portfolio Construction Notes

When a crash state is predicted, significantly reduce or exit the long-short momentum (WML) position for the next month.

## Risk Management Notes

This is a tactical risk model specifically designed to forecast and avoid the conditions that lead to momentum crashes, which often occur during sharp market reversals after a prolonged bear market.

## Signal Id

93

## Signal Name

VIX Proxy Crisis Throttle

## Source Research

Generic Risk Management

## Strategy Category

Risk Overlay

## Signal Construction Formula

Calculate a proxy for market volatility (e.g., realized volatility of the market index over the past month). If this volatility is in its top quintile historically, it signals a crisis state.

## Parameter Variations

Volatility Lookback: 1 month.

## Portfolio Construction Notes

In a crisis state, reduce the gross exposure of the momentum portfolio by a fixed amount (e.g., 50%).

## Risk Management Notes

A simple, heuristic-based risk management rule to de-risk the portfolio during periods of extreme market-wide stress.

## Signal Id

109

## Signal Name

Quarter-End Rebalance Policy

## Source Research

Alpha Architect

## Strategy Category

Portfolio Construction

## Signal Construction Formula

N/A - Timing rule.

## Parameter Variations

Rebalance Months: February, May, August, November.

## Portfolio Construction Notes

The momentum portfolio is held static within the quarter and only rebalanced at the end of quarter-ending months.

## Risk Management Notes

This strategy aims to capture the documented seasonal strength of momentum around quarter-ends, potentially driven by institutional window-dressing. It also significantly reduces turnover and associated trading costs.

## Signal Id

114

## Signal Name

Antonacci-Style Dual Momentum

## Source Research

Gary Antonacci

## Strategy Category

Hybrid Momentum

## Signal Construction Formula

1. Relative Momentum: Rank stocks by a relative momentum score (e.g., 12-2) and select the top decile. 2. Absolute Momentum Filter: For the selected stocks, only include those that also have a positive absolute momentum signal (e.g., past 12-1 return > 0).

## Parameter Variations

Relative Lookback: 12-2. Absolute Lookback: 12-1.

## Portfolio Construction Notes

The portfolio holds the top relative performers, but only if their own absolute trend is positive. If a stock fails the absolute momentum filter, its weight is allocated to cash or a risk-free asset.

## Risk Management Notes

Dual momentum combines the stock-selection benefits of relative momentum with the defensive, crash-avoidance properties of absolute momentum (trend following).

## Signal Id

118

## Signal Name

52-Week High Distance

## Source Research

Generic Trend Following

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S_i = P_{i,t} / max(P_{i,t−1..t−12}) − 1.

## Parameter Variations

Lookback: 12 months (52 weeks).

## Portfolio Construction Notes

The score measures how close the current price is to its 52-week high. A score of 0 means it's at a new high. Can be used as a ranking signal, where stocks with scores closer to 0 are ranked higher.

## Risk Management Notes

This is a form of breakout signal that favors stocks exhibiting strong upward price trajectory.

## Signal Id

123

## Signal Name

Standardized Residual 12-2 Momentum

## Source Research

Blitz, Huij, Martens (2011)

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

S_i = [Σ_{m=2}^{12}(1+ε_{i,t−m}) − 1] / σ_ε,12m, where ε are residuals from a factor model and σ_ε is the standard deviation of those residuals.

## Parameter Variations

Factor Model Lookback: 36-60 months. Momentum Lookback: 12-2 on residuals.

## Portfolio Construction Notes

Rank stocks based on their standardized idiosyncratic momentum. This isolates the momentum effect from common risk factors.

## Risk Management Notes

Residual momentum is found to be less exposed to momentum crashes, as these crashes are often related to reversals in common factors (like market beta) that have been stripped out.

## Signal Id

129

## Signal Name

Volatility Parity Weighting

## Source Research

Generic Risk Management

## Strategy Category

Portfolio Construction

## Signal Construction Formula

Within a basket of selected stocks (e.g., long-only momentum), set weights w_i ∝ 1 / σ_i,12m, where σ_i is the stock's historical volatility.

## Parameter Variations

Volatility Lookback: 12 months.

## Portfolio Construction Notes

After selecting stocks, this weighting scheme is applied. It gives lower weight to more volatile stocks and higher weight to less volatile stocks, such that each stock contributes roughly equally to the portfolio's overall risk.

## Risk Management Notes

This is a risk-based diversification method that prevents a few highly volatile stocks from dominating the portfolio's risk profile. It is also known as inverse-volatility weighting.

## Signal Id

130

## Signal Name

Correlation-Aware Portfolio Volatility Targeting

## Source Research

AQR

## Strategy Category

Risk Overlay

## Signal Construction Formula

1. Select stocks for the portfolio. 2. Estimate the full covariance matrix of the selected names using historical data (e.g., 36 months). 3. Use the covariance matrix to calculate the portfolio's ex-ante volatility. 4. Scale the entire portfolio to a target volatility level (e.g., 10%).

## Parameter Variations

Covariance Lookback: 36 months. Target Volatility: 10%.

## Portfolio Construction Notes

This is a more advanced version of portfolio volatility targeting that accounts for correlations between the assets, providing a more accurate risk forecast.

## Risk Management Notes

By incorporating correlations, this method can more effectively manage portfolio risk, especially in concentrated portfolios or when assets become highly correlated during market stress.

## Signal Id

133

## Signal Name

Beta-Neutral Long-Short Momentum

## Source Research

Generic Risk Management

## Strategy Category

Portfolio Construction

## Signal Construction Formula

1. Form a long portfolio of top momentum stocks and a short portfolio of bottom momentum stocks. 2. Calculate the market beta of the long leg (β_L) and the short leg (β_S). 3. Adjust the notional size of the short leg so that the portfolio's net beta (β_L - β_S) is approximately zero.

## Parameter Variations

Beta Lookback: Typically 12 to 36 months.

## Portfolio Construction Notes

This creates a pure momentum factor portfolio that has minimal exposure to the overall market's direction.

## Risk Management Notes

Beta-neutralizing is a critical step in creating a market-neutral hedge fund strategy, designed to isolate the alpha from the momentum factor itself.

## Signal Id

142

## Signal Name

Rebalance Staggering

## Source Research

Generic Implementation Detail

## Strategy Category

Portfolio Construction

## Signal Construction Formula

N/A - Implementation technique.

## Parameter Variations

Cohorts: Typically 3.

## Portfolio Construction Notes

Divide the total portfolio into multiple (e.g., 3) sub-portfolios or cohorts. Rebalance only one cohort each month on a rotating basis. For example, Cohort 1 in Jan, Cohort 2 in Feb, Cohort 3 in Mar, Cohort 1 in Apr, etc.

## Risk Management Notes

This technique smooths out turnover, reduces the market impact of large rebalancing trades, and diversifies the timing luck associated with rebalancing on a single day of the month.

## Signal Id

151

## Signal Name

Half-Life Weighted Momentum

## Source Research

Generic Variation

## Strategy Category

Cross-Sectional Momentum

## Signal Construction Formula

Score S_i = Σ_{m=2}^{12} w_m * R_{i,t−m}, where weights w_m decay exponentially, e.g., w_m ∝ λ^(m) for 0<λ<1.

## Parameter Variations

Lookback: 11 months (t-12 to t-2). Half-life parameter λ determines the rate of decay.

## Portfolio Construction Notes

Rank stocks based on the exponentially-weighted average return. This gives more importance to more recent months within the lookback period (excluding t-1).

## Risk Management Notes

This weighting scheme makes the signal more responsive to recent information than a simple average, while still considering a longer history.

