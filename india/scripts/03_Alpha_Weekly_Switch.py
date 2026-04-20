import warnings
from typing import List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

warnings.filterwarnings("ignore")

latest_df = pd.read_csv("../data/NIFTY_ALPHA_50_WEEKLY.csv")
latest_df["MOMENTUM_PERCENT_CHANGE"] = latest_df["Close"].pct_change(periods=4) * 100
latest_df["MOMENTUM_PERCENT_CHANGE"] = latest_df["MOMENTUM_PERCENT_CHANGE"].round(2)


# Filter out NaN values from the MOMENTUM_PERCENT_CHANGE column for plotting
filtered_momentum_percent_change = latest_df["MOMENTUM_PERCENT_CHANGE"].dropna()[:-84]
# Plot the distribution of the MOMENTUM_PERCENT_CHANGE column
quantiles = [0.1, 0.25, 0.3, 0.4, 0.5, 0.75, 0.9]

# Calculate the quantile values from the 'MOMENTUM_PERCENT_CHANGE' column
quantile_values = filtered_momentum_percent_change.quantile(quantiles).tolist()
quantile_map = dict(zip(quantiles, quantile_values, strict=False))
# Plot the distribution with the quantile thresholds
plt.figure(figsize=(12, 6))
sns.histplot(filtered_momentum_percent_change, bins=25, kde=True)
for idx, q_value in enumerate(quantile_values):
    plt.axvline(
        x=q_value,
        color="r",
        linestyle="--",
        label=f"Percentile: {quantiles[idx] * 100:.0f}%: {q_value}",
    )

plt.title("Distribution of MOMENTUM_PERCENT_CHANGE with Quantile Thresholds")
plt.xlabel("MOMENTUM_PERCENT_CHANGE")
plt.ylabel("Frequency")
plt.legend()
plt.show()


latest_df = latest_df[-84:]  # Exclude what was used to find the quantiles


def switch(
    latest_df,
    col_name: str = "SWITCH_DYNAMIC",
    initial_value: str = "CASH",
    to_cash: float = -1.96,
    to_momentum: float = 12.0,
) -> pd.DataFrame:
    df = latest_df.copy()
    # Remove any rows where all values are NaN before proceeding
    df.dropna(inplace=True)
    df.reset_index(drop=True, inplace=True)
    switch_list = []
    # Loop through the DataFrame to populate the SWITCH_DYNAMIC column
    # based on the thresholds
    for idx in range(len(df)):
        if idx == 0:
            switch_list.append(initial_value)
            continue
        prev_row = switch_list[idx - 1]
        current_row = df.iloc[idx]
        momentum_change = current_row.get("MOMENTUM_PERCENT_CHANGE")
        if pd.isna(momentum_change):
            switch_value = initial_value
        elif momentum_change < to_cash:
            switch_value = "CASH"
        elif momentum_change > to_momentum:
            switch_value = "MOMENTUM"
        else:
            switch_value = prev_row

        switch_list.append(switch_value)

    df[col_name] = switch_list
    return df


switch_df = switch(
    latest_df=latest_df,
    col_name="SWITCH_DYNAMIC",
    initial_value="CASH",
    to_cash=quantile_map[0.5],
    to_momentum=quantile_map[0.3],
)
switch_df = switch(
    latest_df=switch_df,
    col_name="SWITCH_DYNAMIC_OPTIMISTIC",
    initial_value="CASH",
    to_cash=quantile_map[0.5],
    to_momentum=quantile_map[0.25],
)
switch_df = switch(
    latest_df=switch_df,
    col_name="SWITCH_DYNAMIC_PESSIMISTIC",
    initial_value="CASH",
    to_cash=quantile_map[0.75],
    to_momentum=quantile_map[0.75],
)
(
    switch_df["SWITCH_DYNAMIC"].value_counts(),
    switch_df["SWITCH_DYNAMIC_OPTIMISTIC"].value_counts(),
    switch_df["SWITCH_DYNAMIC_PESSIMISTIC"].value_counts(),
)


# Modify the function to use the strategy from the previous month
# to decide the current month's returns
def add_amount_based_on_strategy(
    df: pd.DataFrame,
    strategy: str,
    initial_amount: float = 1000.0,
    momentum_col: str = "Close",
) -> pd.DataFrame:
    """
    Adds an 'AMOUNT_<STRATEGY>' column to the DataFrame based on the given
    cash-only strategy.

    Parameters:
        df (pd.DataFrame): The DataFrame to which the new column will be
            added.
        strategy (str): The strategy column based on which the amount will be
            calculated.
        initial_amount (float): The initial amount of investment. Default is
            1000 INR.
        momentum_col (str): The column representing the momentum TRI.
            Default is 'NIFTY 200 MOMENTUM 30 TRI'.

    Returns:
        pd.DataFrame: DataFrame with the new 'AMOUNT_<STRATEGY>' column added.
    """
    df_copy = df.copy()
    amount_list = [initial_amount]  # Start with the initial amount
    amount_col = f"AMOUNT_{strategy}"

    for idx in range(1, len(df)):
        prev_row = df_copy.iloc[idx - 1]
        current_row = df_copy.iloc[idx]

        # Use the strategy from the previous month to decide the current month's amount
        if prev_row[strategy] == "MOMENTUM":
            current_amount = amount_list[-1] * (
                current_row[momentum_col] / prev_row[momentum_col]
            )
        else:
            current_amount = amount_list[-1]  # In CASH, just copy the previous value

        amount_list.append(current_amount)

    df_copy[amount_col] = amount_list  # No more slicing, now the lengths should match

    return df_copy


amount_df = add_amount_based_on_strategy(
    switch_df, strategy="SWITCH_DYNAMIC_OPTIMISTIC", initial_amount=1000.0
)
amount_df = add_amount_based_on_strategy(
    amount_df, strategy="SWITCH_DYNAMIC", initial_amount=1000.0
)
amount_df = add_amount_based_on_strategy(
    amount_df, strategy="SWITCH_DYNAMIC_PESSIMISTIC", initial_amount=1000.0
)

# round the values to 2 decimal places
amount_df["AMOUNT_SWITCH_DYNAMIC"] = amount_df["AMOUNT_SWITCH_DYNAMIC"].round(2)
amount_df["AMOUNT_SWITCH_DYNAMIC_OPTIMISTIC"] = amount_df[
    "AMOUNT_SWITCH_DYNAMIC_OPTIMISTIC"
].round(2)
amount_df.tail(24)


# number of changes from CASH to MOMENTUM and vice versa
def change_count(amount_df, strategy: str = "SWITCH_DYNAMIC"):
    df = amount_df.copy()
    df["CHANGE"] = df[strategy].shift(1) != df[strategy]
    df["CHANGE"] = df["CHANGE"].astype(int)
    return df["CHANGE"].sum()


# Number of changes from CASH to MOMENTUM
def sell_count(amount_df, strategy: str = "SWITCH_DYNAMIC"):
    df = amount_df.copy()
    df["CHANGE"] = df[strategy].shift(1) != df[strategy]
    df["CHANGE"] = df["CHANGE"].astype(int)
    df["SELL"] = df["CHANGE"] * (df[strategy] == "CASH")
    return df["SELL"].sum()


pd.DataFrame(
    {
        "Strategy": [
            "SWITCH_DYNAMIC",
            "SWITCH_DYNAMIC_OPTIMISTIC",
            "SWITCH_DYNAMIC_PESSIMISTIC",
        ],
        "Change Count": [
            change_count(amount_df, strategy="SWITCH_DYNAMIC"),
            change_count(amount_df, strategy="SWITCH_DYNAMIC_OPTIMISTIC"),
            change_count(amount_df, strategy="SWITCH_DYNAMIC_PESSIMISTIC"),
        ],
        "Sell Count": [
            sell_count(amount_df, strategy="SWITCH_DYNAMIC"),
            sell_count(amount_df, strategy="SWITCH_DYNAMIC_OPTIMISTIC"),
            sell_count(amount_df, strategy="SWITCH_DYNAMIC_PESSIMISTIC"),
        ],
    }
)


amount_df.tail(24)[
    [
        "Date",
        "Close",
        "SWITCH_DYNAMIC",
        "AMOUNT_SWITCH_DYNAMIC",
        "SWITCH_DYNAMIC_OPTIMISTIC",
        "AMOUNT_SWITCH_DYNAMIC_OPTIMISTIC",
        "SWITCH_DYNAMIC_PESSIMISTIC",
        "AMOUNT_SWITCH_DYNAMIC_PESSIMISTIC",
    ]
]


# Function to calculate rolling returns for weekly data
def calculate_rolling_returns_weekly(
    df: pd.DataFrame, col_name: str, weeks: int
) -> pd.Series:
    start_values = df[col_name].shift(weeks - 1)
    end_values = df[col_name]
    cagr = ((end_values / start_values) ** (1 / (weeks / 52))) - 1
    return cagr * 100  # convert to percentage


# Function to plot PDF and CDF for weekly data
def plot_pdf_cdf(df: pd.DataFrame, col_name: str, weeks: int):
    rolling_returns = calculate_rolling_returns_weekly(df, col_name, weeks).dropna()
    sns.set(style="whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    plt.suptitle(f"PDF and CDF for {weeks}-week Rolling Returns of {col_name}")
    sns.histplot(rolling_returns, bins=50, kde=True, stat="probability", ax=axes[0])
    axes[0].set_title("Probability Density Function (PDF)")
    axes[0].set_xlabel("Rolling Returns (%)")
    axes[0].set_ylabel("Probability")
    sns.histplot(
        rolling_returns,
        bins=30,
        kde=True,
        cumulative=True,
        stat="probability",
        ax=axes[1],
    )
    axes[1].set_title("Cumulative Density Function (CDF)")
    axes[1].set_xlabel("Rolling Returns (%)")
    axes[1].set_ylabel("Cumulative Probability")
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.show()


plot_pdf_cdf(amount_df, "Close", 52)
plot_pdf_cdf(amount_df, "AMOUNT_SWITCH_DYNAMIC", 52)
plot_pdf_cdf(amount_df, "AMOUNT_SWITCH_DYNAMIC_OPTIMISTIC", 52)
plot_pdf_cdf(amount_df, "AMOUNT_SWITCH_DYNAMIC_PESSIMISTIC", 52)


# 📉: Modify the existing functions to work with weekly data rather than monthly.


# Helper function to calculate CAGR for weekly data
def cagr_weekly(end_value, start_value, periods):
    return (end_value / start_value) ** (1 / (periods / 52)) - 1


# Function to calculate common backtest statistics for weekly data
def backtest_stats(
    df: pd.DataFrame, columns: List[str], rf_rate: float = 0.07
) -> pd.DataFrame:
    stats = {}
    for col in columns:
        col_stats = {}

        # Calculate CAGR for weekly data
        cagr_value = cagr_weekly(df[col].iloc[-1], df[col].iloc[0], len(df))
        col_stats["CAGR"] = cagr_value

        # Calculate annualized risk for weekly data
        df["returns"] = df[col].pct_change().dropna()
        annual_risk = df["returns"].std() * np.sqrt(52)
        col_stats["Annualized Risk"] = annual_risk

        # Sharpe Ratio
        sharpe_ratio = (cagr_value - rf_rate) / annual_risk
        col_stats["Sharpe Ratio"] = sharpe_ratio

        # Max Drawdown
        df["cum_return"] = (1 + df["returns"]).cumprod()
        df["cum_roll_max"] = df["cum_return"].cummax()
        df["drawdown"] = df["cum_roll_max"] - df["cum_return"]
        df["drawdown_pct"] = df["drawdown"] / df["cum_roll_max"]
        max_drawdown = df["drawdown_pct"].max()
        col_stats["Max Drawdown"] = max_drawdown

        # Sortino Ratio
        df["downside_returns"] = 0
        target = 0
        mask = df["returns"] < target
        df.loc[mask, "downside_returns"] = df["returns"] ** 2
        expected_return = df["returns"].mean()
        downside_std = np.sqrt(df["downside_returns"].mean())
        sortino_ratio = (expected_return - rf_rate) / downside_std
        col_stats["Sortino Ratio"] = sortino_ratio

        # Calmar Ratio
        calmar_ratio = cagr_value / max_drawdown
        col_stats["Calmar Ratio"] = calmar_ratio

        stats[col] = col_stats

    return pd.DataFrame(stats)


# Code ends here, and it's now prepared to handle weekly data.
backtest_stats(
    amount_df,
    columns=[
        "Close",
        "AMOUNT_SWITCH_DYNAMIC",
        "AMOUNT_SWITCH_DYNAMIC_OPTIMISTIC",
        "AMOUNT_SWITCH_DYNAMIC_PESSIMISTIC",
    ],
)
