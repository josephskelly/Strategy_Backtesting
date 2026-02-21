"""
30-Year Historical Backtest: Daily Rebalance with 2x Leveraged ETFs vs Buy-and-Hold

Compares:
- Daily rebalancing strategy using 11 leveraged 2x sector ETFs
- Buy-and-hold S&P 500 (SPY) baseline
"""

import pandas as pd
import numpy as np
import argparse
from datetime import datetime, timedelta
from backtest_daily_rebalance import DailyRebalanceBacktester
import time
import requests


# 11 leveraged 2x sector ETFs
LEVERAGED_ETFS = {
    "UCC": "Commodities (2x)",
    "UYG": "Financials (2x)",
    "LTL": "Long-Term Treasury (2x)",
    "DIG": "Oil & Gas (2x)",
    "UGE": "Renewable Energy (2x)",
    "ROM": "Real Estate (2x)",
    "UYM": "Metals & Mining (2x)",
    "RXL": "Healthcare (2x)",
    "UXI": "Semiconductors (2x)",
    "URE": "Real Estate (2x)",
    "UPW": "Utilities (2x)",
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


def fetch_leveraged_closes(range_: str = "30y") -> pd.DataFrame:
    """Fetch closing prices for all leveraged ETFs."""
    closes = pd.DataFrame()

    for ticker in LEVERAGED_ETFS:
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


def fetch_spy_data(range_: str = "30y") -> pd.DataFrame:
    """Fetch S&P 500 (SPY) closing prices."""
    rows = _yahoo_chart("SPY", range_=range_)
    df = pd.DataFrame(rows).set_index("date")
    df.index.name = "Date"
    return df[["close"]].rename(columns={"close": "SPY"})


def backtest_spy_buyandhold(prices: pd.Series, initial_capital: float = 10000) -> dict:
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


def run_30year_backtest(initial_capital: float = 10000, trade_amount: float = 200):
    """Run 30-year continuous backtest with leveraged ETFs."""
    print("=" * 180)
    print("30-YEAR CONTINUOUS BACKTEST: DAILY REBALANCE WITH 2X LEVERAGED ETFs vs BUY-AND-HOLD S&P 500")
    print("=" * 180)
    print(f"\nStrategy: Buy leveraged sector drops, Sell leveraged sector gains (${trade_amount} per 1% daily move)")
    print(f"Leveraged ETFs: 11 sectors at 2x leverage")
    print(f"Initial Capital: ${initial_capital:,.2f}")
    print(f"Fetching leveraged ETF and SPY data (going back ~30 years)...\n")

    # Fetch data
    leveraged_closes = fetch_leveraged_closes(range_="30y")
    spy_data = fetch_spy_data(range_="30y")

    if len(leveraged_closes) < 100:
        print("Not enough historical data available for leveraged ETFs.")
        return

    # Clean data
    leveraged_closes = leveraged_closes.dropna(axis=1, how='all').dropna()
    spy_data = spy_data.dropna()

    # Find common date range
    common_index = leveraged_closes.index.intersection(spy_data.index)
    if len(common_index) < 100:
        print("Not enough common data between leveraged ETFs and SPY.")
        return

    leveraged_closes = leveraged_closes.loc[common_index]
    spy_data = spy_data.loc[common_index]

    earliest_date = leveraged_closes.index.min()
    latest_date = leveraged_closes.index.max()

    print(f"Data range: {earliest_date.strftime('%Y-%m-%d')} to {latest_date.strftime('%Y-%m-%d')}")
    print(f"Trading days available: {len(leveraged_closes)}")
    print(f"Leveraged ETFs available: {len(leveraged_closes.columns)}\n")

    # Run daily rebalance backtest on full 30-year period
    print("=" * 180)
    print("RUNNING DAILY REBALANCE BACKTEST (Full 30-Year Period)")
    print("=" * 180)

    backtester = DailyRebalanceBacktester(
        prices_df=leveraged_closes,
        initial_capital=initial_capital,
        trade_amount_per_percent=trade_amount,
    )
    daily_results = backtester.run()

    # Run S&P 500 buy-and-hold
    spy_results = backtest_spy_buyandhold(spy_data["SPY"], initial_capital=initial_capital)

    # Calculate additional metrics
    snapshots = daily_results.snapshots
    total_values = np.array([s.total_value for s in snapshots])
    daily_returns = np.diff(total_values) / initial_capital

    # Sharpe ratio
    if len(daily_returns) > 1 and np.std(daily_returns) > 0:
        sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
    else:
        sharpe_ratio = 0

    # Max drawdown
    running_max = np.maximum.accumulate(total_values)
    drawdowns = (total_values - running_max) / running_max * 100
    max_drawdown = drawdowns.min()

    # Print comprehensive results
    print("\n" + "=" * 180)
    print("RESULTS: 30-YEAR CONTINUOUS STRATEGY")
    print("=" * 180)

    print(f"\n{'Strategy':<50} | {'Final Value':>20} | {'Total Return':>15} | {'Total P&L':>15} | {'Max Drawdown':>15} | {'Sharpe Ratio':>12}")
    print("-" * 180)
    print(f"{'Daily Rebalance (2x Leveraged ETFs)':<50} | ${daily_results.final_value:>19,.2f} | {daily_results.total_return:>14.2f}% | ${daily_results.final_pnl:>14,.2f} | {max_drawdown:>14.2f}% | {sharpe_ratio:>11.3f}")
    print(f"{'Buy-and-Hold S&P 500 (SPY)':<50} | ${spy_results['final_value']:>19,.2f} | {spy_results['return_pct']:>14.2f}% | ${spy_results['pnl']:>14,.2f} | {'N/A':>14} | {'N/A':>11}")

    outperformance = daily_results.total_return - spy_results["return_pct"]
    print("\n" + "=" * 180)
    print("PERFORMANCE COMPARISON")
    print("=" * 180)

    print(f"\nAbsolute Outperformance: {outperformance:+.2f}%")
    print(f"Relative Outperformance: {(daily_results.total_return / spy_results['return_pct'] - 1) * 100:+.1f}%")
    print(f"Excess Return (in dollars): ${daily_results.final_pnl - spy_results['pnl']:+,.2f}")

    # Additional metrics
    print(f"\n{'Metric':<50} | {'Daily Rebalance':<25} | {'Buy-and-Hold SPY':<25}")
    print("-" * 180)
    print(f"{'Number of Trades':<50} | {daily_results.num_trades:>24,} | {'N/A':>24}")
    print(f"{'Avg % Invested (Capital Deployment)':<50} | {daily_results.avg_invested_pct:>23.2f}% | {'100.00%':>24}")
    print(f"{'Avg % Cash (Reserve)':<50} | {daily_results.avg_cash_pct:>23.2f}% | {'0.00%':>24}")

    # Sector-by-sector breakdown
    print("\n" + "=" * 180)
    print("SECTOR-BY-SECTOR PERFORMANCE (Daily Rebalance)")
    print("=" * 180)

    sector_df = pd.DataFrame([
        {
            "Sector": ticker,
            "Trades": perf["num_trades"],
            "P&L": perf["pnl"],
            "Return %": perf["return_pct"],
            "Wins": perf["num_wins"],
            "Win Rate": perf["win_rate"],
        }
        for ticker, perf in daily_results.sector_performance.items()
    ])

    sector_df = sector_df.sort_values("Return %", ascending=False)
    print(sector_df.to_string(index=False, float_format="%.2f"))

    # Summary assessment
    print("\n" + "=" * 180)
    print("ASSESSMENT: DAILY REBALANCE WITH 2X LEVERAGED ETFs vs BUY-AND-HOLD S&P 500")
    print("=" * 180)

    print(f"""
STRATEGY PERFORMANCE (1998-2026, ~30 years):

Daily Rebalance with 2x Leveraged Sector ETFs:
  • Final Value: ${daily_results.final_value:,.2f}
  • Total Return: {daily_results.total_return:.2f}%
  • Total P&L: ${daily_results.final_pnl:,.2f}
  • Max Drawdown: {max_drawdown:.2f}%
  • Sharpe Ratio: {sharpe_ratio:.3f}
  • Total Trades: {daily_results.num_trades:,}
  • Avg Capital Deployed: {daily_results.avg_invested_pct:.2f}%

Buy-and-Hold S&P 500 (SPY):
  • Final Value: ${spy_results['final_value']:,.2f}
  • Total Return: {spy_results['return_pct']:.2f}%
  • Total P&L: ${spy_results['pnl']:,.2f}

Comparison:
  • Absolute Outperformance: {outperformance:+.2f}%
  • Relative Outperformance: {(daily_results.total_return / spy_results['return_pct'] - 1) * 100:+.1f}%
  • Additional P&L: ${daily_results.final_pnl - spy_results['pnl']:+,.2f}

Assessment:
""")

    if outperformance > 500:
        print(f"  ✅ EXCEPTIONAL: Massive outperformance (+{outperformance:.2f}%) with leveraged daily rebalancing")
    elif outperformance > 200:
        print(f"  ✅ EXCELLENT: Exceptional outperformance (+{outperformance:.2f}%) with leveraged daily rebalancing")
    elif outperformance > 100:
        print(f"  ✅ STRONG: Significant outperformance (+{outperformance:.2f}%) with leveraged daily rebalancing")
    elif outperformance > 50:
        print(f"  ✓ GOOD: Solid outperformance (+{outperformance:.2f}%) with leveraged daily rebalancing")
    elif outperformance > 0:
        print(f"  ⚠️  MODEST: Slight outperformance (+{outperformance:.2f}%) with leveraged daily rebalancing")
    else:
        print(f"  ❌ UNDERPERFORMANCE: Daily rebalancing trails S&P 500 by {abs(outperformance):.2f}%")

    print(f"\nNote: Daily rebalance uses 11 leveraged 2x sector ETFs")
    print(f"Configuration: ${trade_amount} per 1% daily move")

    # Capital efficiency
    print("\n" + "=" * 180)
    print("CAPITAL EFFICIENCY ANALYSIS")
    print("=" * 180)

    print(f"""
Daily Rebalance Strategy:
  • Average Capital Deployed: {daily_results.avg_invested_pct:.2f}%
  • Average Cash Reserve: {daily_results.avg_cash_pct:.2f}%
  • Total Trades Executed: {daily_results.num_trades:,}
  • Average Trades per Year: {daily_results.num_trades / 30:.0f}

This means the strategy is NOT fully invested at all times.
It keeps some capital in reserve as a risk management technique.
""")

    print("\n" + "=" * 180)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="30-Year Continuous Backtest: Daily Rebalance with 2x Leveraged ETFs vs Buy-and-Hold"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000,
        help="Initial capital (default $10,000)",
    )
    parser.add_argument(
        "--amount",
        type=float,
        default=200,
        help="Trade amount per 1% daily move (default $200)",
    )

    args = parser.parse_args()
    run_30year_backtest(initial_capital=args.capital, trade_amount=args.amount)
