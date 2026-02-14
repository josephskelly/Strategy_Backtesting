"""
Annual Comparison: Daily Rebalance vs Buy-and-Hold

Test strategy for every calendar year 1998-2025
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backtest_daily_rebalance import DailyRebalanceBacktester
import time
import requests


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


def backtest_daily_rebalance(sector_data: pd.DataFrame, trade_amount: float = 300) -> dict:
    """Run daily rebalance backtest."""
    if len(sector_data) < 2:
        return None

    try:
        backtester = DailyRebalanceBacktester(
            prices_df=sector_data,
            initial_capital=10000,
            trade_amount_per_percent=trade_amount,
        )
        results = backtester.run()

        return {
            "return": results.total_return,
            "value": results.final_value,
            "drawdown": results.max_drawdown,
            "sharpe": results.sharpe_ratio,
            "trades": results.num_trades,
        }
    except Exception as e:
        print(f"  Error running daily rebalance: {e}")
        return None


def backtest_sp500(prices: pd.Series) -> dict:
    """Run buy-and-hold S&P 500."""
    if len(prices) < 2:
        return None

    try:
        shares = 10000 / prices.iloc[0]
        final_value = shares * prices.iloc[-1]
        pnl = final_value - 10000
        return_pct = (pnl / 10000) * 100

        return {
            "return": return_pct,
            "value": final_value,
        }
    except:
        return None


def run_annual_comparison(trade_amount: float = 300):
    """Test every calendar year 1998-2025."""
    print("=" * 180)
    print("ANNUAL COMPARISON: DAILY REBALANCE ($300/1%) vs S&P 500 BUY-AND-HOLD")
    print("=" * 180)
    print()

    # Fetch data
    print("Fetching data...")
    sector_closes = fetch_sector_closes(range_="30y")
    sp500_data = fetch_sp500_data(range_="30y")

    if len(sector_closes) < 100:
        print("Not enough historical data available.")
        return

    earliest_date = sector_closes.index.min()
    latest_date = sector_closes.index.max()

    print(f"Data range: {earliest_date.strftime('%Y-%m-%d')} to {latest_date.strftime('%Y-%m-%d')}\n")

    # Determine year range
    start_year = max(earliest_date.year, 1998)
    end_year = latest_date.year

    results = []

    print("=" * 180)
    print(f"{'Year':<6} | {'Daily Rebal %':>12} | {'S&P 500 %':>12} | {'Outperf':>10} | {'Drawdown':>10} | {'Sharpe':>8} | {'Trades':>7} | {'Winner':>8}")
    print("-" * 180)

    for year in range(start_year, end_year + 1):
        year_start = pd.Timestamp(f"{year}-01-01")
        year_end = pd.Timestamp(f"{year}-12-31")

        # Filter data
        mask = (sector_closes.index >= year_start) & (sector_closes.index <= year_end)
        sector_data = sector_closes[mask]

        sp500_mask = (sp500_data.index >= year_start) & (sp500_data.index <= year_end)
        sp500_filtered = sp500_data[sp500_mask]

        if len(sector_data) < 20 or len(sp500_filtered) < 2:
            continue

        # Clean data
        sector_data = sector_data.dropna(axis=1, how='all').dropna()
        if len(sector_data.columns) < 5:
            continue

        # Run backtests
        daily_result = backtest_daily_rebalance(sector_data, trade_amount=trade_amount)
        sp500_result = backtest_sp500(sp500_filtered["SPY"])

        if daily_result and sp500_result:
            outperf = daily_result["return"] - sp500_result["return"]
            winner = "Daily" if outperf > 0 else "S&P500"

            results.append({
                "year": year,
                "daily_return": daily_result["return"],
                "sp500_return": sp500_result["return"],
                "outperformance": outperf,
                "drawdown": daily_result["drawdown"],
                "sharpe": daily_result["sharpe"],
                "trades": daily_result["trades"],
            })

            print(
                f"{year:<6} | {daily_result['return']:>11.2f}% | {sp500_result['return']:>11.2f}% | {outperf:>9.2f}% | "
                f"{daily_result['drawdown']:>9.2f}% | {daily_result['sharpe']:>7.3f} | {int(daily_result['trades']):>6} | {winner:>8}"
            )

    print("=" * 180)

    if not results:
        print("No valid results obtained.")
        return

    results_df = pd.DataFrame(results)

    # Summary statistics
    print("\n" + "=" * 180)
    print("SUMMARY STATISTICS")
    print("=" * 180)

    daily_rets = results_df["daily_return"]
    sp500_rets = results_df["sp500_return"]
    outperf = results_df["outperformance"]

    print(f"\n{'Metric':<40} | {'Daily Rebalance':<30} | {'S&P 500':<30}")
    print("-" * 180)
    print(f"{'Average Annual Return':<40} | {daily_rets.mean():>10.2f}% {'':<18} | {sp500_rets.mean():>10.2f}%")
    print(f"{'Median Annual Return':<40} | {daily_rets.median():>10.2f}% {'':<18} | {sp500_rets.median():>10.2f}%")
    print(f"{'Std Dev':<40} | {daily_rets.std():>10.2f}% {'':<18} | {sp500_rets.std():>10.2f}%")
    print(f"{'Min Annual Return':<40} | {daily_rets.min():>10.2f}% {'':<18} | {sp500_rets.min():>10.2f}%")
    print(f"{'Max Annual Return':<40} | {daily_rets.max():>10.2f}% {'':<18} | {sp500_rets.max():>10.2f}%")
    print(f"{'Positive Years':<40} | {(daily_rets > 0).sum()}/{len(daily_rets)} ({(daily_rets > 0).sum()/len(daily_rets)*100:.1f}%) | {(sp500_rets > 0).sum()}/{len(sp500_rets)} ({(sp500_rets > 0).sum()/len(sp500_rets)*100:.1f}%)")
    print(f"{'Negative Years':<40} | {(daily_rets < 0).sum()}/{len(daily_rets)} ({(daily_rets < 0).sum()/len(daily_rets)*100:.1f}%) | {(sp500_rets < 0).sum()}/{len(sp500_rets)} ({(sp500_rets < 0).sum()/len(sp500_rets)*100:.1f}%)")

    print(f"\nOutperformance vs S&P 500:")
    print(f"{'Average Outperformance':<40} | {outperf.mean():>10.2f}%")
    print(f"{'Median Outperformance':<40} | {outperf.median():>10.2f}%")
    print(f"{'Win Rate (Years Better)':<40} | {(outperf > 0).sum()}/{len(outperf)} ({(outperf > 0).sum()/len(outperf)*100:.1f}%)")
    print(f"{'Worst Year Underperformance':<40} | {outperf.min():>10.2f}%")
    print(f"{'Best Year Outperformance':<40} | {outperf.max():>10.2f}%")

    # Year breakdown
    print("\n" + "=" * 180)
    print("PERFORMANCE BY YEAR")
    print("=" * 180)

    for idx, row in results_df.iterrows():
        year = int(row["year"])
        daily = row["daily_return"]
        sp500 = row["sp500_return"]
        outperf = row["outperformance"]

        if outperf > 0:
            winner = "✓ Daily"
        else:
            winner = "✗ S&P500"

        print(f"{year}: Daily {daily:>7.2f}% | S&P500 {sp500:>7.2f}% ({winner} {outperf:+.2f}%)")

    # Decade breakdown
    print("\n" + "=" * 180)
    print("PERFORMANCE BY DECADE")
    print("=" * 180)

    for decade_start in range(1990, 2030, 10):
        decade_results = results_df[
            (results_df["year"] >= decade_start) & (results_df["year"] < decade_start + 10)
        ]
        if len(decade_results) > 0:
            print(f"\n{decade_start}s:")
            print(f"  Years: {len(decade_results)}")
            print(f"  Daily Rebalance: {decade_results['daily_return'].mean():>7.2f}% avg (min {decade_results['daily_return'].min():.2f}%, max {decade_results['daily_return'].max():.2f}%)")
            print(f"  S&P 500: {decade_results['sp500_return'].mean():>7.2f}% avg (min {decade_results['sp500_return'].min():.2f}%, max {decade_results['sp500_return'].max():.2f}%)")
            print(f"  Outperformance: {decade_results['outperformance'].mean():>7.2f}% avg")
            print(f"  Win Rate: {(decade_results['outperformance'] > 0).sum()}/{len(decade_results)} years")

    # Save results
    output_file = "backtest_annual_comparison.csv"
    results_df.to_csv(output_file, index=False)
    print(f"\n✓ Detailed results saved to {output_file}")

    # Assessment
    print("\n" + "=" * 180)
    print("ASSESSMENT")
    print("=" * 180)

    outperf_series = results_df["outperformance"]
    win_pct = (outperf_series > 0).sum() / len(outperf_series) * 100
    avg_outperf = outperf_series.mean()

    print(f"""
Daily Rebalance Strategy ($300 per 1% daily move) vs S&P 500:

Performance Over {int(results_df['year'].max()) - int(results_df['year'].min()) + 1} Years ({int(results_df['year'].min())}-{int(results_df['year'].max())}):
  • Average Annual Return: {daily_rets.mean():.2f}% (S&P 500: {sp500_rets.mean():.2f}%)
  • Win Rate: {win_pct:.1f}% ({(outperf_series > 0).sum()}/{len(outperf_series)} years)
  • Average Outperformance: {avg_outperf:+.2f}%
  • Best Year: {outperf_series.max():+.2f}% ({int(results_df.loc[outperf_series.idxmax(), 'year'])})
  • Worst Year: {outperf_series.min():+.2f}% ({int(results_df.loc[outperf_series.idxmin(), 'year'])})

Consistency:
  • Positive years: {(daily_rets > 0).sum()}/{len(daily_rets)} ({(daily_rets > 0).sum()/len(daily_rets)*100:.1f}%)
  • S&P 500 positive: {(sp500_rets > 0).sum()}/{len(sp500_rets)} ({(sp500_rets > 0).sum()/len(sp500_rets)*100:.1f}%)

Assessment: """)

    if win_pct >= 60:
        print(f"✅ EXCELLENT - Wins {win_pct:.0f}% of years with {avg_outperf:+.2f}% avg outperformance")
    elif win_pct >= 50:
        print(f"✓ GOOD - Wins {win_pct:.0f}% of years with {avg_outperf:+.2f}% avg outperformance")
    else:
        print(f"⚠️  MIXED - Wins {win_pct:.0f}% of years with {avg_outperf:+.2f}% avg outperformance")

    print()


if __name__ == "__main__":
    run_annual_comparison(trade_amount=300)
