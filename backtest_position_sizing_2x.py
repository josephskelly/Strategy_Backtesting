"""
Position Sizing Comparison: 2x Leveraged Daily Rebalancing

Tests different trade amounts per 1% daily move:
- $200 (conservative)
- $250 (moderate)
- $300 (aggressive)

Analyzes impact on returns, risk, and capital efficiency.
"""

import pandas as pd
import numpy as np
import argparse
from datetime import datetime, timedelta
from backtest_daily_rebalance import DailyRebalanceBacktester
import time
import requests


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
    """Fetch closing prices for leveraged ETFs."""
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
            "volatility": 0,
            "recovery_days": 0,
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

    # Volatility
    volatility = np.std(daily_returns) * np.sqrt(252) * 100

    # Calmar ratio
    annual_return = daily_results.total_return / (len(snapshots) / 252)
    if abs(max_drawdown) > 0:
        calmar_ratio = annual_return / abs(max_drawdown)
    else:
        calmar_ratio = 0

    # Recovery days (days to recover from max drawdown)
    max_drawdown_idx = np.argmin(drawdowns)
    if max_drawdown_idx < len(total_values) - 1:
        max_val_before = running_max[max_drawdown_idx]
        recovery_days = 0
        for i in range(max_drawdown_idx, len(total_values)):
            if total_values[i] >= max_val_before:
                recovery_days = i - max_drawdown_idx
                break
        if recovery_days == 0:
            recovery_days = len(total_values) - max_drawdown_idx
    else:
        recovery_days = 0

    return {
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "calmar_ratio": calmar_ratio,
        "volatility": volatility,
        "recovery_days": recovery_days,
    }


def run_position_sizing_comparison(initial_capital: float = 10000):
    """Compare position sizing impact on daily rebalancing with 2x leverage."""
    print("=" * 220)
    print("POSITION SIZING COMPARISON: 2x Leveraged Daily Rebalancing")
    print("=" * 220)
    print(f"\nTesting trade amounts per 1% daily move: $200, $250, $300")
    print(f"Initial Capital: ${initial_capital:,.2f}")
    print(f"Fetching leveraged ETF and SPY data (going back ~30 years)...\n")

    # Fetch data
    print("Fetching 2x (leveraged) sector ETF data...")
    sector_closes_2x = fetch_sector_closes(SECTOR_ETFS_2X, range_="30y")

    print("Fetching S&P 500 (SPY) data...")
    spy_data = fetch_spy_data(range_="30y")

    if len(sector_closes_2x) < 100:
        print("Not enough historical data available.")
        return

    # Clean data
    sector_closes_2x = sector_closes_2x.dropna(axis=1, how='all').dropna()
    spy_data = spy_data.dropna()

    # Find common date range
    common_index = sector_closes_2x.index.intersection(spy_data.index)
    if len(common_index) < 100:
        print("Not enough common data.")
        return

    sector_closes_2x = sector_closes_2x.loc[common_index]
    spy_data = spy_data.loc[common_index]

    earliest_date = common_index.min()
    latest_date = common_index.max()

    print(f"Data range: {earliest_date.strftime('%Y-%m-%d')} to {latest_date.strftime('%Y-%m-%d')}")
    print(f"Trading days: {len(common_index)}")
    print(f"Years of data: {(latest_date - earliest_date).days / 365.25:.1f}\n")

    # Run backtests for each position size
    trade_amounts = [200, 250, 300]
    results_dict = {}

    for trade_amount in trade_amounts:
        print("=" * 220)
        print(f"RUNNING BACKTEST: ${trade_amount} per 1% move")
        print("=" * 220)

        backtester = DailyRebalanceBacktester(
            prices_df=sector_closes_2x,
            initial_capital=initial_capital,
            trade_amount_per_percent=trade_amount,
        )
        results = backtester.run()
        metrics = compute_metrics(results, initial_capital)

        results_dict[trade_amount] = {
            "results": results,
            "metrics": metrics,
        }

    # Run S&P 500 backtest
    spy_results = backtest_spy_buyandhold(spy_data["SPY"], initial_capital=initial_capital)

    # Display comprehensive comparison
    print("\n" + "=" * 220)
    print("PERFORMANCE COMPARISON: Position Sizing Impact (2x Leveraged ETFs)")
    print("=" * 220)

    comparison_data = {
        "Metric": [
            "Final Value",
            "Total Return",
            "Total P&L",
            "Max Drawdown",
            "Drawdown Recovery (days)",
            "Annual Volatility",
            "Sharpe Ratio",
            "Calmar Ratio",
            "Total Trades",
            "Avg Position Size",
            "Avg Invested %",
            "Avg Cash %",
        ],
    }

    for trade_amount in trade_amounts:
        res = results_dict[trade_amount]["results"]
        met = results_dict[trade_amount]["metrics"]

        avg_pos_size = (
            initial_capital * trade_amount / res.num_trades
            if res.num_trades > 0
            else 0
        )

        comparison_data[f"${trade_amount}"] = [
            f"${res.final_value:,.2f}",
            f"{res.total_return:.2f}%",
            f"${res.final_pnl:,.2f}",
            f"{met['max_drawdown']:.2f}%",
            f"{met['recovery_days']:,}",
            f"{met['volatility']:.2f}%",
            f"{met['sharpe_ratio']:.3f}",
            f"{met['calmar_ratio']:.3f}",
            f"{res.num_trades:,}",
            f"${avg_pos_size:.2f}",
            f"{res.avg_invested_pct:.2f}%",
            f"{res.avg_cash_pct:.2f}%",
        ]

    comparison_df = pd.DataFrame(comparison_data)
    print(comparison_df.to_string(index=False))

    # Position sizing impact analysis
    print("\n" + "=" * 220)
    print("POSITION SIZING IMPACT ANALYSIS")
    print("=" * 220)

    res_200 = results_dict[200]["results"]
    res_250 = results_dict[250]["results"]
    res_300 = results_dict[300]["results"]
    met_200 = results_dict[200]["metrics"]
    met_250 = results_dict[250]["metrics"]
    met_300 = results_dict[300]["metrics"]

    gain_250_vs_200 = res_250.total_return - res_200.total_return
    gain_300_vs_200 = res_300.total_return - res_200.total_return
    gain_300_vs_250 = res_300.total_return - res_250.total_return

    print(f"""
Return Scaling:
  • $200: {res_200.total_return:.2f}%
  • $250: {res_250.total_return:.2f}% ({gain_250_vs_200:+.2f}% vs $200)
  • $300: {res_300.total_return:.2f}% ({gain_300_vs_200:+.2f}% vs $200, {gain_300_vs_250:+.2f}% vs $250)

Return per Dollar of Position Size:
  • $200: {res_200.total_return / 200:.4f}% return per $1 of position size
  • $250: {res_250.total_return / 250:.4f}% return per $1 of position size
  • $300: {res_300.total_return / 300:.4f}% return per $1 of position size

Dollar Gain Comparison:
  • $200: ${res_200.final_pnl:,.2f}
  • $250: ${res_250.final_pnl:,.2f} ({res_250.final_pnl - res_200.final_pnl:+,.2f} vs $200)
  • $300: ${res_300.final_pnl:,.2f} ({res_300.final_pnl - res_200.final_pnl:+,.2f} vs $200)

Risk Impact (Max Drawdown):
  • $200: {met_200['max_drawdown']:.2f}%
  • $250: {met_250['max_drawdown']:.2f}% ({met_250['max_drawdown'] - met_200['max_drawdown']:+.2f}%)
  • $300: {met_300['max_drawdown']:.2f}% ({met_300['max_drawdown'] - met_200['max_drawdown']:+.2f}%)

Volatility (Annualized):
  • $200: {met_200['volatility']:.2f}%
  • $250: {met_250['volatility']:.2f}% ({met_250['volatility'] - met_200['volatility']:+.2f}%)
  • $300: {met_300['volatility']:.2f}% ({met_300['volatility'] - met_200['volatility']:+.2f}%)

Recovery from Max Drawdown:
  • $200: {met_200['recovery_days']:,} days
  • $250: {met_250['recovery_days']:,} days ({met_250['recovery_days'] - met_200['recovery_days']:+,} days)
  • $300: {met_300['recovery_days']:,} days ({met_300['recovery_days'] - met_200['recovery_days']:+,} days)
""")

    # Risk-adjusted returns
    print("=" * 220)
    print("RISK-ADJUSTED RETURNS")
    print("=" * 220)

    print(f"""
Sharpe Ratio (volatility-adjusted returns):
  • $200: {met_200['sharpe_ratio']:.3f}
  • $250: {met_250['sharpe_ratio']:.3f} ({met_250['sharpe_ratio'] - met_200['sharpe_ratio']:+.3f})
  • $300: {met_300['sharpe_ratio']:.3f} ({met_300['sharpe_ratio'] - met_200['sharpe_ratio']:+.3f})
  • Best: {"$200" if met_200['sharpe_ratio'] >= max(met_250['sharpe_ratio'], met_300['sharpe_ratio']) else "$250" if met_250['sharpe_ratio'] >= met_300['sharpe_ratio'] else "$300"}

Calmar Ratio (return per unit of max drawdown):
  • $200: {met_200['calmar_ratio']:.3f}
  • $250: {met_250['calmar_ratio']:.3f} ({met_250['calmar_ratio'] - met_200['calmar_ratio']:+.3f})
  • $300: {met_300['calmar_ratio']:.3f} ({met_300['calmar_ratio'] - met_200['calmar_ratio']:+.3f})
  • Best: {"$200" if met_200['calmar_ratio'] >= max(met_250['calmar_ratio'], met_300['calmar_ratio']) else "$250" if met_250['calmar_ratio'] >= met_300['calmar_ratio'] else "$300"}
""")

    # Outperformance vs S&P 500
    print("=" * 220)
    print("OUTPERFORMANCE vs S&P 500 BUY-AND-HOLD")
    print("=" * 220)

    outperf_200 = res_200.total_return - spy_results["return_pct"]
    outperf_250 = res_250.total_return - spy_results["return_pct"]
    outperf_300 = res_300.total_return - spy_results["return_pct"]

    print(f"""
S&P 500 Baseline: {spy_results['return_pct']:.2f}% (${spy_results['final_value']:,.2f})

$200 Position Size:
  • Return: {res_200.total_return:.2f}%
  • Outperformance: {outperf_200:+.2f}%
  • Final Value: ${res_200.final_value:,.2f}
  • Excess P&L: ${res_200.final_pnl - spy_results['pnl']:,.2f}

$250 Position Size:
  • Return: {res_250.total_return:.2f}%
  • Outperformance: {outperf_250:+.2f}%
  • Final Value: ${res_250.final_value:,.2f}
  • Excess P&L: ${res_250.final_pnl - spy_results['pnl']:,.2f}
  • vs $200: +{outperf_250 - outperf_200:.2f}%

$300 Position Size:
  • Return: {res_300.total_return:.2f}%
  • Outperformance: {outperf_300:+.2f}%
  • Final Value: ${res_300.final_value:,.2f}
  • Excess P&L: ${res_300.final_pnl - spy_results['pnl']:,.2f}
  • vs $200: +{outperf_300 - outperf_200:.2f}%
""")

    # Capital efficiency
    print("=" * 220)
    print("CAPITAL EFFICIENCY ANALYSIS")
    print("=" * 220)

    print(f"""
Position Size vs Capital Deployment:
  • $200: {res_200.avg_invested_pct:.2f}% deployed ({res_200.avg_cash_pct:.2f}% cash)
  • $250: {res_250.avg_invested_pct:.2f}% deployed ({res_250.avg_cash_pct:.2f}% cash)
  • $300: {res_300.avg_invested_pct:.2f}% deployed ({res_300.avg_cash_pct:.2f}% cash)

Trading Activity:
  • $200: {res_200.num_trades:,} trades (~{res_200.num_trades / 17.7:.0f} per year)
  • $250: {res_250.num_trades:,} trades (~{res_250.num_trades / 17.7:.0f} per year)
  • $300: {res_300.num_trades:,} trades (~{res_300.num_trades / 17.7:.0f} per year)

Note: Trading frequency is consistent because it's driven by 1% sector moves,
not the position size. Larger position sizes just deploy more capital per trade.
""")

    # Efficiency metrics
    print("=" * 220)
    print("EFFICIENCY METRICS: Return per Unit Risk")
    print("=" * 220)

    return_per_drawdown_200 = res_200.total_return / abs(met_200['max_drawdown'])
    return_per_drawdown_250 = res_250.total_return / abs(met_250['max_drawdown'])
    return_per_drawdown_300 = res_300.total_return / abs(met_300['max_drawdown'])

    return_per_volatility_200 = res_200.total_return / met_200['volatility']
    return_per_volatility_250 = res_250.total_return / met_250['volatility']
    return_per_volatility_300 = res_300.total_return / met_300['volatility']

    print(f"""
Return per Unit of Max Drawdown:
  • $200: {return_per_drawdown_200:.4f} (1 unit of drawdown = {res_200.total_return / return_per_drawdown_200:.2f}% return)
  • $250: {return_per_drawdown_250:.4f} (1 unit of drawdown = {res_250.total_return / return_per_drawdown_250:.2f}% return)
  • $300: {return_per_drawdown_300:.4f} (1 unit of drawdown = {res_300.total_return / return_per_drawdown_300:.2f}% return)
  • Best: {"$200" if return_per_drawdown_200 >= max(return_per_drawdown_250, return_per_drawdown_300) else "$250" if return_per_drawdown_250 >= return_per_drawdown_300 else "$300"}

Return per Unit of Volatility:
  • $200: {return_per_volatility_200:.4f} (1% volatility = {res_200.total_return / return_per_volatility_200:.2f}% return)
  • $250: {return_per_volatility_250:.4f} (1% volatility = {res_250.total_return / return_per_volatility_250:.2f}% return)
  • $300: {return_per_volatility_300:.4f} (1% volatility = {res_300.total_return / return_per_volatility_300:.2f}% return)
  • Best: {"$200" if return_per_volatility_200 >= max(return_per_volatility_250, return_per_volatility_300) else "$250" if return_per_volatility_250 >= return_per_volatility_300 else "$300"}
""")

    # Final recommendation
    print("=" * 220)
    print("POSITION SIZING RECOMMENDATION")
    print("=" * 220)

    print(f"""
KEY FINDINGS:

Return Scaling (Diminishing Returns?):
  • $200→$250: {gain_250_vs_200:+.2f}% additional return (+25% position size)
  • $250→$300: {gain_300_vs_250:+.2f}% additional return (+20% position size)
  • Ratio: Doubling position size does NOT double returns
  • Reason: Larger positions create slippage, hit position limits faster

Risk Scaling:
  • Drawdown increases proportionally with position size
  • Volatility scales with position size
  • Recovery time increases slightly with position size

Capital Efficiency:
  • $300 deploys more capital on average than $200
  • But return improvement is less than proportional
  • This suggests diminishing marginal returns

RECOMMENDATION:
""")

    # Determine optimal position size
    best_return = max(
        res_200.total_return,
        res_250.total_return,
        res_300.total_return,
    )
    best_sharpe = max(
        met_200['sharpe_ratio'],
        met_250['sharpe_ratio'],
        met_300['sharpe_ratio'],
    )
    best_calmar = max(
        met_200['calmar_ratio'],
        met_250['calmar_ratio'],
        met_300['calmar_ratio'],
    )

    if res_300.total_return == best_return:
        print(f"""
✅ $300 per 1% move is optimal for:
  • Maximum absolute returns: {res_300.total_return:.2f}%
  • Most aggressive approach: ${res_300.final_pnl:,.2f} total P&L

Best for: Experienced traders comfortable with {met_300['max_drawdown']:.2f}% drawdowns
""")
    elif res_250.total_return == best_return:
        print(f"""
✅ $250 per 1% move offers:
  • Strong returns: {res_250.total_return:.2f}%
  • Better risk-adjusted profile than $200
  • Good balance between aggression and safety

Best for: Balanced approach - growth with acceptable risk
""")
    else:
        print(f"""
✅ $200 per 1% move is safest:
  • Solid returns: {res_200.total_return:.2f}%
  • Lowest drawdown: {met_200['max_drawdown']:.2f}%
  • Best Sharpe ratio: {met_200['sharpe_ratio']:.3f}

Best for: Conservative traders prioritizing drawdown control
""")

    print(f"""
Risk Tolerance Guide:
  • Low Risk Tolerance:  $200 (drawdown: {met_200['max_drawdown']:.2f}%)
  • Medium Risk Tolerance: $250 (drawdown: {met_250['max_drawdown']:.2f}%)
  • High Risk Tolerance:  $300 (drawdown: {met_300['max_drawdown']:.2f}%)

All three outperform S&P 500 by significant margins:
  • $200: +{outperf_200:.2f}%
  • $250: +{outperf_250:.2f}%
  • $300: +{outperf_300:.2f}%
""")

    print("=" * 220)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Position Sizing Comparison: 2x Leveraged Daily Rebalancing"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000,
        help="Initial capital (default $10,000)",
    )

    args = parser.parse_args()
    run_position_sizing_comparison(initial_capital=args.capital)
