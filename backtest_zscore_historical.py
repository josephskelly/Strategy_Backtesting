"""
Z=1.0 Backtest with Extended Historical Data

Test mean reversion strategy on 2x leveraged ETFs across random 2-year periods
spanning 15+ years of market history, with periods spaced far apart for diversity.
"""

import pandas as pd
import numpy as np
import argparse
from datetime import datetime, timedelta
from backtest_engine import PortfolioStddevBacktester
from leveraged_etfs import fetch_leveraged_closes
import time


def run_single_period(start_date: str, end_date: str) -> dict:
    """Run backtest for a single period."""
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
    elif days_diff <= 1825:
        range_str = "5y"
    else:
        range_str = "10y"

    try:
        # Fetch leveraged ETF data
        leveraged_closes = fetch_leveraged_closes(range_=range_str)

        # Filter to date range
        mask = (leveraged_closes.index >= start) & (leveraged_closes.index <= end)
        leveraged_closes = leveraged_closes[mask]

        if len(leveraged_closes) < 21:
            return None

        # Run backtest
        backtester = PortfolioStddevBacktester(
            prices_df=leveraged_closes,
            initial_capital=10000,
            lookback_period=20,
            z_threshold=1.0,
            max_sector_allocation=0.25,
        )
        results = backtester.run()

        return {
            "period": date_range,
            "start": start_date,
            "end": end_date,
            "return": results.total_return,
            "value": results.final_value,
            "drawdown": results.max_drawdown,
            "sharpe": results.sharpe_ratio,
            "trades": results.num_trades,
            "invested_pct": results.avg_invested_pct,
            "pnl": results.final_pnl,
        }
    except Exception as e:
        print(f"  Error in period {date_range}: {str(e)[:50]}")
        return None


def run_historical_backtest(num_periods: int = 15):
    """Test across extended historical periods, spaced far apart."""
    print("=" * 150)
    print("HISTORICAL BACKTEST: Z=1.0 ACROSS 5 YEARS OF MARKET CONDITIONS")
    print("=" * 150)
    print(f"\nTesting {num_periods} random 2-year periods spanning 2021-2026...")
    print("(Note: Yahoo Finance provides ~5 years of historical data for these leveraged ETFs)\n")

    results = []

    # First, fetch data to see actual date range available
    try:
        leveraged_closes = fetch_leveraged_closes(range_="5y")
        earliest_date = leveraged_closes.index.min()
        latest_date = leveraged_closes.index.max()
        print(f"Available data range: {earliest_date.strftime('%Y-%m-%d')} to {latest_date.strftime('%Y-%m-%d')}\n")
    except Exception as e:
        print(f"Error fetching data: {e}")
        return

    # Generate well-spaced random 2-year periods from available range
    # Need at least 2 years of data for each period
    min_start = earliest_date + timedelta(days=730)
    max_start = latest_date - timedelta(days=730)

    available_days = (max_start - min_start).days
    if available_days < 0:
        print("Not enough historical data for 2-year periods")
        return

    min_spacing = 90  # 3 months minimum between period start dates (allows some overlap)

    selected_periods = []
    used_starts = set()

    # Generate random periods with minimum spacing
    # With 5 years of data, we can fit ~15-20 periods with 3-month spacing
    for attempt in range(num_periods * 20):  # Multiple attempts to find valid periods
        if len(selected_periods) >= num_periods:
            break

        # Random start date within available window
        random_offset = np.random.randint(0, max(1, available_days))
        period_start = min_start + timedelta(days=random_offset)
        period_end = period_start + timedelta(days=730)

        # Check if this start date is far enough from used dates
        is_valid = True
        for used_start in used_starts:
            if abs((period_start - used_start).days) < min_spacing:
                is_valid = False
                break

        if is_valid and period_end <= latest_date:
            selected_periods.append((period_start, period_end))
            used_starts.add(period_start)

    # Sort by date
    selected_periods.sort()

    # Run backtests
    for i, (period_start, period_end) in enumerate(selected_periods):
        print(f"Period {i+1}/{num_periods}: {period_start.strftime('%Y-%m-%d')} to {period_end.strftime('%Y-%m-%d')}")

        result = run_single_period(
            period_start.strftime("%Y-%m-%d"),
            period_end.strftime("%Y-%m-%d")
        )

        if result:
            results.append(result)
            print(f"  Return: {result['return']:>7.2f}% | DD: {result['drawdown']:>7.2f}% | Trades: {result['trades']:>3.0f} | Sharpe: {result['sharpe']:>6.2f}")

        time.sleep(0.5)  # Be nice to the API

    if not results:
        print("No valid results obtained.")
        return

    # Create results dataframe
    results_df = pd.DataFrame(results)

    print("\n" + "=" * 150)
    print("DETAILED RESULTS")
    print("=" * 150)

    display_cols = ["period", "return", "drawdown", "sharpe", "trades", "invested_pct"]
    display_df = results_df[display_cols].copy()
    display_df.columns = ["Period", "Return %", "Max DD %", "Sharpe", "Trades", "Avg Invested %"]
    print(display_df.to_string(index=False))

    # Summary statistics
    print("\n" + "=" * 150)
    print("HISTORICAL PERFORMANCE SUMMARY (Z=1.0)")
    print("=" * 150)

    returns = results_df["return"]
    drawdowns = results_df["drawdown"]
    sharpes = results_df["sharpe"]
    trades = results_df["trades"]

    print(f"\nReturn Statistics:")
    print(f"  Mean Return:                {returns.mean():>7.2f}%")
    print(f"  Median Return:              {returns.median():>7.2f}%")
    print(f"  Std Dev:                    {returns.std():>7.2f}%")
    print(f"  Min Return:                 {returns.min():>7.2f}%")
    print(f"  Max Return:                 {returns.max():>7.2f}%")
    print(f"  Positive Periods:           {(returns > 0).sum()}/{len(returns)} ({(returns > 0).sum()/len(returns)*100:.1f}%)")

    print(f"\nRisk Metrics:")
    print(f"  Avg Max Drawdown:           {drawdowns.mean():>7.2f}%")
    print(f"  Worst Drawdown:             {drawdowns.min():>7.2f}%")
    print(f"  Best Case Drawdown:         {drawdowns.max():>7.2f}%")
    print(f"  Avg Sharpe Ratio:           {sharpes.mean():>7.3f}")
    print(f"  Median Sharpe Ratio:        {sharpes.median():>7.3f}")

    print(f"\nTrading Activity:")
    print(f"  Avg Trades per Period:      {trades.mean():>7.0f}")
    print(f"  Median Trades per Period:   {trades.median():>7.0f}")
    print(f"  Range:                      {trades.min():.0f} - {trades.max():.0f}")

    print(f"\nCapital Efficiency:")
    print(f"  Avg Capital Invested:       {results_df['invested_pct'].mean():>7.1f}%")

    # Market periods breakdown
    print("\n" + "=" * 150)
    print("MARKET PERIOD ANALYSIS")
    print("=" * 150)

    print(f"\nBull Markets (Return > 15%):")
    bull = results_df[results_df["return"] > 15]
    if len(bull) > 0:
        print(f"  Count: {len(bull)} periods")
        print(f"  Avg Return: {bull['return'].mean():.2f}%")
        print(f"  Avg Sharpe: {bull['sharpe'].mean():.3f}")

    print(f"\nNormal Markets (0% < Return < 15%):")
    normal = results_df[(results_df["return"] > 0) & (results_df["return"] <= 15)]
    if len(normal) > 0:
        print(f"  Count: {len(normal)} periods")
        print(f"  Avg Return: {normal['return'].mean():.2f}%")
        print(f"  Avg Sharpe: {normal['sharpe'].mean():.3f}")

    print(f"\nBear Markets (Return < 0%):")
    bear = results_df[results_df["return"] < 0]
    if len(bear) > 0:
        print(f"  Count: {len(bear)} periods")
        print(f"  Avg Return: {bear['return'].mean():.2f}%")
        print(f"  Avg Sharpe: {bear['sharpe'].mean():.3f}")

    # Decade breakdown
    print("\n" + "=" * 150)
    print("PERFORMANCE BY TIME PERIOD")
    print("=" * 150)

    for decade_start in [2009, 2013, 2017, 2021]:
        decade_end = decade_start + 4
        decade_results = results_df[
            (results_df["start"].str[:4].astype(int) >= decade_start) &
            (results_df["start"].str[:4].astype(int) < decade_end)
        ]
        if len(decade_results) > 0:
            print(f"\n{decade_start}-{decade_end}:")
            print(f"  Periods: {len(decade_results)}")
            print(f"  Avg Return: {decade_results['return'].mean():>7.2f}%")
            print(f"  Avg Sharpe: {decade_results['sharpe'].mean():>7.3f}")
            print(f"  Avg Trades: {decade_results['trades'].mean():>7.0f}")

    # Save results
    output_file = "backtest_zscore_historical_results.csv"
    results_df.to_csv(output_file, index=False)
    print(f"\n✓ Detailed results saved to {output_file}")

    # Overall assessment
    print("\n" + "=" * 150)
    print("ASSESSMENT")
    print("=" * 150)

    overall_avg_return = returns.mean()
    overall_win_rate = (returns > 0).sum() / len(returns) * 100
    overall_sharpe = sharpes.mean()

    print(f"""
STRATEGY PERFORMANCE ACROSS 15+ YEARS OF MARKET CONDITIONS:

Return Profile:
  • Average Return: {overall_avg_return:.2f}% per 2-year period
  • Win Rate: {overall_win_rate:.1f}% of periods profitable
  • Drawdown: {drawdowns.mean():.2f}% average

Risk-Adjusted Performance:
  • Sharpe Ratio: {overall_sharpe:.3f}
  • Consistency: {returns.std():.2f}% std dev

Assessment:
""")

    if overall_avg_return > 20 and overall_win_rate > 80:
        print(f"  ✅ EXCELLENT: Consistent outperformance across all market conditions")
    elif overall_avg_return > 15 and overall_win_rate > 70:
        print(f"  ✅ STRONG: Reliable strategy with good risk-adjusted returns")
    elif overall_avg_return > 10 and overall_win_rate > 60:
        print(f"  ✓ GOOD: Positive returns across diverse periods")
    elif overall_avg_return > 5 and overall_win_rate > 50:
        print(f"  ⚠️  MODERATE: Works but inconsistent across market conditions")
    else:
        print(f"  ❌ WEAK: Struggle in certain market environments")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Historical Backtest of Z=1.0 Strategy (2009-2026)"
    )
    parser.add_argument(
        "--periods",
        type=int,
        default=15,
        help="Number of random 2-year periods to test (default 15)",
    )

    args = parser.parse_args()
    run_historical_backtest(num_periods=args.periods)
