"""
Portfolio Backtest across random 2-year periods vs Buy-and-Hold benchmark.

Tests strategy robustness by running multiple backtests on randomly selected
2-year windows and comparing to passive buy-and-hold returns.
"""

import pandas as pd
import numpy as np
from sector_etfs import fetch_sector_closes, SECTOR_ETFS
from portfolio_stddev_backtest import PortfolioStddevBacktester
from datetime import timedelta
import random


def fetch_full_price_history(years: int = 5) -> pd.DataFrame:
    """Fetch full price history for random period selection."""
    print(f"Fetching {years}-year price history...")
    closes = fetch_sector_closes(range_=f"{years}y")
    return closes


def run_backtest_on_period(
    prices_df: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> dict:
    """Run dynamic allocation backtest on specific date range."""
    # Extract period data
    period_data = prices_df.loc[start_date:end_date].copy()

    if len(period_data) < 30:  # Need enough data for 20-day lookback + buffer
        return None

    # Run backtest
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
        "days": len(period_data),
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

    # Equal-weight buy-and-hold: start with $909 per sector
    initial_per_sector = 10000 / len(period_data.columns)

    # Calculate returns for each sector
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

    # Max drawdown for first sector (rough estimate)
    first_ticker = period_data.columns[0]
    prices = period_data[first_ticker].values
    running_max = np.maximum.accumulate(prices)
    drawdowns = (prices - running_max) / running_max * 100
    max_drawdown = drawdowns.min()

    return {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "days": len(period_data),
        "return_pct": portfolio_return,
        "final_value": 10000 * (1 + portfolio_return / 100),
        "max_drawdown": max_drawdown,
        "sharpe_ratio": 0,  # N/A for B&H
    }


def generate_random_2year_periods(
    prices_df: pd.DataFrame, num_periods: int = 10
) -> list:
    """Generate random non-overlapping 2-year periods from data."""
    dates = prices_df.index
    min_date = dates[0]
    max_date = dates[-1]

    # Maximum start date is 2 years before max_date
    two_years = timedelta(days=365 * 2)
    max_start_date = max_date - two_years

    if max_start_date <= min_date:
        print("Not enough data for multiple 2-year periods")
        return []

    periods = []
    for _ in range(num_periods):
        # Random start date
        days_available = (max_start_date - min_date).days
        random_days = random.randint(0, max(1, days_available))
        start = min_date + timedelta(days=random_days)
        end = start + two_years

        # Make sure end date is in our data
        if end > max_date:
            end = max_date
            start = end - two_years

        periods.append((start, end))

    return periods


def main():
    """Run backtests on random periods vs buy-and-hold."""
    print("=" * 120)
    print("PORTFOLIO STRATEGY vs BUY-AND-HOLD ACROSS RANDOM 2-YEAR PERIODS")
    print("=" * 120)
    print()

    # Fetch full history
    prices_df = fetch_full_price_history(years=5)
    print(f"Data range: {prices_df.index[0].date()} to {prices_df.index[-1].date()}")
    print(f"Total days: {len(prices_df)}")
    print()

    # Generate random 2-year periods
    print("Generating 10 random 2-year periods...")
    periods = generate_random_2year_periods(prices_df, num_periods=10)
    print(f"Generated {len(periods)} periods")
    print()

    # Run backtests
    strategy_results = []
    bh_results = []

    print("Running backtests on random periods...")
    print()

    for i, (start, end) in enumerate(periods, 1):
        print(f"Period {i}/10: {start.date()} to {end.date()}", end=" ... ")

        # Strategy backtest
        strat = run_backtest_on_period(prices_df, start, end)
        if strat:
            strategy_results.append(strat)
            print(f"Strategy: {strat['return_pct']:+6.2f}%", end=" | ")

        # Buy-and-hold
        bh = calculate_buy_and_hold_return(prices_df, start, end)
        if bh:
            bh_results.append(bh)
            print(f"B&H: {bh['return_pct']:+6.2f}%", end=" | ")

        if strat and bh:
            outperformance = strat["return_pct"] - bh["return_pct"]
            print(f"Outperformance: {outperformance:+6.2f}%")
        else:
            print()

    print()
    print("=" * 120)
    print("STRATEGY PERFORMANCE SUMMARY")
    print("=" * 120)
    print()

    if strategy_results:
        strat_df = pd.DataFrame(strategy_results)

        print(f"Average Return:           {strat_df['return_pct'].mean():>8.2f}%")
        print(f"Median Return:            {strat_df['return_pct'].median():>8.2f}%")
        print(f"Std Dev:                  {strat_df['return_pct'].std():>8.2f}%")
        print(f"Min Return:               {strat_df['return_pct'].min():>8.2f}%")
        print(f"Max Return:               {strat_df['return_pct'].max():>8.2f}%")
        print()
        print(f"Average Max Drawdown:     {strat_df['max_drawdown'].mean():>8.2f}%")
        print(f"Average Sharpe Ratio:     {strat_df['sharpe_ratio'].mean():>8.2f}")
        print(f"Average Trades:           {strat_df['num_trades'].mean():>8.0f}")
        print(f"Average Capital Deployed: {strat_df['avg_deployed'].mean():>8.2f}%")
        print()
        print(f"Positive Return Periods:  {(strat_df['return_pct'] > 0).sum()}/10")
        print(f"Win Rate:                 {(strat_df['return_pct'] > 0).sum() * 10}%")

    print()
    print("=" * 120)
    print("BUY-AND-HOLD PERFORMANCE SUMMARY")
    print("=" * 120)
    print()

    if bh_results:
        bh_df = pd.DataFrame(bh_results)

        print(f"Average Return:           {bh_df['return_pct'].mean():>8.2f}%")
        print(f"Median Return:            {bh_df['return_pct'].median():>8.2f}%")
        print(f"Std Dev:                  {bh_df['return_pct'].std():>8.2f}%")
        print(f"Min Return:               {bh_df['return_pct'].min():>8.2f}%")
        print(f"Max Return:               {bh_df['return_pct'].max():>8.2f}%")
        print()
        print(f"Average Max Drawdown:     {bh_df['max_drawdown'].mean():>8.2f}%")
        print()
        print(f"Positive Return Periods:  {(bh_df['return_pct'] > 0).sum()}/10")
        print(f"Win Rate:                 {(bh_df['return_pct'] > 0).sum() * 10}%")

    print()
    print("=" * 120)
    print("STRATEGY vs BUY-AND-HOLD COMPARISON")
    print("=" * 120)
    print()

    if strategy_results and bh_results:
        strat_avg = strat_df['return_pct'].mean()
        bh_avg = bh_df['return_pct'].mean()
        outperformance = strat_avg - bh_avg

        print(f"Strategy Avg Return:      {strat_avg:>8.2f}%")
        print(f"B&H Avg Return:           {bh_avg:>8.2f}%")
        print(f"Outperformance:           {outperformance:>8.2f}% {'✓ BETTER' if outperformance > 0 else '✗ WORSE'}")
        print()

        strat_std = strat_df['return_pct'].std()
        bh_std = bh_df['return_pct'].std()

        print(f"Strategy Return Volatility: {strat_std:>8.2f}%")
        print(f"B&H Return Volatility:      {bh_std:>8.2f}%")
        print()

        strat_dd = strat_df['max_drawdown'].mean()
        bh_dd = bh_df['max_drawdown'].mean()

        print(f"Strategy Avg Max Drawdown:   {strat_dd:>8.2f}%")
        print(f"B&H Avg Max Drawdown:        {bh_dd:>8.2f}%")
        print()

        strat_wins = (strat_df['return_pct'] > 0).sum()
        bh_wins = (bh_df['return_pct'] > 0).sum()

        print(f"Strategy Positive Periods:   {strat_wins}/10")
        print(f"B&H Positive Periods:        {bh_wins}/10")

    # Detailed results table
    print()
    print("=" * 120)
    print("DETAILED RESULTS BY PERIOD")
    print("=" * 120)
    print()

    comparison = []
    for strat, bh in zip(strategy_results, bh_results):
        comparison.append({
            "Period": f"{strat['start_date']} to {strat['end_date']}",
            "Strategy Return": strat['return_pct'],
            "B&H Return": bh['return_pct'],
            "Outperformance": strat['return_pct'] - bh['return_pct'],
            "Drawdown": strat['max_drawdown'],
            "Trades": strat['num_trades'],
        })

    comp_df = pd.DataFrame(comparison)
    print(comp_df.to_string(index=False))

    # Save results
    strat_df.to_csv("strategy_random_periods.csv", index=False)
    bh_df.to_csv("buyhold_random_periods.csv", index=False)
    comp_df.to_csv("comparison_random_periods.csv", index=False)

    print()
    print("✓ Results saved to:")
    print("  - strategy_random_periods.csv")
    print("  - buyhold_random_periods.csv")
    print("  - comparison_random_periods.csv")
    print()


if __name__ == "__main__":
    main()
