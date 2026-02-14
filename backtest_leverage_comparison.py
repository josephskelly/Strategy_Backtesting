"""
Leverage Level Comparison: Daily Rebalancing with 1x vs 2x ETFs

Compares daily rebalancing performance across:
- 1x: Regular Vanguard sector ETFs
- 2x: Leveraged 2x sector ETFs
- Both vs Buy-and-hold S&P 500
"""

import pandas as pd
import numpy as np
import argparse
from datetime import datetime, timedelta
from backtest_daily_rebalance import DailyRebalanceBacktester
import time
import requests


# 11 Regular Vanguard sector ETFs (1x)
SECTOR_ETFS_1X = {
    "VGT": "Information Technology",
    "VHT": "Health Care",
    "VFH": "Financials",
    "VCR": "Consumer Discretionary",
    "VDC": "Consumer Staples",
    "VDE": "Energy",
    "VIS": "Industrials",
    "VOX": "Communication Services",
    "VNQ": "Real Estate",
    "VAW": "Materials",
    "VPU": "Utilities",
}

# 11 Leveraged 2x sector ETFs
SECTOR_ETFS_2X = {
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


def fetch_sector_closes(ticker_dict: dict, range_: str = "30y") -> pd.DataFrame:
    """Fetch closing prices for all sector ETFs."""
    closes = pd.DataFrame()

    for ticker in ticker_dict:
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


def compute_metrics(daily_results, initial_capital):
    """Compute additional performance metrics."""
    snapshots = daily_results.snapshots
    if not snapshots:
        return {
            "sharpe_ratio": 0,
            "max_drawdown": 0,
            "calmar_ratio": 0,
            "win_trades": 0,
            "total_trades": 0,
            "win_rate": 0,
        }

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

    # Calmar ratio
    annual_return = daily_results.total_return / (len(snapshots) / 252)
    if abs(max_drawdown) > 0:
        calmar_ratio = annual_return / abs(max_drawdown)
    else:
        calmar_ratio = 0

    # Count winning trades
    win_trades = sum(
        1 for perf in daily_results.sector_performance.values()
        if perf["num_wins"] > 0
    )
    total_trades = daily_results.num_trades
    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0

    return {
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "calmar_ratio": calmar_ratio,
        "win_trades": win_trades,
        "total_trades": total_trades,
        "win_rate": win_rate,
    }


def run_leverage_comparison(initial_capital: float = 10000, trade_amount: float = 200):
    """Compare daily rebalancing across 1x and 2x leverage levels."""
    print("=" * 200)
    print("LEVERAGE LEVEL COMPARISON: Daily Rebalancing with 1x vs 2x ETFs")
    print("=" * 200)
    print(f"\nStrategy: Buy sector drops, Sell sector gains (${trade_amount} per 1% daily move)")
    print(f"Initial Capital: ${initial_capital:,.2f}")
    print(f"Fetching sector ETF and SPY data (going back ~30 years)...\n")

    # Fetch 1x data
    print("Fetching 1x (regular) sector ETF data...")
    sector_closes_1x = fetch_sector_closes(SECTOR_ETFS_1X, range_="30y")

    # Fetch 2x data
    print("Fetching 2x (leveraged) sector ETF data...")
    sector_closes_2x = fetch_sector_closes(SECTOR_ETFS_2X, range_="30y")

    # Fetch SPY data
    print("Fetching S&P 500 (SPY) data...")
    spy_data = fetch_spy_data(range_="30y")

    if len(sector_closes_1x) < 100 or len(sector_closes_2x) < 100:
        print("Not enough historical data available.")
        return

    # Clean data
    sector_closes_1x = sector_closes_1x.dropna(axis=1, how='all').dropna()
    sector_closes_2x = sector_closes_2x.dropna(axis=1, how='all').dropna()
    spy_data = spy_data.dropna()

    # Find common date range across all datasets
    common_index = sector_closes_1x.index.intersection(sector_closes_2x.index).intersection(spy_data.index)
    if len(common_index) < 100:
        print("Not enough common data between all datasets.")
        return

    sector_closes_1x = sector_closes_1x.loc[common_index]
    sector_closes_2x = sector_closes_2x.loc[common_index]
    spy_data = spy_data.loc[common_index]

    earliest_date = common_index.min()
    latest_date = common_index.max()

    print(f"\nData range: {earliest_date.strftime('%Y-%m-%d')} to {latest_date.strftime('%Y-%m-%d')}")
    print(f"Trading days: {len(common_index)}")
    print(f"Years of data: {(latest_date - earliest_date).days / 365.25:.1f}\n")

    # Run 1x backtest
    print("=" * 200)
    print("RUNNING 1x (REGULAR) SECTOR ETF BACKTEST")
    print("=" * 200)
    backtester_1x = DailyRebalanceBacktester(
        prices_df=sector_closes_1x,
        initial_capital=initial_capital,
        trade_amount_per_percent=trade_amount,
    )
    results_1x = backtester_1x.run()
    metrics_1x = compute_metrics(results_1x, initial_capital)

    # Run 2x backtest
    print("\n" + "=" * 200)
    print("RUNNING 2x (LEVERAGED) SECTOR ETF BACKTEST")
    print("=" * 200)
    backtester_2x = DailyRebalanceBacktester(
        prices_df=sector_closes_2x,
        initial_capital=initial_capital,
        trade_amount_per_percent=trade_amount,
    )
    results_2x = backtester_2x.run()
    metrics_2x = compute_metrics(results_2x, initial_capital)

    # Run S&P 500 backtest
    results_spy = backtest_spy_buyandhold(spy_data["SPY"], initial_capital=initial_capital)

    # Display comprehensive comparison
    print("\n" + "=" * 200)
    print("PERFORMANCE COMPARISON: 1x vs 2x vs S&P 500 BUY-AND-HOLD")
    print("=" * 200)

    comparison_data = {
        "Metric": [
            "Final Value",
            "Total Return",
            "Total P&L",
            "Max Drawdown",
            "Sharpe Ratio",
            "Calmar Ratio",
            "Avg Invested %",
            "Total Trades",
            "Avg Trade Size",
        ],
        "1x ETFs": [
            f"${results_1x.final_value:,.2f}",
            f"{results_1x.total_return:.2f}%",
            f"${results_1x.final_pnl:,.2f}",
            f"{metrics_1x['max_drawdown']:.2f}%",
            f"{metrics_1x['sharpe_ratio']:.3f}",
            f"{metrics_1x['calmar_ratio']:.3f}",
            f"{results_1x.avg_invested_pct:.2f}%",
            f"{results_1x.num_trades:,}",
            f"${initial_capital * trade_amount / results_1x.num_trades:,.2f}" if results_1x.num_trades > 0 else "N/A",
        ],
        "2x ETFs": [
            f"${results_2x.final_value:,.2f}",
            f"{results_2x.total_return:.2f}%",
            f"${results_2x.final_pnl:,.2f}",
            f"{metrics_2x['max_drawdown']:.2f}%",
            f"{metrics_2x['sharpe_ratio']:.3f}",
            f"{metrics_2x['calmar_ratio']:.3f}",
            f"{results_2x.avg_invested_pct:.2f}%",
            f"{results_2x.num_trades:,}",
            f"${initial_capital * trade_amount / results_2x.num_trades:,.2f}" if results_2x.num_trades > 0 else "N/A",
        ],
        "SPY B&H": [
            f"${results_spy['final_value']:,.2f}",
            f"{results_spy['return_pct']:.2f}%",
            f"${results_spy['pnl']:,.2f}",
            "N/A",
            "N/A",
            "N/A",
            "100.00%",
            "N/A",
            "N/A",
        ],
    }

    comparison_df = pd.DataFrame(comparison_data)
    print(comparison_df.to_string(index=False))

    # Calculate leverage impact
    print("\n" + "=" * 200)
    print("LEVERAGE IMPACT ANALYSIS")
    print("=" * 200)

    leverage_gain = results_2x.total_return - results_1x.total_return
    leverage_gain_pct = (leverage_gain / results_1x.total_return) * 100 if results_1x.total_return > 0 else 0
    leverage_dollar = results_2x.final_pnl - results_1x.final_pnl
    drawdown_increase = metrics_2x['max_drawdown'] - metrics_1x['max_drawdown']

    print(f"""
Return Impact:
  • 1x Return: {results_1x.total_return:.2f}%
  • 2x Return: {results_2x.total_return:.2f}%
  • Leverage Gain: {leverage_gain:+.2f}% ({leverage_gain_pct:+.1f}% relative)
  • Dollar Gain: ${leverage_dollar:+,.2f}

Risk Impact (Max Drawdown):
  • 1x Drawdown: {metrics_1x['max_drawdown']:.2f}%
  • 2x Drawdown: {metrics_2x['max_drawdown']:.2f}%
  • Drawdown Increase: {drawdown_increase:+.2f}% (magnification: {abs(metrics_2x['max_drawdown']) / abs(metrics_1x['max_drawdown']):.2f}x)

Risk-Adjusted Returns (Sharpe Ratio):
  • 1x Sharpe: {metrics_1x['sharpe_ratio']:.3f}
  • 2x Sharpe: {metrics_2x['sharpe_ratio']:.3f}
  • Change: {metrics_2x['sharpe_ratio'] - metrics_1x['sharpe_ratio']:+.3f}

Capital Efficiency (Calmar Ratio):
  • 1x Calmar: {metrics_1x['calmar_ratio']:.3f}
  • 2x Calmar: {metrics_2x['calmar_ratio']:.3f}
  • Change: {metrics_2x['calmar_ratio'] - metrics_1x['calmar_ratio']:+.3f}
""")

    # Outperformance vs S&P 500
    print("=" * 200)
    print("OUTPERFORMANCE vs S&P 500 BUY-AND-HOLD")
    print("=" * 200)

    outperf_1x = results_1x.total_return - results_spy["return_pct"]
    outperf_2x = results_2x.total_return - results_spy["return_pct"]
    outperf_diff = outperf_2x - outperf_1x

    print(f"""
1x Daily Rebalance:
  • Return: {results_1x.total_return:.2f}%
  • vs S&P 500: {outperf_1x:+.2f}% outperformance
  • Final Value: ${results_1x.final_value:,.2f}
  • Excess P&L: ${results_1x.final_pnl - results_spy['pnl']:,.2f}

2x Daily Rebalance:
  • Return: {results_2x.total_return:.2f}%
  • vs S&P 500: {outperf_2x:+.2f}% outperformance
  • Final Value: ${results_2x.final_value:,.2f}
  • Excess P&L: ${results_2x.final_pnl - results_spy['pnl']:,.2f}

Leverage Multiplier Effect:
  • Additional Outperformance (2x vs 1x): {outperf_diff:+.2f}%
  • Additional Excess P&L: ${(results_2x.final_pnl - results_spy['pnl']) - (results_1x.final_pnl - results_spy['pnl']):,.2f}
""")

    # Sector performance comparison
    print("=" * 200)
    print("TOP 5 PERFORMING SECTORS: 1x vs 2x")
    print("=" * 200)

    sectors_1x = pd.DataFrame([
        {
            "Ticker": ticker,
            "Sector": perf.get("sector_name", ticker),
            "Return %": perf["return_pct"],
            "Trades": perf["num_trades"],
            "Win Rate": perf["win_rate"],
        }
        for ticker, perf in results_1x.sector_performance.items()
    ]).sort_values("Return %", ascending=False).head(5)

    sectors_2x = pd.DataFrame([
        {
            "Ticker": ticker,
            "Return %": perf["return_pct"],
            "Trades": perf["num_trades"],
            "Win Rate": perf["win_rate"],
        }
        for ticker, perf in results_2x.sector_performance.items()
    ]).sort_values("Return %", ascending=False).head(5)

    print("\n1x (Regular) Sector ETFs:")
    print(sectors_1x[["Ticker", "Return %", "Trades", "Win Rate"]].to_string(index=False, float_format="%.2f"))

    print("\n2x (Leveraged) Sector ETFs:")
    print(sectors_2x[["Ticker", "Return %", "Trades", "Win Rate"]].to_string(index=False, float_format="%.2f"))

    # Risk-Return Profile
    print("\n" + "=" * 200)
    print("RISK-RETURN PROFILE")
    print("=" * 200)

    print(f"""
Return per Unit of Risk (Calmar Ratio = Return / Max Drawdown):
  • 1x Calmar Ratio: {metrics_1x['calmar_ratio']:.3f}
    - Annual Return Equivalent: {metrics_1x['calmar_ratio'] * abs(metrics_1x['max_drawdown']):.2f}%
  • 2x Calmar Ratio: {metrics_2x['calmar_ratio']:.3f}
    - Annual Return Equivalent: {metrics_2x['calmar_ratio'] * abs(metrics_2x['max_drawdown']):.2f}%

Sharpe Ratio (Risk-Adjusted Returns):
  • 1x Sharpe: {metrics_1x['sharpe_ratio']:.3f}
  • 2x Sharpe: {metrics_2x['sharpe_ratio']:.3f}
  • Better metric: {"2x" if metrics_2x['sharpe_ratio'] > metrics_1x['sharpe_ratio'] else "1x"}
""")

    # Final assessment
    print("\n" + "=" * 200)
    print("ASSESSMENT: WHICH LEVERAGE LEVEL IS BETTER?")
    print("=" * 200)

    print(f"""
QUANTITATIVE COMPARISON:

Absolute Returns:
  • 1x: {results_1x.total_return:.2f}% ({results_1x.num_trades:,} trades)
  • 2x: {results_2x.total_return:.2f}% ({results_2x.num_trades:,} trades)
  • Winner: {"2x by " + f"{leverage_gain:.2f}%" if results_2x.total_return > results_1x.total_return else "1x"}

Risk Management (Max Drawdown):
  • 1x: {metrics_1x['max_drawdown']:.2f}%
  • 2x: {metrics_2x['max_drawdown']:.2f}%
  • Risk Premium: {abs(metrics_2x['max_drawdown']) / abs(metrics_1x['max_drawdown']):.2f}x amplification

Risk-Adjusted Returns (Sharpe Ratio):
  • 1x: {metrics_1x['sharpe_ratio']:.3f}
  • 2x: {metrics_2x['sharpe_ratio']:.3f}
  • Better: {"2x" if metrics_2x['sharpe_ratio'] > metrics_1x['sharpe_ratio'] else "1x"}

Capital Efficiency (Calmar Ratio):
  • 1x: {metrics_1x['calmar_ratio']:.3f}
  • 2x: {metrics_2x['calmar_ratio']:.3f}
  • Better: {"2x" if metrics_2x['calmar_ratio'] > metrics_1x['calmar_ratio'] else "1x"}

CONCLUSION:
{"✅ 2x LEVERAGE WINS: Higher absolute returns AND better risk-adjusted metrics" if (results_2x.total_return > results_1x.total_return) and (metrics_2x['sharpe_ratio'] > metrics_1x['sharpe_ratio']) else
 "⚠️  TRADE-OFF: 2x has higher returns but worse risk metrics" if results_2x.total_return > results_1x.total_return else
 "❌ 1x PREFERRED: Lower returns but better risk management"}
""")

    print("=" * 200)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Leverage Level Comparison: Daily Rebalance with 1x vs 2x ETFs"
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
    run_leverage_comparison(initial_capital=args.capital, trade_amount=args.amount)
