"""
Compare Z-Score Thresholds (1.0 vs 1.5)

Test mean reversion strategy on 2x leveraged ETFs with different z-score thresholds
across random 2-year periods to find optimal signal sensitivity.
"""

import pandas as pd
import numpy as np
import argparse
from datetime import datetime, timedelta
from backtest_engine import PortfolioStddevBacktester
from leveraged_etfs import fetch_leveraged_closes
import time


def run_single_period(start_date: str, end_date: str, z_threshold: float) -> dict:
    """Run backtest for a single period with given z-threshold."""
    date_range = f"{start_date} to {end_date}"

    # Calculate range string for Yahoo Finance
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    days_diff = (end - start).days

    if days_diff <= 365:
        range_str = "1y"
    elif days_diff <= 730:
        range_str = "2y"
    elif days_diff <= 1095:
        range_str = "3y"
    else:
        range_str = "5y"

    try:
        # Fetch leveraged ETF data
        leveraged_closes = fetch_leveraged_closes(range_=range_str)

        # Filter to date range
        mask = (leveraged_closes.index >= start) & (leveraged_closes.index <= end)
        leveraged_closes = leveraged_closes[mask]

        if len(leveraged_closes) < 21:
            return None

        # Run backtest with specified threshold
        backtester = PortfolioStddevBacktester(
            prices_df=leveraged_closes,
            initial_capital=10000,
            lookback_period=20,
            z_threshold=z_threshold,
            max_sector_allocation=0.25,
        )
        results = backtester.run()

        return {
            "period": date_range,
            "return": results.total_return,
            "value": results.final_value,
            "drawdown": results.max_drawdown,
            "sharpe": results.sharpe_ratio,
            "trades": results.num_trades,
            "invested_pct": results.avg_invested_pct,
        }
    except Exception as e:
        print(f"  Error in period {date_range}: {str(e)[:50]}")
        return None


def run_comparison(num_periods: int = 10):
    """Compare z-threshold 1.0 vs 1.5 across random periods."""
    print("=" * 150)
    print("Z-SCORE THRESHOLD COMPARISON (1.0 vs 1.5)")
    print("=" * 150)
    print(f"\nTesting {num_periods} random 2-year periods...\n")

    results_10 = []
    results_15 = []

    # Generate random 2-year periods
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*5)  # Last 5 years to sample from

    for i in range(num_periods):
        # Random end date within the last 5 years
        random_end = start_date + timedelta(days=np.random.randint(730, 1825))
        random_start = random_end - timedelta(days=730)  # 2 years before

        period_str = f"Period {i+1}/{num_periods}: {random_start.strftime('%Y-%m-%d')} to {random_end.strftime('%Y-%m-%d')}"
        print(period_str)

        # Test with z_threshold = 1.0
        result_10 = run_single_period(
            random_start.strftime("%Y-%m-%d"),
            random_end.strftime("%Y-%m-%d"),
            z_threshold=1.0
        )

        # Test with z_threshold = 1.5
        result_15 = run_single_period(
            random_start.strftime("%Y-%m-%d"),
            random_end.strftime("%Y-%m-%d"),
            z_threshold=1.5
        )

        if result_10 and result_15:
            results_10.append(result_10)
            results_15.append(result_15)
            print(f"  Z=1.0: {result_10['return']:>7.2f}% ({result_10['trades']:>3.0f} trades) | Z=1.5: {result_15['return']:>7.2f}% ({result_15['trades']:>3.0f} trades)")

        time.sleep(0.5)  # Be nice to the API

    if not results_10 or not results_15:
        print("No valid results obtained.")
        return

    # Create results dataframes
    df_10 = pd.DataFrame(results_10)
    df_15 = pd.DataFrame(results_15)

    print("\n" + "=" * 150)
    print("DETAILED RESULTS - Z-THRESHOLD 1.0")
    print("=" * 150)

    cols_display_10 = df_10[["period", "return", "drawdown", "sharpe", "trades", "invested_pct"]].copy()
    cols_display_10.columns = ["Period", "Return %", "Max DD %", "Sharpe", "Trades", "Avg Invested %"]
    print(cols_display_10.to_string(index=False))

    print("\n" + "=" * 150)
    print("DETAILED RESULTS - Z-THRESHOLD 1.5")
    print("=" * 150)

    cols_display_15 = df_15[["period", "return", "drawdown", "sharpe", "trades", "invested_pct"]].copy()
    cols_display_15.columns = ["Period", "Return %", "Max DD %", "Sharpe", "Trades", "Avg Invested %"]
    print(cols_display_15.to_string(index=False))

    # Comparison statistics
    print("\n" + "=" * 150)
    print("STATISTICAL COMPARISON")
    print("=" * 150)

    print(f"\n{'Metric':<35} | {'Z-Threshold 1.0':<30} | {'Z-Threshold 1.5':<30}")
    print("-" * 150)
    print(f"{'Mean Return':<35} | {df_10['return'].mean():>7.2f}% {'':<22} | {df_15['return'].mean():>7.2f}% {'':<22}")
    print(f"{'Median Return':<35} | {df_10['return'].median():>7.2f}% {'':<22} | {df_15['return'].median():>7.2f}% {'':<22}")
    print(f"{'Std Dev':<35} | {df_10['return'].std():>7.2f}% {'':<22} | {df_15['return'].std():>7.2f}% {'':<22}")
    print(f"{'Min Return':<35} | {df_10['return'].min():>7.2f}% {'':<22} | {df_15['return'].min():>7.2f}% {'':<22}")
    print(f"{'Max Return':<35} | {df_10['return'].max():>7.2f}% {'':<22} | {df_15['return'].max():>7.2f}% {'':<22}")
    print(f"{'Avg Max Drawdown':<35} | {df_10['drawdown'].mean():>7.2f}% {'':<22} | {df_15['drawdown'].mean():>7.2f}% {'':<22}")
    print(f"{'Avg Sharpe Ratio':<35} | {df_10['sharpe'].mean():>7.2f} {'':<24} | {df_15['sharpe'].mean():>7.2f} {'':<24}")
    print(f"{'Avg Trades per Period':<35} | {df_10['trades'].mean():>7.0f} {'':<24} | {df_15['trades'].mean():>7.0f} {'':<24}")
    print(f"{'Avg Capital Invested':<35} | {df_10['invested_pct'].mean():>7.1f}% {'':<22} | {df_15['invested_pct'].mean():>7.1f}% {'':<22}")

    # Head-to-head
    wins_10 = (df_10['return'] > df_15['return']).sum()
    wins_15 = (df_15['return'] > df_10['return']).sum()
    ties = (df_10['return'] == df_15['return']).sum()

    print("\n" + "=" * 150)
    print("HEAD-TO-HEAD COMPARISON")
    print("=" * 150)
    print(f"\nZ=1.0 Wins: {wins_10}/{len(df_10)} periods ({wins_10/len(df_10)*100:.1f}%)")
    print(f"Z=1.5 Wins: {wins_15}/{len(df_15)} periods ({wins_15/len(df_15)*100:.1f}%)")
    print(f"Ties:       {ties}/{len(df_10)} periods ({ties/len(df_10)*100:.1f}%)")

    avg_outperformance_10_vs_15 = (df_10['return'] - df_15['return']).mean()
    print(f"\nAverage Outperformance: Z=1.0 {avg_outperformance_10_vs_15:+.2f}% vs Z=1.5")

    # Risk-adjusted metrics
    print("\n" + "=" * 150)
    print("RISK-ADJUSTED ANALYSIS")
    print("=" * 150)

    # Sharpe ratio comparison
    avg_sharpe_10 = df_10['sharpe'].mean()
    avg_sharpe_15 = df_15['sharpe'].mean()

    print(f"\nAvg Sharpe Ratio (Z=1.0): {avg_sharpe_10:.3f}")
    print(f"Avg Sharpe Ratio (Z=1.5): {avg_sharpe_15:.3f}")

    # Return per trade (efficiency)
    avg_return_per_trade_10 = df_10['return'].mean() / df_10['trades'].mean()
    avg_return_per_trade_15 = df_15['return'].mean() / df_15['trades'].mean()

    print(f"\nReturn per Trade (Z=1.0): {avg_return_per_trade_10:.3f}%")
    print(f"Return per Trade (Z=1.5): {avg_return_per_trade_15:.3f}%")

    # Capital efficiency
    print(f"\nCapital Utilization (Z=1.0): {df_10['invested_pct'].mean():.1f}%")
    print(f"Capital Utilization (Z=1.5): {df_15['invested_pct'].mean():.1f}%")

    # Save comparison
    comparison_df = pd.DataFrame({
        "Period": df_10["period"],
        "Z1.0_Return": df_10["return"],
        "Z1.5_Return": df_15["return"],
        "Difference": df_10["return"] - df_15["return"],
        "Z1.0_Trades": df_10["trades"],
        "Z1.5_Trades": df_15["trades"],
        "Z1.0_Drawdown": df_10["drawdown"],
        "Z1.5_Drawdown": df_15["drawdown"],
    })

    output_file = "backtest_zscore_comparison_results.csv"
    comparison_df.to_csv(output_file, index=False)
    print(f"\n✓ Detailed comparison saved to {output_file}")

    # Recommendation
    print("\n" + "=" * 150)
    print("RECOMMENDATION")
    print("=" * 150)

    if avg_outperformance_10_vs_15 > 2:
        print(f"""
✓ Z=1.0 BETTER: Higher returns by {avg_outperformance_10_vs_15:.2f}% on average
  → Z=1.0 catches more opportunities
  → More trades ({df_10['trades'].mean():.0f} vs {df_15['trades'].mean():.0f}) but better overall returns
  → Recommended for active traders
        """)
    elif avg_outperformance_10_vs_15 < -2:
        print(f"""
✓ Z=1.5 BETTER: Higher returns by {abs(avg_outperformance_10_vs_15):.2f}% on average
  → Z=1.5 filters noise, fewer false signals
  → Fewer trades ({df_15['trades'].mean():.0f} vs {df_10['trades'].mean():.0f}) but higher quality
  → Better Sharpe ratio suggests more consistent returns
  → Recommended for efficiency-focused traders
        """)
    else:
        print(f"""
~ SIMILAR PERFORMANCE: Within {abs(avg_outperformance_10_vs_15):.2f}% of each other
  → Z=1.0: More trades, higher volume strategy
  → Z=1.5: Lower frequency, higher conviction trades
  → Choose based on preference: volume vs quality
        """)

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare Z-Score Thresholds (1.0 vs 1.5)"
    )
    parser.add_argument(
        "--periods",
        type=int,
        default=10,
        help="Number of random 2-year periods to test (default 10)",
    )

    args = parser.parse_args()
    run_comparison(num_periods=args.periods)
