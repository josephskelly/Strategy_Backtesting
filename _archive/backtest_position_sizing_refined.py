"""
Refined Position Sizing Analysis: 2x Leveraged Daily Rebalancing

Tests trade amounts per 1% daily move:
- $125 (conservative-moderate)
- $150 (moderate)
- $175 (moderate-aggressive)

Identifies the exact sweet spot within the optimal range.
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


def run_refined_position_sizing(initial_capital: float = 10000):
    """Compare position sizing within the optimal range."""
    print("=" * 260)
    print("REFINED POSITION SIZING ANALYSIS: Finding the Exact Sweet Spot")
    print("=" * 260)
    print(f"\nTesting trade amounts per 1% daily move: $125, $150, $175")
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
    trade_amounts = [125, 150, 175]
    results_dict = {}

    for trade_amount in trade_amounts:
        print("=" * 260)
        print(f"RUNNING BACKTEST: ${trade_amount} per 1% move")
        print("=" * 260)

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

    # Extract results
    res_125 = results_dict[125]["results"]
    res_150 = results_dict[150]["results"]
    res_175 = results_dict[175]["results"]
    met_125 = results_dict[125]["metrics"]
    met_150 = results_dict[150]["metrics"]
    met_175 = results_dict[175]["metrics"]

    # Display comprehensive comparison
    print("\n" + "=" * 260)
    print("PERFORMANCE COMPARISON: Refined Position Sizing ($125, $150, $175)")
    print("=" * 260)

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

    # Detailed analysis
    print("\n" + "=" * 260)
    print("DETAILED PERFORMANCE ANALYSIS")
    print("=" * 260)

    print(f"""
ABSOLUTE RETURNS:
  • $125: {res_125.total_return:.2f}%
  • $150: {res_150.total_return:.2f}%
  • $175: {res_175.total_return:.2f}%

RANK: {("1. $150" if res_150.total_return >= max(res_125.total_return, res_175.total_return) else "1. $125" if res_125.total_return >= res_175.total_return else "1. $175")}

INCREMENTAL GAINS:
  • $125→$150: {res_150.total_return - res_125.total_return:+.2f}% ({(res_150.total_return / res_125.total_return - 1) * 100:+.1f}%)
  • $150→$175: {res_175.total_return - res_150.total_return:+.2f}% ({(res_175.total_return / res_150.total_return - 1) * 100:+.1f}%)

EFFICIENCY: Return per Dollar of Position Size
  • $125: {res_125.total_return / 125:.4f}% per $1 {'✅ BEST' if res_125.total_return / 125 >= max(res_150.total_return / 150, res_175.total_return / 175) else ''}
  • $150: {res_150.total_return / 150:.4f}% per $1 {'✅ BEST' if res_150.total_return / 150 >= max(res_125.total_return / 125, res_175.total_return / 175) else ''}
  • $175: {res_175.total_return / 175:.4f}% per $1 {'✅ BEST' if res_175.total_return / 175 >= max(res_125.total_return / 125, res_150.total_return / 150) else ''}

DOLLAR GAINS:
  • $125: ${res_125.final_pnl:,.2f}
  • $150: ${res_150.final_pnl:,.2f} ({res_150.final_pnl - res_125.final_pnl:+,.2f})
  • $175: ${res_175.final_pnl:,.2f} ({res_175.final_pnl - res_125.final_pnl:+,.2f})
""")

    # Risk metrics
    print("=" * 260)
    print("RISK METRICS")
    print("=" * 260)

    print(f"""
SHARPE RATIO (volatility-adjusted returns):
  • $125: {met_125['sharpe_ratio']:.3f} {'✅ BEST' if met_125['sharpe_ratio'] >= max(met_150['sharpe_ratio'], met_175['sharpe_ratio']) else ''}
  • $150: {met_150['sharpe_ratio']:.3f} {'✅ BEST' if met_150['sharpe_ratio'] >= max(met_125['sharpe_ratio'], met_175['sharpe_ratio']) else ''}
  • $175: {met_175['sharpe_ratio']:.3f} {'✅ BEST' if met_175['sharpe_ratio'] >= max(met_125['sharpe_ratio'], met_150['sharpe_ratio']) else ''}

CALMAR RATIO (return per unit of max drawdown):
  • $125: {met_125['calmar_ratio']:.3f} {'✅ BEST' if met_125['calmar_ratio'] >= max(met_150['calmar_ratio'], met_175['calmar_ratio']) else ''}
  • $150: {met_150['calmar_ratio']:.3f} {'✅ BEST' if met_150['calmar_ratio'] >= max(met_125['calmar_ratio'], met_175['calmar_ratio']) else ''}
  • $175: {met_175['calmar_ratio']:.3f} {'✅ BEST' if met_175['calmar_ratio'] >= max(met_125['calmar_ratio'], met_150['calmar_ratio']) else ''}

MAX DRAWDOWN (portfolio peak-to-trough):
  • $125: {met_125['max_drawdown']:.2f}%
  • $150: {met_150['max_drawdown']:.2f}%
  • $175: {met_175['max_drawdown']:.2f}%

VOLATILITY (annualized):
  • $125: {met_125['volatility']:.2f}%
  • $150: {met_150['volatility']:.2f}%
  • $175: {met_175['volatility']:.2f}%

RECOVERY TIME FROM MAX DRAWDOWN:
  • $125: {met_125['recovery_days']:,} days
  • $150: {met_150['recovery_days']:,} days ({met_150['recovery_days'] - met_125['recovery_days']:+,})
  • $175: {met_175['recovery_days']:,} days ({met_175['recovery_days'] - met_125['recovery_days']:+,})
""")

    # Outperformance
    print("=" * 260)
    print("OUTPERFORMANCE vs S&P 500 BUY-AND-HOLD")
    print("=" * 260)

    outperf_125 = res_125.total_return - spy_results["return_pct"]
    outperf_150 = res_150.total_return - spy_results["return_pct"]
    outperf_175 = res_175.total_return - spy_results["return_pct"]

    print(f"""
S&P 500 Baseline: {spy_results['return_pct']:.2f}% (${spy_results['final_value']:,.2f})

$125 Position Size:
  • Return: {res_125.total_return:.2f}%
  • Outperformance: {outperf_125:+.2f}%
  • Final Value: ${res_125.final_value:,.2f}
  • Excess P&L: ${res_125.final_pnl - spy_results['pnl']:,.2f}

$150 Position Size:
  • Return: {res_150.total_return:.2f}%
  • Outperformance: {outperf_150:+.2f}%
  • Final Value: ${res_150.final_value:,.2f}
  • Excess P&L: ${res_150.final_pnl - spy_results['pnl']:,.2f}

$175 Position Size:
  • Return: {res_175.total_return:.2f}%
  • Outperformance: {outperf_175:+.2f}%
  • Final Value: ${res_175.final_value:,.2f}
  • Excess P&L: ${res_175.final_pnl - spy_results['pnl']:,.2f}
""")

    # Capital efficiency
    print("=" * 260)
    print("CAPITAL EFFICIENCY")
    print("=" * 260)

    print(f"""
AVERAGE CAPITAL DEPLOYMENT:
  • $125: {res_125.avg_invested_pct:.2f}% deployed ({res_125.avg_cash_pct:.2f}% cash)
  • $150: {res_150.avg_invested_pct:.2f}% deployed ({res_150.avg_cash_pct:.2f}% cash)
  • $175: {res_175.avg_invested_pct:.2f}% deployed ({res_175.avg_cash_pct:.2f}% cash)

TRADING ACTIVITY:
  • $125: {res_125.num_trades:,} trades (~{res_125.num_trades / 17.7:.0f} per year)
  • $150: {res_150.num_trades:,} trades (~{res_150.num_trades / 17.7:.0f} per year)
  • $175: {res_175.num_trades:,} trades (~{res_175.num_trades / 17.7:.0f} per year)

CAPITAL UTILIZATION PATTERN:
  Lower position size = Higher cash reserves = More flexibility
  Higher position size = Lower cash reserves = Risk of missing trades
""")

    # Efficiency metrics
    print("=" * 260)
    print("EFFICIENCY RANKINGS")
    print("=" * 260)

    eff_125_dd = res_125.total_return / abs(met_125['max_drawdown'])
    eff_150_dd = res_150.total_return / abs(met_150['max_drawdown'])
    eff_175_dd = res_175.total_return / abs(met_175['max_drawdown'])

    eff_125_vol = res_125.total_return / met_125['volatility']
    eff_150_vol = res_150.total_return / met_150['volatility']
    eff_175_vol = res_175.total_return / met_175['volatility']

    print(f"""
Return per % of Max Drawdown:
  • $125: {eff_125_dd:.3f} {'✅' if eff_125_dd >= max(eff_150_dd, eff_175_dd) else ''}
  • $150: {eff_150_dd:.3f} {'✅' if eff_150_dd >= max(eff_125_dd, eff_175_dd) else ''}
  • $175: {eff_175_dd:.3f} {'✅' if eff_175_dd >= max(eff_125_dd, eff_150_dd) else ''}

Return per % of Volatility:
  • $125: {eff_125_vol:.3f} {'✅' if eff_125_vol >= max(eff_150_vol, eff_175_vol) else ''}
  • $150: {eff_150_vol:.3f} {'✅' if eff_150_vol >= max(eff_125_vol, eff_175_vol) else ''}
  • $175: {eff_175_vol:.3f} {'✅' if eff_175_vol >= max(eff_125_vol, eff_150_vol) else ''}

Return per $ of Position Size:
  • $125: {res_125.total_return / 125:.4f} {'✅' if res_125.total_return / 125 >= max(res_150.total_return / 150, res_175.total_return / 175) else ''}
  • $150: {res_150.total_return / 150:.4f} {'✅' if res_150.total_return / 150 >= max(res_125.total_return / 125, res_175.total_return / 175) else ''}
  • $175: {res_175.total_return / 175:.4f} {'✅' if res_175.total_return / 175 >= max(res_125.total_return / 125, res_150.total_return / 150) else ''}
""")

    # Final recommendation
    print("=" * 260)
    print("RECOMMENDATION: OPTIMAL POSITION SIZING")
    print("=" * 260)

    # Determine best based on multiple criteria
    best_return = max(res_125.total_return, res_150.total_return, res_175.total_return)
    best_return_amount = 125 if res_125.total_return == best_return else (150 if res_150.total_return == best_return else 175)

    best_sharpe = max(met_125['sharpe_ratio'], met_150['sharpe_ratio'], met_175['sharpe_ratio'])
    best_sharpe_amount = 125 if met_125['sharpe_ratio'] == best_sharpe else (150 if met_150['sharpe_ratio'] == best_sharpe else 175)

    best_calmar = max(met_125['calmar_ratio'], met_150['calmar_ratio'], met_175['calmar_ratio'])
    best_calmar_amount = 125 if met_125['calmar_ratio'] == best_calmar else (150 if met_150['calmar_ratio'] == best_calmar else 175)

    # Calculate which is "best overall"
    if best_return_amount == best_sharpe_amount == best_calmar_amount:
        overall_best = best_return_amount
    else:
        # Majority vote with weighting
        votes = {}
        for amount in [125, 150, 175]:
            votes[amount] = 0
            if amount == best_return_amount:
                votes[amount] += 1
            if amount == best_sharpe_amount:
                votes[amount] += 1
            if amount == best_calmar_amount:
                votes[amount] += 1
        overall_best = max(votes.keys(), key=lambda k: votes[k])

    print(f"""
🎯 OPTIMAL POSITION SIZE: ${overall_best} per 1% move

WINNING METRICS:
  ✅ Best absolute return: ${best_return_amount} ({best_return:.2f}%)
  ✅ Best Sharpe ratio (risk-adjusted): ${best_sharpe_amount} ({best_sharpe:.3f})
  ✅ Best Calmar ratio (recovery efficiency): ${best_calmar_amount} ({best_calmar:.3f})

DETAILED COMPARISON:

$125 Position Size:
  • Return: {res_125.total_return:.2f}%
  • Sharpe: {met_125['sharpe_ratio']:.3f}
  • Calmar: {met_125['calmar_ratio']:.3f}
  • Recovery: {met_125['recovery_days']} days
  • Cash reserve: {res_125.avg_cash_pct:.2f}%
  • vs $150: {res_125.total_return - res_150.total_return:+.2f}% return
  {'✅ CONSERVATIVE OPTION' if res_125.total_return > res_150.total_return else '❌ Lower returns than $150'}

$150 Position Size:
  • Return: {res_150.total_return:.2f}%
  • Sharpe: {met_150['sharpe_ratio']:.3f}
  • Calmar: {met_150['calmar_ratio']:.3f}
  • Recovery: {met_150['recovery_days']} days
  • Cash reserve: {res_150.avg_cash_pct:.2f}%
  • vs $125: {res_150.total_return - res_125.total_return:+.2f}% return
  • vs $175: {res_150.total_return - res_175.total_return:+.2f}% return
  {'✅ BALANCED OPTION' if res_150.total_return > max(res_125.total_return, res_175.total_return) else '❌ Middle performer'}

$175 Position Size:
  • Return: {res_175.total_return:.2f}%
  • Sharpe: {met_175['sharpe_ratio']:.3f}
  • Calmar: {met_175['calmar_ratio']:.3f}
  • Recovery: {met_175['recovery_days']} days
  • Cash reserve: {res_175.avg_cash_pct:.2f}%
  • vs $150: {res_175.total_return - res_150.total_return:+.2f}% return
  {'✅ AGGRESSIVE OPTION' if res_175.total_return > res_150.total_return else '❌ Capital exhaustion kicks in'}

RECOMMENDATION STRATEGY:

If you prioritize ABSOLUTE RETURNS:
  → Use ${best_return_amount} ({best_return:.2f}%)

If you prioritize RISK-ADJUSTED RETURNS:
  → Use ${best_sharpe_amount} (Sharpe: {best_sharpe:.3f})

If you prioritize RECOVERY SPEED:
  → Use ${best_calmar_amount} (Calmar: {best_calmar:.3f})

🏆 OVERALL RECOMMENDATION:
  → ${overall_best} per 1% move
     Final Value: ${results_dict[overall_best]['results'].final_value:,.2f}
     Return: {results_dict[overall_best]['results'].total_return:.2f}%
     Sharpe: {results_dict[overall_best]['metrics']['sharpe_ratio']:.3f}
     Calmar: {results_dict[overall_best]['metrics']['calmar_ratio']:.3f}
""")

    # Summary table
    print("\n" + "=" * 260)
    print("SUMMARY: Quick Reference")
    print("=" * 260)

    summary_data = {
        "Position Size": ["$125", "$150", "$175"],
        "Return": [f"{res_125.total_return:.2f}%", f"{res_150.total_return:.2f}%", f"{res_175.total_return:.2f}%"],
        "Sharpe": [f"{met_125['sharpe_ratio']:.3f}", f"{met_150['sharpe_ratio']:.3f}", f"{met_175['sharpe_ratio']:.3f}"],
        "Calmar": [f"{met_125['calmar_ratio']:.3f}", f"{met_150['calmar_ratio']:.3f}", f"{met_175['calmar_ratio']:.3f}"],
        "Drawdown": [f"{met_125['max_drawdown']:.2f}%", f"{met_150['max_drawdown']:.2f}%", f"{met_175['max_drawdown']:.2f}%"],
        "Recovery": [f"{met_125['recovery_days']}d", f"{met_150['recovery_days']}d", f"{met_175['recovery_days']}d"],
        "Volatility": [f"{met_125['volatility']:.2f}%", f"{met_150['volatility']:.2f}%", f"{met_175['volatility']:.2f}%"],
        "Cash %": [f"{res_125.avg_cash_pct:.2f}%", f"{res_150.avg_cash_pct:.2f}%", f"{res_175.avg_cash_pct:.2f}%"],
    }

    summary_df = pd.DataFrame(summary_data)
    print(summary_df.to_string(index=False))

    print("\n" + "=" * 260)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Refined Position Sizing Analysis: 2x Leveraged Daily Rebalancing"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000,
        help="Initial capital (default $10,000)",
    )

    args = parser.parse_args()
    run_refined_position_sizing(initial_capital=args.capital)
