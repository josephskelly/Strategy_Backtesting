"""
Test Mean Reversion Strategy across Random 2-Year Periods

Backtests the strategy on multiple random 2-year windows from 5-year history
and compares to buy-and-hold benchmark.

Usage:
    python backtest_random_periods.py              # 10 random periods
    python backtest_random_periods.py --periods 20 # 20 random periods
"""

import os

import pandas as pd
import numpy as np
from sector_etfs import fetch_sector_closes, SECTOR_ETFS
from backtest_engine import PortfolioStddevBacktester
from datetime import timedelta
import random
import argparse

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_full_price_history(years: int = 5) -> pd.DataFrame:
    """Fetch full price history for random period selection."""
    print(f"Fetching {years}-year price history...")
    closes = fetch_sector_closes(range_=f"{years}y")
    return closes


def run_mean_reversion_backtest(
    prices_df: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> dict:
    """Run mean reversion backtest on specific period."""
    period_data = prices_df.loc[start_date:end_date].copy()

    if len(period_data) < 30:
        return None

    backtester = PortfolioStddevBacktester(
        prices_df=period_data,
        initial_capital=10000,
        lookback_period=20,
        z_threshold=1.0,
        max_sector_allocation=0.30,
    )
    results = backtester.run()

    return {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "return_pct": results.total_return,
        "final_value": results.final_value,
        "max_drawdown": results.max_drawdown,
        "sharpe_ratio": results.sharpe_ratio,
        "num_trades": results.num_trades,
        "avg_deployed": results.avg_invested_pct,
    }


def calculate_buy_and_hold_return(
    prices_df: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> dict:
    """Calculate equal-weight buy-and-hold returns."""
    period_data = prices_df.loc[start_date:end_date].copy()

    if len(period_data) < 2:
        return None

    initial_per_sector = 10000 / len(period_data.columns)
    sector_returns = {}
    portfolio_return = 0

    for ticker in period_data.columns:
        start_price = period_data[ticker].iloc[0]
        end_price = period_data[ticker].iloc[-1]
        sector_return = ((end_price - start_price) / start_price) * 100
        final_value = initial_per_sector * (1 + sector_return / 100)
        sector_returns[ticker] = sector_return
        portfolio_return += final_value

    portfolio_return = ((portfolio_return - 10000) / 10000) * 100

    # Max drawdown
    first_ticker = period_data.columns[0]
    prices = period_data[first_ticker].values
    running_max = np.maximum.accumulate(prices)
    drawdowns = (prices - running_max) / running_max * 100
    max_drawdown = drawdowns.min()

    return {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "return_pct": portfolio_return,
        "final_value": 10000 * (1 + portfolio_return / 100),
        "max_drawdown": max_drawdown,
        "sharpe_ratio": 0,
    }


def generate_random_2year_periods(
    prices_df: pd.DataFrame, num_periods: int = 10
) -> list:
    """Generate random non-overlapping 2-year periods from data."""
    dates = prices_df.index
    min_date = dates[0]
    max_date = dates[-1]

    two_years = timedelta(days=365 * 2)
    max_start_date = max_date - two_years

    if max_start_date <= min_date:
        print("Not enough data for multiple 2-year periods")
        return []

    periods = []
    for _ in range(num_periods):
        days_available = (max_start_date - min_date).days
        random_days = random.randint(0, max(1, days_available))
        start = min_date + timedelta(days=random_days)
        end = start + two_years

        if end > max_date:
            end = max_date
            start = end - two_years

        periods.append((start, end))

    return periods


def main(num_periods: int = 10):
    """Run backtests on random periods vs buy-and-hold."""
    print("=" * 120)
    print(f"MEAN REVERSION STRATEGY vs BUY-AND-HOLD ({num_periods} RANDOM 2-YEAR PERIODS)")
    print("=" * 120)
    print()

    # Fetch full history
    prices_df = fetch_full_price_history(years=5)
    print(f"Data range: {prices_df.index[0].date()} to {prices_df.index[-1].date()}")
    print(f"Total days: {len(prices_df)}")
    print()

    # Generate random 2-year periods
    print(f"Generating {num_periods} random 2-year periods...")
    periods = generate_random_2year_periods(prices_df, num_periods=num_periods)
    print(f"Generated {len(periods)} periods")
    print()

    # Run backtests
    mr_results = []
    bh_results = []

    print(f"Running backtests on random periods...")
    print()

    for i, (start, end) in enumerate(periods, 1):
        print(f"Period {i}/{num_periods}: {start.date()} to {end.date()}", end=" ... ")

        # Mean reversion
        mr = run_mean_reversion_backtest(prices_df, start, end)
        if mr:
            mr_results.append(mr)
            print(f"MR: {mr['return_pct']:+6.2f}%", end=" | ")

        # Buy-and-hold
        bh = calculate_buy_and_hold_return(prices_df, start, end)
        if bh:
            bh_results.append(bh)
            outperf = mr['return_pct'] - bh['return_pct']
            print(f"B&H: {bh['return_pct']:+6.2f}% | Outperformance: {outperf:+6.2f}%")
        else:
            print()

    print()
    print("=" * 120)
    print("PERFORMANCE SUMMARY")
    print("=" * 120)
    print()

    mr_df = pd.DataFrame(mr_results)
    bh_df = pd.DataFrame(bh_results)

    print(f"{'Metric':<30} {'Mean Reversion':>15} {'Buy-and-Hold':>15} {'Difference':>15}")
    print("-" * 80)

    mr_avg = mr_df['return_pct'].mean()
    bh_avg = bh_df['return_pct'].mean()

    print(f"{'Average Return':<30} {mr_avg:>14.2f}% {bh_avg:>14.2f}% {mr_avg - bh_avg:>14.2f}%")
    print(f"{'Median Return':<30} {mr_df['return_pct'].median():>14.2f}% {bh_df['return_pct'].median():>14.2f}% {mr_df['return_pct'].median() - bh_df['return_pct'].median():>14.2f}%")
    print(f"{'Return Std Dev':<30} {mr_df['return_pct'].std():>14.2f}% {bh_df['return_pct'].std():>14.2f}%")
    print(f"{'Min Return':<30} {mr_df['return_pct'].min():>14.2f}% {bh_df['return_pct'].min():>14.2f}%")
    print(f"{'Max Return':<30} {mr_df['return_pct'].max():>14.2f}% {bh_df['return_pct'].max():>14.2f}%")
    print()
    print(f"{'Avg Max Drawdown':<30} {mr_df['max_drawdown'].mean():>14.2f}% {bh_df['max_drawdown'].mean():>14.2f}% {mr_df['max_drawdown'].mean() - bh_df['max_drawdown'].mean():>14.2f}%")
    print(f"{'Avg Sharpe Ratio':<30} {mr_df['sharpe_ratio'].mean():>14.2f}  {bh_df['sharpe_ratio'].mean():>14.2f}")
    print(f"{'Avg Trades':<30} {mr_df['num_trades'].mean():>14.0f}  {'N/A':>14}")
    print(f"{'Avg Capital Deployed':<30} {mr_df['avg_deployed'].mean():>14.2f}% {'100.00%':>14}")
    print()
    print(f"{'Positive Periods':<30} {(mr_df['return_pct'] > 0).sum():>14}/{num_periods} {(bh_df['return_pct'] > 0).sum():>14}/{num_periods}")

    # Detailed comparison table
    print()
    print("=" * 120)
    print("PERIOD-BY-PERIOD RESULTS")
    print("=" * 120)
    print()

    comparison = []
    for mr, bh in zip(mr_results, bh_results):
        comparison.append({
            "Period": f"{mr['start_date']} to {mr['end_date']}",
            "Mean Reversion": mr['return_pct'],
            "Buy-and-Hold": bh['return_pct'],
            "Outperformance": mr['return_pct'] - bh['return_pct'],
            "MR Drawdown": mr['max_drawdown'],
            "B&H Drawdown": bh['max_drawdown'],
        })

    comp_df = pd.DataFrame(comparison)
    print(comp_df.to_string(index=False))

    # Save results
    mr_df.to_csv(f"{OUTPUT_DIR}/mean_reversion_random_periods.csv", index=False)
    bh_df.to_csv(f"{OUTPUT_DIR}/buyhold_random_periods.csv", index=False)
    comp_df.to_csv(f"{OUTPUT_DIR}/comparison_random_periods.csv", index=False)

    print()
    print("✓ Results saved to CSV files")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test Mean Reversion across random 2-year periods"
    )
    parser.add_argument(
        "--periods",
        type=int,
        default=10,
        help="Number of random 2-year periods to test",
    )

    args = parser.parse_args()
    main(num_periods=args.periods)
