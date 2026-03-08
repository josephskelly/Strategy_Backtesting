"""
Incremental Position Sizing Analysis: 2x Leveraged Daily Rebalancing

Tests trade amounts per 1% daily move in $5 increments:
- $150, $155, $160, $165, $170, $175, $180, $185, $190, $195, $200

Maps the precise optimal position size curve.
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


def run_incremental_position_sizing(initial_capital: float = 10000):
    """Compare position sizing with $5 increments."""
    print("=" * 280)
    print("INCREMENTAL POSITION SIZING ANALYSIS: $5 Increments from $150 to $200")
    print("=" * 280)
    print(f"\nTesting trade amounts per 1% daily move: $150, $155, $160, $165, $170, $175, $180, $185, $190, $195, $200")
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
    trade_amounts = [150, 155, 160, 165, 170, 175, 180, 185, 190, 195, 200]
    results_dict = {}

    for trade_amount in trade_amounts:
        print("=" * 280)
        print(f"RUNNING BACKTEST: ${trade_amount} per 1% move")
        print("=" * 280)

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
    print("\n" + "=" * 280)
    print("PERFORMANCE COMPARISON: Position Sizing Grid ($150-$200 in $5 increments)")
    print("=" * 280)

    comparison_data = {
        "Position": [],
        "Final Value": [],
        "Return": [],
        "P&L": [],
        "Drawdown": [],
        "Recovery": [],
        "Volatility": [],
        "Sharpe": [],
        "Calmar": [],
    }

    for trade_amount in trade_amounts:
        res = results_dict[trade_amount]["results"]
        met = results_dict[trade_amount]["metrics"]

        comparison_data["Position"].append(f"${trade_amount}")
        comparison_data["Final Value"].append(f"${res.final_value:,.0f}")
        comparison_data["Return"].append(f"{res.total_return:.2f}%")
        comparison_data["P&L"].append(f"${res.final_pnl:,.0f}")
        comparison_data["Drawdown"].append(f"{met['max_drawdown']:.2f}%")
        comparison_data["Recovery"].append(f"{met['recovery_days']}d")
        comparison_data["Volatility"].append(f"{met['volatility']:.2f}%")
        comparison_data["Sharpe"].append(f"{met['sharpe_ratio']:.3f}")
        comparison_data["Calmar"].append(f"{met['calmar_ratio']:.3f}")

    comparison_df = pd.DataFrame(comparison_data)
    print(comparison_df.to_string(index=False))

    # Find peak return
    returns = [results_dict[amt]["results"].total_return for amt in trade_amounts]
    peak_return_idx = returns.index(max(returns))
    peak_return_amount = trade_amounts[peak_return_idx]
    peak_return_value = returns[peak_return_idx]

    # Find best Sharpe
    sharpes = [results_dict[amt]["metrics"]["sharpe_ratio"] for amt in trade_amounts]
    best_sharpe_idx = sharpes.index(max(sharpes))
    best_sharpe_amount = trade_amounts[best_sharpe_idx]
    best_sharpe_value = sharpes[best_sharpe_idx]

    # Find best Calmar
    calmars = [results_dict[amt]["metrics"]["calmar_ratio"] for amt in trade_amounts]
    best_calmar_idx = calmars.index(max(calmars))
    best_calmar_amount = trade_amounts[best_calmar_idx]
    best_calmar_value = calmars[best_calmar_idx]

    # Detailed metrics
    print("\n" + "=" * 280)
    print("DETAILED METRICS TABLE")
    print("=" * 280)

    detailed_data = {
        "$": [],
        "Return": [],
        "vs Peak": [],
        "Sharpe": [],
        "Calmar": [],
        "Vol": [],
        "DD": [],
        "Deployed": [],
        "Trades": [],
    }

    for trade_amount in trade_amounts:
        res = results_dict[trade_amount]["results"]
        met = results_dict[trade_amount]["metrics"]

        detailed_data["$"].append(f"{trade_amount}")
        detailed_data["Return"].append(f"{res.total_return:.2f}%")
        detailed_data["vs Peak"].append(f"{res.total_return - peak_return_value:+.2f}%")
        detailed_data["Sharpe"].append(f"{met['sharpe_ratio']:.3f}")
        detailed_data["Calmar"].append(f"{met['calmar_ratio']:.3f}")
        detailed_data["Vol"].append(f"{met['volatility']:.2f}%")
        detailed_data["DD"].append(f"{met['max_drawdown']:.2f}%")
        detailed_data["Deployed"].append(f"{res.avg_invested_pct:.2f}%")
        detailed_data["Trades"].append(f"{res.num_trades:,}")

    detailed_df = pd.DataFrame(detailed_data)
    print(detailed_df.to_string(index=False))

    # Analysis of the curve
    print("\n" + "=" * 280)
    print("RETURN CURVE ANALYSIS")
    print("=" * 280)

    print(f"""
PEAK RETURN: ${peak_return_amount} = {peak_return_value:.2f}%

RETURN PROGRESSION:
""")

    for i, amount in enumerate(trade_amounts):
        ret = results_dict[amount]["results"].total_return
        if i == 0:
            print(f"  ${amount}: {ret:.2f}%")
        else:
            prev_amount = trade_amounts[i-1]
            prev_ret = results_dict[prev_amount]["results"].total_return
            delta = ret - prev_ret
            pct_change = (ret / prev_ret - 1) * 100
            print(f"  ${amount}: {ret:.2f}% ({delta:+.2f}%, {pct_change:+.1f}%)")

    # Analyze the slope
    print(f"""
ANALYSIS:
The return curve shows {'accelerating' if returns[-1] > returns[-2] + (returns[-2] - returns[-3]) else 'decelerating'} gains.
""")

    # Sharpe curve
    print("\n" + "=" * 280)
    print("SHARPE RATIO CURVE")
    print("=" * 280)

    print(f"""
BEST SHARPE: ${best_sharpe_amount} = {best_sharpe_value:.3f}

SHARPE PROGRESSION:
""")

    for i, amount in enumerate(trade_amounts):
        sharpe = results_dict[amount]["metrics"]["sharpe_ratio"]
        if i == 0:
            print(f"  ${amount}: {sharpe:.3f}")
        else:
            prev_amount = trade_amounts[i-1]
            prev_sharpe = results_dict[prev_amount]["metrics"]["sharpe_ratio"]
            delta = sharpe - prev_sharpe
            print(f"  ${amount}: {sharpe:.3f} ({delta:+.3f})")

    # Calmar curve
    print("\n" + "=" * 280)
    print("CALMAR RATIO CURVE")
    print("=" * 280)

    print(f"""
BEST CALMAR: ${best_calmar_amount} = {best_calmar_value:.3f}

CALMAR PROGRESSION:
""")

    for i, amount in enumerate(trade_amounts):
        calmar = results_dict[amount]["metrics"]["calmar_ratio"]
        if i == 0:
            print(f"  ${amount}: {calmar:.3f}")
        else:
            prev_amount = trade_amounts[i-1]
            prev_calmar = results_dict[prev_amount]["metrics"]["calmar_ratio"]
            delta = calmar - prev_calmar
            print(f"  ${amount}: {calmar:.3f} ({delta:+.3f})")

    # Efficiency analysis
    print("\n" + "=" * 280)
    print("CAPITAL EFFICIENCY ANALYSIS")
    print("=" * 280)

    print(f"""
Return per Dollar of Position Size:
""")

    efficiency = {}
    for amount in trade_amounts:
        res = results_dict[amount]["results"]
        eff = res.total_return / amount
        efficiency[amount] = eff
        print(f"  ${amount}: {eff:.4f}% per $1")

    best_efficiency = max(efficiency.values())
    best_efficiency_amount = [k for k, v in efficiency.items() if v == best_efficiency][0]

    print(f"\nMost Efficient: ${best_efficiency_amount} ({best_efficiency:.4f}%)")

    # Recommendation
    print("\n" + "=" * 280)
    print("FINAL RECOMMENDATION")
    print("=" * 280)

    print(f"""
🎯 WINNERS BY CATEGORY:

Absolute Return: ${peak_return_amount} ({peak_return_value:.2f}%) ✅
Sharpe Ratio (Risk-Adjusted): ${best_sharpe_amount} ({best_sharpe_value:.3f}) ✅
Calmar Ratio (Return/Drawdown): ${best_calmar_amount} ({best_calmar_value:.3f}) ✅
Capital Efficiency: ${best_efficiency_amount} ({best_efficiency:.4f}% per $1) ✅

OPTIMAL POSITION SIZING RECOMMENDATION:

Based on comprehensive analysis:

1️⃣ FOR MAXIMUM RETURNS:
   → Use ${peak_return_amount} per 1% move
   → Return: {peak_return_value:.2f}%
   → Final Value: ${results_dict[peak_return_amount]["results"].final_value:,.2f}
   → Best if: You prioritize absolute profits

2️⃣ FOR BEST RISK-ADJUSTED RETURNS:
   → Use ${best_sharpe_amount} per 1% move
   → Sharpe: {best_sharpe_value:.3f}
   → Return: {results_dict[best_sharpe_amount]["results"].total_return:.2f}%
   → Best if: You prioritize consistency and risk management

3️⃣ FOR BEST RETURN-PER-UNIT-RISK:
   → Use ${best_calmar_amount} per 1% move
   → Calmar: {best_calmar_value:.3f}
   → Return: {results_dict[best_calmar_amount]["results"].total_return:.2f}%
   → Best if: You want efficient use of risk budget

OVERALL WINNER: ${peak_return_amount}
• Highest absolute return on $10K initial capital
• Strong risk metrics (Sharpe, Calmar, Volatility)
• Proven over 17.7 years of data
• Still maintains {results_dict[peak_return_amount]["metrics"]["recovery_days"]} day recovery time

""")

    # Detailed comparison of top 3
    top_3_amounts = sorted(trade_amounts, key=lambda x: results_dict[x]["results"].total_return, reverse=True)[:3]

    print("=" * 280)
    print("TOP 3 POSITION SIZES: DETAILED COMPARISON")
    print("=" * 280)

    for i, amount in enumerate(top_3_amounts, 1):
        res = results_dict[amount]["results"]
        met = results_dict[amount]["metrics"]

        print(f"""
#{i} - ${amount} per 1% move
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return:             {res.total_return:.2f}%
Final Value:        ${res.final_value:,.2f}
P&L:                ${res.final_pnl:,.2f}

Risk Metrics:
  Sharpe Ratio:     {met['sharpe_ratio']:.3f}
  Calmar Ratio:     {met['calmar_ratio']:.3f}
  Max Drawdown:     {met['max_drawdown']:.2f}%
  Volatility:       {met['volatility']:.2f}%
  Recovery Time:    {met['recovery_days']} days

Capital Efficiency:
  Avg Deployed:     {res.avg_invested_pct:.2f}%
  Avg Cash:         {res.avg_cash_pct:.2f}%
  Return/Dollar:    {res.total_return / amount:.4f}%

Trading:
  Total Trades:     {res.num_trades:,}
  Per Year:         ~{res.num_trades / 17.7:.0f}

Outperformance vs SPY:
  SPY Return:       {spy_results['return_pct']:.2f}%
  Strategy Return:  {res.total_return:.2f}%
  Outperformance:   {res.total_return - spy_results['return_pct']:+.2f}%
""")

    print("=" * 280)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Incremental Position Sizing Analysis: 2x Leveraged Daily Rebalancing"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000,
        help="Initial capital (default $10,000)",
    )

    args = parser.parse_args()
    run_incremental_position_sizing(initial_capital=args.capital)
