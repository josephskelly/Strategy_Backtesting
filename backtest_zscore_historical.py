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
import requests


def _yahoo_chart(ticker: str, range_: str = "5d", interval: str = "1d") -> list[dict]:
    """Fetch OHLCV data from Yahoo Finance's chart API for a single ticker."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?range={range_}&interval={interval}"
    )
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    quotes = result["indicators"]["quote"][0]

    rows = []
    for i, ts in enumerate(timestamps):
        rows.append({
            "date": pd.Timestamp(ts, unit="s").normalize(),
            "close": quotes["close"][i],
        })
    return rows


def fetch_sp500_data(range_: str = "5y") -> pd.DataFrame:
    """Fetch S&P 500 (SPY) closing prices."""
    rows = _yahoo_chart("SPY", range_=range_)
    df = pd.DataFrame(rows).set_index("date")
    df.index.name = "Date"
    return df[["close"]].rename(columns={"close": "SPY"})


def backtest_sp500_buyandhold(prices: pd.Series, initial_capital: float = 10000) -> dict:
    """Simple buy-and-hold S&P 500 strategy."""
    if len(prices) < 2:
        return {"return_pct": 0, "final_value": initial_capital, "pnl": 0}

    # Buy at the start
    shares = initial_capital / prices.iloc[0]

    # Sell at the end
    final_value = shares * prices.iloc[-1]
    pnl = final_value - initial_capital
    return_pct = (pnl / initial_capital) * 100

    return {
        "return_pct": return_pct,
        "final_value": final_value,
        "pnl": pnl,
    }


def run_single_period(start_date: str, end_date: str) -> dict:
    """Run backtest for a single period (Leveraged ETF + S&P 500 comparison)."""
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

        # Run leveraged ETF backtest
        backtester = PortfolioStddevBacktester(
            prices_df=leveraged_closes,
            initial_capital=10000,
            lookback_period=20,
            z_threshold=1.0,
            max_sector_allocation=0.25,
        )
        lev_results = backtester.run()

        # Fetch S&P 500 data
        sp500_data = fetch_sp500_data(range_=range_str)
        sp500_data = sp500_data[(sp500_data.index >= start) & (sp500_data.index <= end)]

        if len(sp500_data) < 2:
            return None

        # Run S&P 500 buy-and-hold
        sp500_results = backtest_sp500_buyandhold(sp500_data["SPY"])

        return {
            "period": date_range,
            "start": start_date,
            "end": end_date,
            "lev_return": lev_results.total_return,
            "lev_value": lev_results.final_value,
            "lev_drawdown": lev_results.max_drawdown,
            "lev_sharpe": lev_results.sharpe_ratio,
            "lev_trades": lev_results.num_trades,
            "lev_invested_pct": lev_results.avg_invested_pct,
            "lev_pnl": lev_results.final_pnl,
            "sp500_return": sp500_results["return_pct"],
            "sp500_value": sp500_results["final_value"],
            "sp500_pnl": sp500_results["pnl"],
            "outperformance": lev_results.total_return - sp500_results["return_pct"],
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
            diff_indicator = "✓" if result['lev_return'] > result['sp500_return'] else "✗"
            print(f"  Leveraged: {result['lev_return']:>7.2f}% | S&P500: {result['sp500_return']:>7.2f}% ({diff_indicator} {result['outperformance']:+.2f}%)")

        time.sleep(0.5)  # Be nice to the API

    if not results:
        print("No valid results obtained.")
        return

    # Create results dataframe
    results_df = pd.DataFrame(results)

    print("\n" + "=" * 150)
    print("DETAILED RESULTS")
    print("=" * 150)

    display_cols = ["period", "lev_return", "sp500_return", "outperformance", "lev_sharpe", "lev_trades"]
    display_df = results_df[display_cols].copy()
    display_df.columns = ["Period", "Leveraged %", "S&P500 %", "Outperformance", "Sharpe", "Trades"]
    print(display_df.to_string(index=False))

    # Summary statistics
    print("\n" + "=" * 150)
    print("HISTORICAL PERFORMANCE SUMMARY")
    print("=" * 150)

    lev_returns = results_df["lev_return"]
    sp500_returns = results_df["sp500_return"]
    drawdowns = results_df["lev_drawdown"]
    sharpes = results_df["lev_sharpe"]
    trades = results_df["lev_trades"]

    print(f"\n{'Metric':<35} | {'Leveraged ETF':<30} | {'S&P 500 B&H':<30}")
    print("-" * 150)
    print(f"{'Mean Return':<35} | {lev_returns.mean():>7.2f}% {'':<22} | {sp500_returns.mean():>7.2f}% {'':<22}")
    print(f"{'Median Return':<35} | {lev_returns.median():>7.2f}% {'':<22} | {sp500_returns.median():>7.2f}% {'':<22}")
    print(f"{'Std Dev':<35} | {lev_returns.std():>7.2f}% {'':<22} | {sp500_returns.std():>7.2f}% {'':<22}")
    print(f"{'Min Return':<35} | {lev_returns.min():>7.2f}% {'':<22} | {sp500_returns.min():>7.2f}% {'':<22}")
    print(f"{'Max Return':<35} | {lev_returns.max():>7.2f}% {'':<22} | {sp500_returns.max():>7.2f}% {'':<22}")
    print(f"{'Positive Periods':<35} | {(lev_returns > 0).sum()}/{len(lev_returns)} ({(lev_returns > 0).sum()/len(lev_returns)*100:.1f}%) | {(sp500_returns > 0).sum()}/{len(sp500_returns)} ({(sp500_returns > 0).sum()/len(sp500_returns)*100:.1f}%)")

    print(f"\nRisk Metrics:")
    print(f"  Avg Max Drawdown (Leveraged):    {drawdowns.mean():>7.2f}%")
    print(f"  Avg Sharpe Ratio (Leveraged):    {sharpes.mean():>7.3f}")
    print(f"  Avg Trades per Period:           {trades.mean():>7.0f}")

    print(f"\nOutperformance vs S&P 500:")
    print(f"  Avg Outperformance:              {results_df['outperformance'].mean():>7.2f}%")
    print(f"  Win Rate (Periods Better):       {(results_df['outperformance'] > 0).sum()}/{len(results_df)} ({(results_df['outperformance'] > 0).sum()/len(results_df)*100:.1f}%)")

    # Market periods breakdown
    print("\n" + "=" * 150)
    print("MARKET PERIOD ANALYSIS")
    print("=" * 150)

    print(f"\nBull Markets (S&P 500 Return > 15%):")
    bull = results_df[results_df["sp500_return"] > 15]
    if len(bull) > 0:
        print(f"  Count: {len(bull)} periods")
        print(f"  Avg Leveraged Return: {bull['lev_return'].mean():.2f}%")
        print(f"  Avg S&P 500 Return: {bull['sp500_return'].mean():.2f}%")
        print(f"  Avg Outperformance: {bull['outperformance'].mean():.2f}%")
        print(f"  Avg Sharpe: {bull['lev_sharpe'].mean():.3f}")

    print(f"\nNormal Markets (0% < S&P 500 Return < 15%):")
    normal = results_df[(results_df["sp500_return"] > 0) & (results_df["sp500_return"] <= 15)]
    if len(normal) > 0:
        print(f"  Count: {len(normal)} periods")
        print(f"  Avg Leveraged Return: {normal['lev_return'].mean():.2f}%")
        print(f"  Avg S&P 500 Return: {normal['sp500_return'].mean():.2f}%")
        print(f"  Avg Outperformance: {normal['outperformance'].mean():.2f}%")
        print(f"  Avg Sharpe: {normal['lev_sharpe'].mean():.3f}")

    print(f"\nBear Markets (S&P 500 Return < 0%):")
    bear = results_df[results_df["sp500_return"] < 0]
    if len(bear) > 0:
        print(f"  Count: {len(bear)} periods")
        print(f"  Avg Leveraged Return: {bear['lev_return'].mean():.2f}%")
        print(f"  Avg S&P 500 Return: {bear['sp500_return'].mean():.2f}%")
        print(f"  Avg Outperformance: {bear['outperformance'].mean():.2f}%")
        print(f"  Avg Sharpe: {bear['lev_sharpe'].mean():.3f}")

    # Time period breakdown
    print("\n" + "=" * 150)
    print("PERFORMANCE BY TIME PERIOD")
    print("=" * 150)

    for period_start in [2021, 2022, 2023, 2024]:
        period_results = results_df[
            (results_df["start"].str[:4].astype(int) == period_start)
        ]
        if len(period_results) > 0:
            print(f"\n{period_start}:")
            print(f"  Periods: {len(period_results)}")
            print(f"  Avg Leveraged Return: {period_results['lev_return'].mean():>7.2f}%")
            print(f"  Avg S&P 500 Return: {period_results['sp500_return'].mean():>7.2f}%")
            print(f"  Avg Outperformance: {period_results['outperformance'].mean():>7.2f}%")
            print(f"  Avg Sharpe: {period_results['lev_sharpe'].mean():>7.3f}")
            print(f"  Avg Trades: {period_results['lev_trades'].mean():>7.0f}")

    # Save results
    output_file = "backtest_zscore_historical_results.csv"
    results_df.to_csv(output_file, index=False)
    print(f"\n✓ Detailed results saved to {output_file}")

    # Overall assessment
    print("\n" + "=" * 150)
    print("ASSESSMENT: LEVERAGED ETF vs S&P 500 BUY-AND-HOLD")
    print("=" * 150)

    overall_lev_return = lev_returns.mean()
    overall_sp500_return = sp500_returns.mean()
    overall_outperformance = results_df['outperformance'].mean()
    overall_win_rate = (results_df['outperformance'] > 0).sum() / len(results_df) * 100
    overall_sharpe = sharpes.mean()

    print(f"""
STRATEGY PERFORMANCE ACROSS 5 YEARS (2021-2026):

Leveraged ETF Mean Reversion:
  • Average Return: {overall_lev_return:.2f}% per 2-year period
  • Win Rate vs S&P 500: {overall_win_rate:.1f}%
  • Avg Outperformance: {overall_outperformance:+.2f}%
  • Avg Drawdown: {drawdowns.mean():.2f}%
  • Sharpe Ratio: {overall_sharpe:.3f}

S&P 500 Buy-and-Hold (Benchmark):
  • Average Return: {overall_sp500_return:.2f}% per 2-year period

Comparison:
  • Leveraged ETF Outperformance: {overall_lev_return - overall_sp500_return:+.2f}% absolute
  • Relative Outperformance: {(overall_lev_return / overall_sp500_return - 1) * 100:+.1f}%

Assessment:
""")

    if overall_outperformance > 15:
        print(f"  ✅ EXCELLENT: Significant outperformance (+{overall_outperformance:.2f}%) with {overall_win_rate:.0f}% win rate")
    elif overall_outperformance > 10:
        print(f"  ✅ STRONG: Consistent outperformance (+{overall_outperformance:.2f}%) with {overall_win_rate:.0f}% win rate")
    elif overall_outperformance > 5:
        print(f"  ✓ GOOD: Moderate outperformance (+{overall_outperformance:.2f}%) with {overall_win_rate:.0f}% win rate")
    elif overall_outperformance > 0:
        print(f"  ⚠️  MODEST: Slight outperformance (+{overall_outperformance:.2f}%) with {overall_win_rate:.0f}% win rate")
    else:
        print(f"  ❌ UNDERPERFORMANCE: Strategy trails S&P 500 by {abs(overall_outperformance):.2f}%")

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
