"""
30-Year Cumulative Comparison

Compound the annual returns from 1999-2026 to show total wealth growth
"""

import pandas as pd
import numpy as np


def calculate_cumulative_returns(annual_returns):
    """Calculate cumulative wealth from annual returns."""
    cumulative = [10000]  # Start with $10,000

    for ret in annual_returns:
        cumulative.append(cumulative[-1] * (1 + ret / 100))

    return cumulative


# Annual returns from the backtest
annual_data = {
    "year": [1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009,
             2010, 2011, 2012, 2013, 2014, 2015, 2017, 2018, 2019, 2020, 2021,
             2022, 2023, 2024, 2025, 2026],
    "daily_return": [18.22, 8.90, -7.42, -13.27, 15.81, 7.10, 9.93, 12.79, 10.71, 3.95, 31.74,
                     7.51, 0.64, 34.99, 19.78, 0.96, 0.98, 8.37, -4.27, 13.79, 0.10, 23.51,
                     -0.48, 4.37, 9.67, 16.49, 1.47],
    "sp500_return": [19.38, -9.80, -11.27, -23.63, 22.19, 8.67, 3.50, 11.78, 3.42, -37.74, 19.88,
                     10.96, -1.22, 11.69, 26.45, 12.37, -0.76, 18.48, -7.01, 28.65, 15.09, 28.79,
                     -19.95, 24.81, 24.00, 16.64, -0.21],
}

df = pd.DataFrame(annual_data)

# Calculate cumulative returns
daily_cumulative = calculate_cumulative_returns(df["daily_return"])
sp500_cumulative = calculate_cumulative_returns(df["sp500_return"])

# Create output dataframe
years = [1998] + list(df["year"])  # Include starting year
output_df = pd.DataFrame({
    "Year": years,
    "Daily Rebalance $": daily_cumulative,
    "S&P 500 $": sp500_cumulative,
})

# Calculate gains and advantage
output_df["Daily Return %"] = output_df["Daily Rebalance $"].pct_change() * 100
output_df["S&P Return %"] = output_df["S&P 500 $"].pct_change() * 100
output_df["Advantage $"] = output_df["Daily Rebalance $"] - output_df["S&P 500 $"]
output_df["Advantage %"] = (output_df["Daily Rebalance $"] / output_df["S&P 500 $"] - 1) * 100

print("=" * 200)
print("30-YEAR CUMULATIVE WEALTH COMPARISON (1999-2026)")
print("Starting Capital: $10,000")
print("=" * 200)
print()

# Print detailed year-by-year
print("Year-by-Year Wealth Growth:")
print("-" * 200)
print(f"{'Year':<6} | {'Daily Rebalance':<20} | {'S&P 500':<20} | {'Daily Return':<15} | {'S&P Return':<15} | {'Advantage':<20}")
print("-" * 200)

for idx, row in output_df.iterrows():
    year = int(row["Year"])
    daily_val = row["Daily Rebalance $"]
    sp500_val = row["S&P 500 $"]
    daily_ret = row["Daily Return %"]
    sp500_ret = row["S&P Return %"]
    advantage = row["Advantage $"]

    if idx == 0:
        print(f"{year:<6} | ${daily_val:>17,.0f} | ${sp500_val:>17,.0f} | {'—':<15} | {'—':<15} | ${advantage:>18,.0f}")
    else:
        print(f"{year:<6} | ${daily_val:>17,.0f} | ${sp500_val:>17,.0f} | {daily_ret:>13.2f}% | {sp500_ret:>13.2f}% | ${advantage:>18,.0f}")

print("-" * 200)
print()

# Summary statistics
final_year = output_df.iloc[-1]
print("=" * 200)
print("FINAL RESULTS (After 28 Years: 1999-2026)")
print("=" * 200)
print()

daily_final = final_year["Daily Rebalance $"]
sp500_final = final_year["S&P 500 $"]
daily_total_return = (daily_final / 10000 - 1) * 100
sp500_total_return = (sp500_final / 10000 - 1) * 100
difference = daily_final - sp500_final
difference_pct = (daily_final / sp500_final - 1) * 100

print(f"Daily Rebalance Strategy ($300 per 1% move):")
print(f"  Final Value: ${daily_final:,.0f}")
print(f"  Total Return: {daily_total_return:.2f}%")
print(f"  Annualized Return: {(((daily_final/10000)**(1/27))-1)*100:.2f}%")
print(f"  Total Gain: ${daily_final - 10000:,.0f}")
print()

print(f"S&P 500 Buy-and-Hold:")
print(f"  Final Value: ${sp500_final:,.0f}")
print(f"  Total Return: {sp500_total_return:.2f}%")
print(f"  Annualized Return: {(((sp500_final/10000)**(1/27))-1)*100:.2f}%")
print(f"  Total Gain: ${sp500_final - 10000:,.0f}")
print()

print(f"Advantage (Daily Rebalance):")
if difference > 0:
    print(f"  ✅ Strategy ahead by: ${difference:,.0f}")
    print(f"  ✅ Percentage advantage: {difference_pct:.2f}%")
    print(f"  ✅ Extra wealth created: ${difference:,.0f}")
else:
    print(f"  ❌ Strategy behind by: ${abs(difference):,.0f}")
    print(f"  ❌ Percentage disadvantage: {difference_pct:.2f}%")
    print(f"  ❌ Wealth lost: ${abs(difference):,.0f}")

print()
print("=" * 200)
print("DECADE-BY-DECADE WEALTH")
print("=" * 200)
print()

decade_points = {
    "1998 (Start)": output_df[output_df["Year"] == 1998],
    "1999 (End of 1990s)": output_df[output_df["Year"] == 1999],
    "2009 (End of 2000s)": output_df[output_df["Year"] == 2009],
    "2019 (End of 2010s)": output_df[output_df["Year"] == 2019],
    "2026 (Current)": output_df[output_df["Year"] == 2026],
}

for label, subset in decade_points.items():
    if not subset.empty:
        row = subset.iloc[0]
        daily_val = row["Daily Rebalance $"]
        sp500_val = row["S&P 500 $"]
        advantage = daily_val - sp500_val
        advantage_pct = (daily_val / sp500_val - 1) * 100

        print(f"{label}:")
        print(f"  Daily Rebalance: ${daily_val:>12,.0f} (gain from start: ${daily_val - 10000:>10,.0f})")
        print(f"  S&P 500:         ${sp500_val:>12,.0f} (gain from start: ${sp500_val - 10000:>10,.0f})")
        print(f"  Advantage:       ${advantage:>12,.0f} ({advantage_pct:+.2f}%)")
        print()

print("=" * 200)
print("KEY INSIGHTS")
print("=" * 200)
print()

# Find when strategies diverged most
output_df["Advantage $"] = output_df["Daily Rebalance $"] - output_df["S&P 500 $"]
max_advantage_idx = output_df["Advantage $"].idxmax()
min_advantage_idx = output_df["Advantage $"].idxmin()

max_adv_row = output_df.iloc[max_advantage_idx]
min_adv_row = output_df.iloc[min_advantage_idx]

print(f"BIGGEST ADVANTAGE (Daily Rebalance ahead):")
print(f"  Year: {int(max_adv_row['Year'])}")
print(f"  Daily Rebalance: ${max_adv_row['Daily Rebalance $']:,.0f}")
print(f"  S&P 500: ${max_adv_row['S&P 500 $']:,.0f}")
print(f"  Advantage: ${max_adv_row['Advantage $']:,.0f}")
print()

print(f"BIGGEST DISADVANTAGE (S&P 500 ahead):")
print(f"  Year: {int(min_adv_row['Year'])}")
print(f"  Daily Rebalance: ${min_adv_row['Daily Rebalance $']:,.0f}")
print(f"  S&P 500: ${min_adv_row['S&P 500 $']:,.0f}")
print(f"  Disadvantage: ${abs(min_adv_row['Advantage $']):,.0f}")
print()

# Risk-adjusted analysis
print("=" * 200)
print("WHAT THIS MEANS")
print("=" * 200)
print()

if difference > 0:
    print(f"""
✅ STRATEGY OUTPERFORMS over 30 years

Starting with $10,000 in 1999:
  • Daily Rebalance grew to: ${daily_final:,.0f}
  • S&P 500 grew to: ${sp500_final:,.0f}

  You'd have ${difference:,.0f} MORE using daily rebalance
  That's a {difference_pct:.1f}% advantage

The key: While the strategy loses in strong bull markets,
it WINS SO MUCH in crashes that it comes out ahead overall.

2008 alone: +3.95% vs -37.74% (41.69 percentage point swing)
2012: +34.99% vs +11.69% (23.30 percentage point swing)
2022: -0.48% vs -19.95% (19.46 percentage point swing)

These crisis wins more than make up for bull market losses.
""")
else:
    print(f"""
❌ S&P 500 OUTPERFORMS over 30 years

Starting with $10,000 in 1999:
  • Daily Rebalance grew to: ${daily_final:,.0f}
  • S&P 500 grew to: ${sp500_final:,.0f}

  You'd have ${abs(difference):,.0f} LESS using daily rebalance

However, the strategy provides:
  • {(11.04/17.03)*100:.0f}% less volatility (11% vs 17% std dev)
  • 85% positive years vs 67% for S&P
  • Exceptional crash protection

This is about RISK-ADJUSTED returns, not just absolute returns.
""")

print()
print("=" * 200)
