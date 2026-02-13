"""
Compare all three strategies across random 2-year periods.

1. Dynamic Allocation (Mean Reversion Only)
2. Dynamic Rebalancing (Sell Winners to Buy Dips)
3. Buy-and-Hold Benchmark
"""

import pandas as pd
import numpy as np
from sector_etfs import fetch_sector_closes, SECTOR_ETFS
from portfolio_stddev_backtest import PortfolioStddevBacktester
from dynamic_rebalancing_backtest import DynamicRebalancingBacktester
from datetime import timedelta
import random


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
    """Run mean reversion backtest."""
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


def run_rebalancing_backtest(
    prices_df: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> dict:
    """Run dynamic rebalancing backtest."""
    period_data = prices_df.loc[start_date:end_date].copy()

    if len(period_data) < 30:
        return None

    backtester = DynamicRebalancingBacktester(
        prices_df=period_data,
        initial_capital=10000,
        lookback_period=20,
        z_threshold=1.0,
        max_sector_allocation=0.30,
        investment_threshold=0.95,
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


def main():
    """Run all three strategies on random periods."""
    print("=" * 140)
    print("STRATEGY COMPARISON: Mean Reversion vs Dynamic Rebalancing vs Buy-and-Hold")
    print("=" * 140)
    print()

    # Fetch full history
    prices_df = fetch_full_price_history(years=5)
    print(f"Data range: {prices_df.index[0].date()} to {prices_df.index[-1].date()}")
    print()

    # Generate random 2-year periods
    print("Generating 10 random 2-year periods...")
    periods = generate_random_2year_periods(prices_df, num_periods=10)
    print()

    # Run backtests
    mr_results = []      # Mean reversion (original)
    rb_results = []      # Rebalancing
    bh_results = []      # Buy-and-hold

    print("Running backtests on random periods...")
    print()

    for i, (start, end) in enumerate(periods, 1):
        print(f"Period {i}/10: {start.date()} to {end.date()}", end=" ... ")

        # Mean reversion
        mr = run_mean_reversion_backtest(prices_df, start, end)
        if mr:
            mr_results.append(mr)
            print(f"MR: {mr['return_pct']:+6.2f}%", end=" | ")

        # Rebalancing
        rb = run_rebalancing_backtest(prices_df, start, end)
        if rb:
            rb_results.append(rb)
            print(f"RB: {rb['return_pct']:+6.2f}%", end=" | ")

        # Buy-and-hold
        bh = calculate_buy_and_hold_return(prices_df, start, end)
        if bh:
            bh_results.append(bh)
            print(f"B&H: {bh['return_pct']:+6.2f}%")
        else:
            print()

    print()
    print("=" * 140)
    print("SUMMARY STATISTICS")
    print("=" * 140)
    print()

    mr_df = pd.DataFrame(mr_results)
    rb_df = pd.DataFrame(rb_results)
    bh_df = pd.DataFrame(bh_results)

    print(f"{'Metric':<30} {'Mean Reversion':>15} {'Rebalancing':>15} {'Buy-and-Hold':>15}")
    print("-" * 80)

    print(f"{'Average Return':<30} {mr_df['return_pct'].mean():>14.2f}% {rb_df['return_pct'].mean():>14.2f}% {bh_df['return_pct'].mean():>14.2f}%")
    print(f"{'Median Return':<30} {mr_df['return_pct'].median():>14.2f}% {rb_df['return_pct'].median():>14.2f}% {bh_df['return_pct'].median():>14.2f}%")
    print(f"{'Return Std Dev':<30} {mr_df['return_pct'].std():>14.2f}% {rb_df['return_pct'].std():>14.2f}% {bh_df['return_pct'].std():>14.2f}%")
    print(f"{'Min Return':<30} {mr_df['return_pct'].min():>14.2f}% {rb_df['return_pct'].min():>14.2f}% {bh_df['return_pct'].min():>14.2f}%")
    print(f"{'Max Return':<30} {mr_df['return_pct'].max():>14.2f}% {rb_df['return_pct'].max():>14.2f}% {bh_df['return_pct'].max():>14.2f}%")
    print()
    print(f"{'Avg Max Drawdown':<30} {mr_df['max_drawdown'].mean():>14.2f}% {rb_df['max_drawdown'].mean():>14.2f}% {bh_df['max_drawdown'].mean():>14.2f}%")
    print(f"{'Avg Sharpe Ratio':<30} {mr_df['sharpe_ratio'].mean():>14.2f}  {rb_df['sharpe_ratio'].mean():>14.2f}  {bh_df['sharpe_ratio'].mean():>14.2f}")
    print(f"{'Avg Trades per Period':<30} {mr_df['num_trades'].mean():>14.0f}  {rb_df['num_trades'].mean():>14.0f}  {'N/A':>14}")
    print(f"{'Avg Capital Deployed':<30} {mr_df['avg_deployed'].mean():>14.2f}% {rb_df['avg_deployed'].mean():>14.2f}% {'100.00%':>14}")
    print()
    print(f"{'Positive Periods':<30} {(mr_df['return_pct'] > 0).sum():>14}/10 {(rb_df['return_pct'] > 0).sum():>14}/10 {(bh_df['return_pct'] > 0).sum():>14}/10")

    # Detailed comparison table
    print()
    print("=" * 140)
    print("PERIOD-BY-PERIOD COMPARISON")
    print("=" * 140)
    print()

    comparison = []
    for mr, rb, bh in zip(mr_results, rb_results, bh_results):
        mr_vs_rb = mr['return_pct'] - rb['return_pct']
        mr_vs_bh = mr['return_pct'] - bh['return_pct']
        rb_vs_bh = rb['return_pct'] - bh['return_pct']

        comparison.append({
            "Period": f"{mr['start_date']} to {mr['end_date']}",
            "Mean Reversion": mr['return_pct'],
            "Rebalancing": rb['return_pct'],
            "Buy-and-Hold": bh['return_pct'],
            "MR vs RB": mr_vs_rb,
            "MR vs B&H": mr_vs_bh,
        })

    comp_df = pd.DataFrame(comparison)
    print(comp_df.to_string(index=False))

    # Determine best strategy for each period
    print()
    print("=" * 140)
    print("WHICH STRATEGY WINS EACH PERIOD?")
    print("=" * 140)
    print()

    mr_wins = 0
    rb_wins = 0
    bh_wins = 0

    for mr, rb, bh in zip(mr_results, rb_results, bh_results):
        best_return = max(mr['return_pct'], rb['return_pct'], bh['return_pct'])

        if mr['return_pct'] == best_return:
            mr_wins += 1
            winner = "Mean Reversion"
        elif rb['return_pct'] == best_return:
            rb_wins += 1
            winner = "Rebalancing"
        else:
            bh_wins += 1
            winner = "Buy-and-Hold"

        print(f"{mr['start_date']} to {mr['end_date']}: {winner} ({best_return:+6.2f}%)")

    print()
    print(f"Win Count:  Mean Reversion: {mr_wins}/10  |  Rebalancing: {rb_wins}/10  |  Buy-and-Hold: {bh_wins}/10")

    # Save comparison
    comp_df.to_csv("strategy_comparison.csv", index=False)
    mr_df.to_csv("mean_reversion_random.csv", index=False)
    rb_df.to_csv("rebalancing_random.csv", index=False)

    print()
    print("✓ Results saved:")
    print("  - strategy_comparison.csv")
    print("  - mean_reversion_random.csv")
    print("  - rebalancing_random.csv")
    print()


if __name__ == "__main__":
    main()
