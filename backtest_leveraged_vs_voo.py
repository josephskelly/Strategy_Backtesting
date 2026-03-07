"""
Compare 2x Leveraged ETF Mean Reversion vs Buy-and-Hold VOO

Test mean reversion strategy on 2x leveraged ETFs (25% allocation)
against a simple buy-and-hold VOO strategy across random 2-year periods.
"""

import os

import pandas as pd
import numpy as np
import argparse
from datetime import datetime, timedelta
from backtest_engine import PortfolioStddevBacktester
from leveraged_etfs import fetch_leveraged_closes, LEVERAGED_ETFS
import requests
import time

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


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


def fetch_voo_data(range_: str = "5d") -> pd.DataFrame:
    """Fetch VOO closing prices."""
    rows = _yahoo_chart("VOO", range_=range_)
    df = pd.DataFrame(rows).set_index("date")
    df.index.name = "Date"
    return df[["close"]].rename(columns={"close": "VOO"})


def backtest_voo_buyandhold(prices: pd.Series, initial_capital: float = 10000) -> dict:
    """Simple buy-and-hold VOO strategy."""
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
    """Run both strategies for a single period."""
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

        # Fetch VOO data
        voo_data = fetch_voo_data(range_=range_str)
        voo_data = voo_data[(voo_data.index >= start) & (voo_data.index <= end)]

        if len(leveraged_closes) < 21 or len(voo_data) < 2:
            return None

        # Run leveraged ETF backtest
        backtester = PortfolioStddevBacktester(
            prices_df=leveraged_closes,
            initial_capital=10000,
            lookback_period=20,
            z_threshold=1.0,
            max_sector_allocation=0.25,  # 25% allocation
        )
        lev_results = backtester.run()

        # Run VOO buy-and-hold
        voo_results = backtest_voo_buyandhold(voo_data["VOO"])

        return {
            "period": date_range,
            "lev_return": lev_results.total_return,
            "lev_value": lev_results.final_value,
            "lev_drawdown": lev_results.max_drawdown,
            "lev_sharpe": lev_results.sharpe_ratio,
            "lev_trades": lev_results.num_trades,
            "voo_return": voo_results["return_pct"],
            "voo_value": voo_results["final_value"],
            "voo_pnl": voo_results["pnl"],
        }
    except Exception as e:
        print(f"  Error in period {date_range}: {str(e)[:50]}")
        return None


def run_random_periods(num_periods: int = 10):
    """Test multiple random 2-year periods."""
    print("=" * 130)
    print("2x LEVERAGED ETF MEAN REVERSION vs BUY-AND-HOLD VOO (25% Allocation)")
    print("=" * 130)
    print(f"\nTesting {num_periods} random 2-year periods...\n")

    results = []

    # Generate random 2-year periods
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*5)  # Last 5 years to sample from

    for i in range(num_periods):
        # Random end date within the last 5 years
        random_end = start_date + timedelta(days=np.random.randint(730, 1825))
        random_start = random_end - timedelta(days=730)  # 2 years before

        print(f"Period {i+1}/{num_periods}: {random_start.strftime('%Y-%m-%d')} to {random_end.strftime('%Y-%m-%d')}")

        result = run_single_period(
            random_start.strftime("%Y-%m-%d"),
            random_end.strftime("%Y-%m-%d")
        )

        if result:
            results.append(result)
            print(f"  Leveraged ETF: {result['lev_return']:>7.2f}% | VOO B&H: {result['voo_return']:>7.2f}%")

        time.sleep(0.5)  # Be nice to the API

    if not results:
        print("No valid results obtained.")
        return

    # Create results dataframe
    results_df = pd.DataFrame(results)

    print("\n" + "=" * 130)
    print("DETAILED RESULTS")
    print("=" * 130)

    display_cols = ["period", "lev_return", "voo_return", "lev_drawdown", "lev_sharpe", "lev_trades"]
    display_df = results_df[display_cols].copy()
    display_df.columns = ["Period", "Leveraged %", "VOO %", "Max DD %", "Sharpe", "Trades"]
    print(display_df.to_string(index=False))

    # Summary statistics
    print("\n" + "=" * 130)
    print("SUMMARY STATISTICS")
    print("=" * 130)

    lev_returns = results_df["lev_return"]
    voo_returns = results_df["voo_return"]

    print(f"\n{'LEVERAGED ETF (25% allocation)':40} | {'VOO BUY-AND-HOLD':40}")
    print("-" * 130)
    print(f"Mean Return:        {lev_returns.mean():>7.2f}%                  | Mean Return:        {voo_returns.mean():>7.2f}%")
    print(f"Median Return:      {lev_returns.median():>7.2f}%                  | Median Return:      {voo_returns.median():>7.2f}%")
    print(f"Std Dev:            {lev_returns.std():>7.2f}%                  | Std Dev:            {voo_returns.std():>7.2f}%")
    print(f"Min Return:         {lev_returns.min():>7.2f}%                  | Min Return:         {voo_returns.min():>7.2f}%")
    print(f"Max Return:         {lev_returns.max():>7.2f}%                  | Max Return:         {voo_returns.max():>7.2f}%")

    # Head-to-head comparison
    print("\n" + "=" * 130)
    print("HEAD-TO-HEAD COMPARISON")
    print("=" * 130)

    lev_wins = (results_df["lev_return"] > results_df["voo_return"]).sum()
    voo_wins = (results_df["voo_return"] > results_df["lev_return"]).sum()
    ties = (results_df["lev_return"] == results_df["voo_return"]).sum()

    print(f"\nLeveraged ETF Wins: {lev_wins}/{len(results)} periods ({lev_wins/len(results)*100:.1f}%)")
    print(f"VOO B&H Wins:       {voo_wins}/{len(results)} periods ({voo_wins/len(results)*100:.1f}%)")
    print(f"Ties:               {ties}/{len(results)} periods ({ties/len(results)*100:.1f}%)")

    avg_outperformance = (results_df["lev_return"] - results_df["voo_return"]).mean()
    print(f"\nAverage Outperformance: Leveraged ETF {avg_outperformance:+.2f}% vs VOO")

    # Risk metrics
    print("\n" + "=" * 130)
    print("RISK METRICS")
    print("=" * 130)

    print(f"\nAvg Max Drawdown (Leveraged ETF):    {results_df['lev_drawdown'].mean():.2f}%")
    print(f"Avg Sharpe Ratio (Leveraged ETF):   {results_df['lev_sharpe'].mean():.2f}")
    print(f"Avg Trades per Period:              {results_df['lev_trades'].mean():.0f}")

    # Save detailed results
    output_file = f"{OUTPUT_DIR}/backtest_leveraged_vs_voo_results.csv"
    results_df.to_csv(output_file, index=False)
    print(f"\n✓ Detailed results saved to {output_file}")

    # Recommendation
    print("\n" + "=" * 130)
    print("RECOMMENDATION")
    print("=" * 130)

    if avg_outperformance > 5:
        print(f"""
✓ STRONG OUTPERFORMANCE: Leveraged ETF strategy beats VOO by {avg_outperformance:.2f}% on average
  → Strategy successfully captures mean reversion opportunities
  → Suitable for active traders willing to manage positions daily
  → Monitor drawdown levels and consider 20% allocation for more conservative approach
        """)
    elif avg_outperformance > 0:
        print(f"""
✓ MODEST OUTPERFORMANCE: Leveraged ETF strategy beats VOO by {avg_outperformance:.2f}% on average
  → Strategy is competitive but depends on market conditions
  → VOO offers simpler passive alternative with lower trading friction
  → Consider hybrid approach or test other lookback/threshold parameters
        """)
    else:
        print(f"""
✗ UNDERPERFORMANCE: VOO strategy beats Leveraged ETF by {abs(avg_outperformance):.2f}% on average
  → Mean reversion not working well in current market conditions
  → Consider testing longer lookback periods or tighter z-score thresholds
  → VOO buy-and-hold is more reliable in trending markets
        """)

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare Leveraged ETF Strategy vs VOO Buy-and-Hold"
    )
    parser.add_argument(
        "--periods",
        type=int,
        default=10,
        help="Number of random 2-year periods to test (default 10)",
    )

    args = parser.parse_args()
    run_random_periods(num_periods=args.periods)
