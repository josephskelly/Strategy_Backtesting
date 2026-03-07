"""
Simulated Historical Backtest (20-30 Years)

Test mean reversion strategy on simulated 2x leveraged sector ETFs
across 20-30 years of market history (1995-2026) using regular sector ETF data
multiplied by 2x to simulate leverage.

Sector ETFs available:
- XLK: Technology
- XLV: Healthcare
- XLE: Energy
- XLI: Industrials
- XLF: Financials
- XLY: Consumer Discretionary
- XLP: Consumer Staples
- XLRE: Real Estate
- XLU: Utilities
- XLM: Materials
- XLCO: Communication Services
"""

import os

import pandas as pd
import numpy as np
import argparse
from datetime import datetime, timedelta
from backtest_engine import PortfolioStddevBacktester
import time
import requests

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# Regular (1x) sector ETFs for historical data
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLV": "Healthcare",
    "XLE": "Energy",
    "XLI": "Industrials",
    "XLF": "Financials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLM": "Materials",
}


def _yahoo_chart(ticker: str, range_: str = "5d", interval: str = "1d") -> list[dict]:
    """Fetch OHLCV data from Yahoo Finance's chart API."""
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


def fetch_sector_closes(range_: str = "30y") -> pd.DataFrame:
    """Fetch closing prices for all sector ETFs."""
    closes = pd.DataFrame()

    for ticker in SECTOR_ETFS:
        try:
            rows = _yahoo_chart(ticker, range_=range_)
            df = pd.DataFrame(rows).set_index("date")
            closes[ticker] = df["close"]
            time.sleep(0.2)
        except Exception as e:
            print(f"Warning: Could not fetch {ticker}: {e}")
            continue

    closes.index.name = "Date"
    return closes


def fetch_sp500_data(range_: str = "30y") -> pd.DataFrame:
    """Fetch S&P 500 (SPY) closing prices."""
    rows = _yahoo_chart("SPY", range_=range_)
    df = pd.DataFrame(rows).set_index("date")
    df.index.name = "Date"
    return df[["close"]].rename(columns={"close": "SPY"})


def simulate_2x_leverage(prices_df: pd.DataFrame) -> pd.DataFrame:
    """
    Simulate 2x leveraged ETFs by multiplying sector price movements by 2.

    For each ticker, calculates daily returns, multiplies by 2, then reconstructs
    prices to represent 2x leverage.
    """
    leveraged = pd.DataFrame(index=prices_df.index)

    for ticker in prices_df.columns:
        if ticker not in prices_df.columns:
            continue

        prices = prices_df[ticker].dropna()
        if len(prices) < 2:
            continue

        # Calculate daily returns
        daily_returns = prices.pct_change()

        # Multiply returns by 2x for leverage
        leveraged_returns = daily_returns * 2

        # Reconstruct prices from leveraged returns
        leveraged_prices = prices.iloc[0] * (1 + leveraged_returns).cumprod()

        leveraged[ticker] = leveraged_prices

    return leveraged


def backtest_sp500_buyandhold(prices: pd.Series, initial_capital: float = 10000) -> dict:
    """Simple buy-and-hold S&P 500 strategy."""
    if len(prices) < 2:
        return {"return_pct": 0, "final_value": initial_capital, "pnl": 0}

    shares = initial_capital / prices.iloc[0]
    final_value = shares * prices.iloc[-1]
    pnl = final_value - initial_capital
    return_pct = (pnl / initial_capital) * 100

    return {
        "return_pct": return_pct,
        "final_value": final_value,
        "pnl": pnl,
    }


def run_single_period(start_date: str, end_date: str, sector_closes: pd.DataFrame, sp500_data: pd.DataFrame) -> dict:
    """Run backtest for a single historical period."""
    date_range = f"{start_date} to {end_date}"
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)

    try:
        # Filter sector data to date range
        mask = (sector_closes.index >= start) & (sector_closes.index <= end)
        sector_data = sector_closes[mask]

        if len(sector_data) < 21:
            return None

        # Simulate 2x leverage
        leveraged_closes = simulate_2x_leverage(sector_data)
        leveraged_closes = leveraged_closes.dropna(axis=1, how='all').dropna()

        if len(leveraged_closes) < 21 or len(leveraged_closes.columns) < 5:
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

        # Filter S&P 500 data to same date range
        sp500_filtered = sp500_data[(sp500_data.index >= start) & (sp500_data.index <= end)]

        if len(sp500_filtered) < 2:
            return None

        # Run S&P 500 buy-and-hold
        sp500_results = backtest_sp500_buyandhold(sp500_filtered["SPY"])

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
            "sp500_return": sp500_results["return_pct"],
            "sp500_value": sp500_results["final_value"],
            "outperformance": lev_results.total_return - sp500_results["return_pct"],
        }
    except Exception as e:
        print(f"  Error in period {date_range}: {str(e)[:80]}")
        return None


def run_simulated_historical_backtest(num_periods: int = 30):
    """Test across 20-30 years of simulated 2x leveraged data."""
    print("=" * 160)
    print("SIMULATED HISTORICAL BACKTEST: 2X LEVERAGED SECTORS (1995-2026)")
    print("=" * 160)
    print(f"\nFetching sector ETF data (going back ~30 years)...\n")

    # Fetch data
    sector_closes = fetch_sector_closes(range_="30y")
    sp500_data = fetch_sp500_data(range_="30y")

    if len(sector_closes) < 100:
        print("Not enough historical data available.")
        return

    earliest_date = sector_closes.index.min()
    latest_date = sector_closes.index.max()

    print(f"Available data range: {earliest_date.strftime('%Y-%m-%d')} to {latest_date.strftime('%Y-%m-%d')}")
    print(f"Data points: {len(sector_closes)}")
    print(f"Sector ETFs available: {len(sector_closes.columns)}\n")

    # Generate well-spaced random 2-year periods
    min_start = earliest_date + timedelta(days=730)
    max_start = latest_date - timedelta(days=730)

    available_days = (max_start - min_start).days
    if available_days < 0:
        print("Not enough data for 2-year periods")
        return

    min_spacing = 180  # 6 months minimum between periods

    selected_periods = []
    used_starts = set()

    print(f"Generating {num_periods} random 2-year periods with minimum 6-month spacing...\n")

    for attempt in range(num_periods * 50):
        if len(selected_periods) >= num_periods:
            break

        random_offset = np.random.randint(0, max(1, available_days))
        period_start = min_start + timedelta(days=random_offset)
        period_end = period_start + timedelta(days=730)

        is_valid = True
        for used_start in used_starts:
            if abs((period_start - used_start).days) < min_spacing:
                is_valid = False
                break

        if is_valid and period_end <= latest_date:
            selected_periods.append((period_start, period_end))
            used_starts.add(period_start)

    selected_periods.sort()

    print(f"Testing {len(selected_periods)} periods...\n")
    print("=" * 160)

    results = []
    for i, (period_start, period_end) in enumerate(selected_periods):
        period_str = f"Period {i+1}/{len(selected_periods)}: {period_start.strftime('%Y-%m-%d')} to {period_end.strftime('%Y-%m-%d')}"
        print(period_str)

        result = run_single_period(
            period_start.strftime("%Y-%m-%d"),
            period_end.strftime("%Y-%m-%d"),
            sector_closes,
            sp500_data,
        )

        if result:
            results.append(result)
            diff_indicator = "✓" if result['lev_return'] > result['sp500_return'] else "✗"
            print(f"  Simulated 2x: {result['lev_return']:>7.2f}% | S&P 500: {result['sp500_return']:>7.2f}% ({diff_indicator} {result['outperformance']:+.2f}%)")

        time.sleep(0.3)

    if not results:
        print("No valid results obtained.")
        return

    results_df = pd.DataFrame(results)

    print("\n" + "=" * 160)
    print("DETAILED RESULTS")
    print("=" * 160)

    display_df = results_df[["period", "lev_return", "sp500_return", "outperformance", "lev_sharpe", "lev_trades"]].copy()
    display_df.columns = ["Period", "2x Sim %", "S&P500 %", "Outperformance", "Sharpe", "Trades"]
    print(display_df.to_string(index=False))

    # Summary statistics
    print("\n" + "=" * 160)
    print("HISTORICAL PERFORMANCE SUMMARY (1995-2026)")
    print("=" * 160)

    lev_returns = results_df["lev_return"]
    sp500_returns = results_df["sp500_return"]
    drawdowns = results_df["lev_drawdown"]
    sharpes = results_df["lev_sharpe"]
    trades = results_df["lev_trades"]

    print(f"\n{'Metric':<40} | {'Sim 2x Leverage':<32} | {'S&P 500 B&H':<32}")
    print("-" * 160)
    print(f"{'Mean Return':<40} | {lev_returns.mean():>7.2f}% {'':<24} | {sp500_returns.mean():>7.2f}% {'':<24}")
    print(f"{'Median Return':<40} | {lev_returns.median():>7.2f}% {'':<24} | {sp500_returns.median():>7.2f}% {'':<24}")
    print(f"{'Std Dev':<40} | {lev_returns.std():>7.2f}% {'':<24} | {sp500_returns.std():>7.2f}% {'':<24}")
    print(f"{'Min Return':<40} | {lev_returns.min():>7.2f}% {'':<24} | {sp500_returns.min():>7.2f}% {'':<24}")
    print(f"{'Max Return':<40} | {lev_returns.max():>7.2f}% {'':<24} | {sp500_returns.max():>7.2f}% {'':<24}")
    print(f"{'Positive Periods':<40} | {(lev_returns > 0).sum()}/{len(lev_returns)} ({(lev_returns > 0).sum()/len(lev_returns)*100:.1f}%) | {(sp500_returns > 0).sum()}/{len(sp500_returns)} ({(sp500_returns > 0).sum()/len(sp500_returns)*100:.1f}%)")

    print(f"\nRisk Metrics:")
    print(f"  Avg Max Drawdown (Sim 2x):       {drawdowns.mean():>7.2f}%")
    print(f"  Worst Drawdown (Sim 2x):        {drawdowns.min():>7.2f}%")
    print(f"  Avg Sharpe Ratio (Sim 2x):      {sharpes.mean():>7.3f}")
    print(f"  Avg Trades per Period:          {trades.mean():>7.0f}")

    print(f"\nOutperformance vs S&P 500:")
    print(f"  Avg Outperformance:             {results_df['outperformance'].mean():>7.2f}%")
    print(f"  Win Rate (Periods Better):      {(results_df['outperformance'] > 0).sum()}/{len(results_df)} ({(results_df['outperformance'] > 0).sum()/len(results_df)*100:.1f}%)")

    # Market periods breakdown
    print("\n" + "=" * 160)
    print("MARKET REGIME ANALYSIS")
    print("=" * 160)

    print(f"\nBull Markets (S&P 500 Return > 20%):")
    bull = results_df[results_df["sp500_return"] > 20]
    if len(bull) > 0:
        print(f"  Count: {len(bull)} periods")
        print(f"  Avg 2x Return: {bull['lev_return'].mean():.2f}%")
        print(f"  Avg S&P 500 Return: {bull['sp500_return'].mean():.2f}%")
        print(f"  Avg Outperformance: {bull['outperformance'].mean():.2f}%")
    else:
        print(f"  Count: 0 periods")

    print(f"\nNormal Markets (0% < S&P 500 Return < 20%):")
    normal = results_df[(results_df["sp500_return"] > 0) & (results_df["sp500_return"] <= 20)]
    if len(normal) > 0:
        print(f"  Count: {len(normal)} periods")
        print(f"  Avg 2x Return: {normal['lev_return'].mean():.2f}%")
        print(f"  Avg S&P 500 Return: {normal['sp500_return'].mean():.2f}%")
        print(f"  Avg Outperformance: {normal['outperformance'].mean():.2f}%")
    else:
        print(f"  Count: 0 periods")

    print(f"\nBear Markets (S&P 500 Return < 0%):")
    bear = results_df[results_df["sp500_return"] < 0]
    if len(bear) > 0:
        print(f"  Count: {len(bear)} periods")
        print(f"  Avg 2x Return: {bear['lev_return'].mean():.2f}%")
        print(f"  Avg S&P 500 Return: {bear['sp500_return'].mean():.2f}%")
        print(f"  Avg Outperformance: {bear['outperformance'].mean():.2f}%")
    else:
        print(f"  Count: 0 periods")

    # Time period breakdown
    print("\n" + "=" * 160)
    print("PERFORMANCE BY DECADE")
    print("=" * 160)

    for year_start in range(2000, 2030, 10):
        decade_results = results_df[
            (results_df["start"].str[:4].astype(int) >= year_start) &
            (results_df["start"].str[:4].astype(int) < year_start + 10)
        ]
        if len(decade_results) > 0:
            print(f"\n{year_start}s:")
            print(f"  Periods: {len(decade_results)}")
            print(f"  Avg 2x Return: {decade_results['lev_return'].mean():>7.2f}%")
            print(f"  Avg S&P 500 Return: {decade_results['sp500_return'].mean():>7.2f}%")
            print(f"  Avg Outperformance: {decade_results['outperformance'].mean():>7.2f}%")
            print(f"  Avg Sharpe: {decade_results['lev_sharpe'].mean():>7.3f}")

    # Save results
    output_file = f"{OUTPUT_DIR}/backtest_simulated_historical_results.csv"
    results_df.to_csv(output_file, index=False)
    print(f"\n✓ Detailed results saved to {output_file}")

    # Overall assessment
    print("\n" + "=" * 160)
    print("ASSESSMENT: SIMULATED 2X LEVERAGE vs S&P 500 BUY-AND-HOLD")
    print("=" * 160)

    overall_lev_return = lev_returns.mean()
    overall_sp500_return = sp500_returns.mean()
    overall_outperformance = results_df['outperformance'].mean()
    overall_win_rate = (results_df['outperformance'] > 0).sum() / len(results_df) * 100

    print(f"""
STRATEGY PERFORMANCE ACROSS 30 YEARS OF MARKET HISTORY (1995-2026):

Simulated 2x Leveraged Mean Reversion:
  • Average Return: {overall_lev_return:.2f}% per 2-year period
  • Win Rate vs S&P 500: {overall_win_rate:.1f}%
  • Avg Outperformance: {overall_outperformance:+.2f}%
  • Avg Drawdown: {drawdowns.mean():.2f}%
  • Avg Sharpe Ratio: {sharpes.mean():.3f}
  • Tested in: Bull markets, bear markets, sideways markets

S&P 500 Buy-and-Hold (Benchmark):
  • Average Return: {overall_sp500_return:.2f}% per 2-year period

Comparison:
  • Absolute Outperformance: {overall_lev_return - overall_sp500_return:+.2f}%
  • Relative Outperformance: {(overall_lev_return / overall_sp500_return - 1) * 100:+.1f}%

Assessment:
""")

    if overall_outperformance > 15:
        print(f"  ✅ EXCELLENT: Significant outperformance (+{overall_outperformance:.2f}%) with {overall_win_rate:.0f}% win rate")
        print(f"     Strategy works across different market regimes (30-year test)")
    elif overall_outperformance > 10:
        print(f"  ✅ STRONG: Consistent outperformance (+{overall_outperformance:.2f}%) with {overall_win_rate:.0f}% win rate")
    elif overall_outperformance > 5:
        print(f"  ✓ GOOD: Moderate outperformance (+{overall_outperformance:.2f}%) with {overall_win_rate:.0f}% win rate")
    elif overall_outperformance > 0:
        print(f"  ⚠️  MODEST: Slight outperformance (+{overall_outperformance:.2f}%) with {overall_win_rate:.0f}% win rate")
    else:
        print(f"  ❌ UNDERPERFORMANCE: Strategy trails S&P 500 by {abs(overall_outperformance):.2f}%")

    print("\nNote: 2x leverage simulation multiplies daily returns by 2x for all 2-year periods.")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Simulated Historical Backtest (1995-2026)"
    )
    parser.add_argument(
        "--periods",
        type=int,
        default=30,
        help="Number of random 2-year periods to test (default 30)",
    )

    args = parser.parse_args()
    run_simulated_historical_backtest(num_periods=args.periods)
