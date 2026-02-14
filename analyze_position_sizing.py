"""
Analyze position sizing and cash management

Check:
1. How much total capital is deployed per year?
2. Do we ever run out of cash?
3. What's the optimal trade size?
4. How leveraged are we at peak?
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


def analyze_capital_management(sector_closes: pd.DataFrame, trade_amount: float = 300, initial_capital: float = 10000):
    """Analyze cash balance and capital deployment over time."""

    print("=" * 180)
    print(f"POSITION SIZING ANALYSIS")
    print(f"Initial Capital: ${initial_capital:,.0f}")
    print(f"Trade Amount per 1% move: ${trade_amount:.0f}")
    print("=" * 180)
    print()

    # Create the backtester
    backtester = DailyRebalanceBacktester(
        prices_df=sector_closes,
        initial_capital=initial_capital,
        trade_amount_per_percent=trade_amount,
    )

    # Run backtest and capture snapshots
    results = backtester.run()

    # Analyze snapshots
    snapshots = results.snapshots

    cash_balances = [s.cash for s in snapshots]
    total_values = [s.total_value for s in snapshots]
    invested_values = [s.invested_value for s in snapshots]

    # Calculate metrics
    min_cash = min(cash_balances)
    min_cash_idx = cash_balances.index(min_cash)
    min_cash_date = snapshots[min_cash_idx].date

    max_invested = max(invested_values)
    max_invested_idx = invested_values.index(max_invested)
    max_invested_date = snapshots[max_invested_idx].date

    avg_cash = np.mean(cash_balances)
    avg_invested_pct = np.mean([s.invested_value / s.total_value * 100 if s.total_value > 0 else 0 for s in snapshots])

    # Never went negative?
    min_cash_ever = min_cash
    went_negative = min_cash < 0

    print(f"Capital Allocation Analysis:")
    print(f"-" * 180)
    print(f"Minimum Cash Balance: ${min_cash:,.0f}")
    if went_negative:
        print(f"  ⚠️  WARNING: Cash went NEGATIVE (would need margin/borrowing)")
    else:
        print(f"  ✅ Always solvent (never needed borrowing)")
    print(f"  Occurred on: {min_cash_date.strftime('%Y-%m-%d')}")
    print()
    print(f"Maximum Invested Value: ${max_invested:,.0f}")
    print(f"  Occurred on: {max_invested_date.strftime('%Y-%m-%d')}")
    print()
    print(f"Average Cash Balance: ${avg_cash:,.0f}")
    print(f"Average Cash as % of Portfolio: {(avg_cash/initial_capital)*100:.1f}%")
    print(f"Average Invested as % of Portfolio: {avg_invested_pct:.1f}%")
    print()

    # Annual analysis
    print(f"Annual Capital Deployment:")
    print(f"-" * 180)

    snapshots_df = pd.DataFrame([
        {
            'date': s.date,
            'cash': s.cash,
            'invested': s.invested_value,
            'total': s.total_value,
        }
        for s in snapshots
    ])

    snapshots_df['year'] = snapshots_df['date'].dt.year

    for year in sorted(snapshots_df['year'].unique()):
        year_data = snapshots_df[snapshots_df['year'] == year]
        if len(year_data) > 0:
            start_cash = year_data.iloc[0]['cash']
            end_cash = year_data.iloc[-1]['cash']
            min_cash_year = year_data['cash'].min()
            max_invested_year = year_data['invested'].max()

            cash_deployed = start_cash - end_cash

            print(f"{year}:")
            print(f"  Start Cash: ${start_cash:>12,.0f}")
            print(f"  End Cash:   ${end_cash:>12,.0f}")
            print(f"  Min Cash:   ${min_cash_year:>12,.0f}")
            print(f"  Max Invested: ${max_invested_year:>12,.0f}")
            print(f"  Net Deployment: ${cash_deployed:>12,.0f}")
            print()

    # Summary
    print(f"=" * 180)
    print(f"SUMMARY FOR ${trade_amount:.0f} PER 1% MOVE")
    print(f"=" * 180)
    print()

    if went_negative:
        print(f"❌ NOT SUSTAINABLE: Ran out of cash on {min_cash_date.strftime('%Y-%m-%d')}")
        print(f"   Need at least ${abs(min_cash):.0f} more capital")
        print()
    else:
        cash_cushion = min_cash / initial_capital * 100
        print(f"✅ SUSTAINABLE: Never ran out of cash")
        print(f"   Worst case cash reserve: ${min_cash:,.0f} ({cash_cushion:.1f}% of starting capital)")
        print()

    print(f"Capital Utilization:")
    print(f"  Average invested: {avg_invested_pct:.1f}%")
    print(f"  Average cash kept: {100-avg_invested_pct:.1f}%")
    print()

    return results, min_cash, max_invested, avg_invested_pct


def test_multiple_trade_amounts(sector_closes: pd.DataFrame, initial_capital: float = 10000):
    """Test different trade amounts to find optimal sizing."""

    print("\n" + "=" * 180)
    print("TESTING DIFFERENT POSITION SIZES")
    print("=" * 180)
    print()

    trade_amounts = [100, 150, 200, 250, 300, 350, 400, 500]
    results_list = []

    for trade_amount in trade_amounts:
        print(f"Testing ${trade_amount} per 1% move...")

        try:
            backtester = DailyRebalanceBacktester(
                prices_df=sector_closes,
                initial_capital=initial_capital,
                trade_amount_per_percent=trade_amount,
            )
            results = backtester.run()

            # Get stats
            snapshots = results.snapshots
            min_cash = min([s.cash for s in snapshots])
            avg_cash_pct = np.mean([s.cash / s.total_value * 100 if s.total_value > 0 else 0 for s in snapshots])

            results_list.append({
                'trade_amount': trade_amount,
                'final_return': results.total_return,
                'final_value': results.final_value,
                'sharpe': results.sharpe_ratio,
                'min_cash': min_cash,
                'avg_cash_pct': avg_cash_pct,
                'sustainable': min_cash >= 0,
            })

        except Exception as e:
            print(f"  Error: {str(e)[:100]}")
            continue

    # Display results
    print()
    print("=" * 180)
    print(f"{'Trade $':<12} | {'Final Return':<15} | {'Final Value':<15} | {'Sharpe':<10} | {'Min Cash':<15} | {'Avg Cash %':<12} | {'Status':<12}")
    print("-" * 180)

    for r in results_list:
        status = "✅ OK" if r['sustainable'] else "❌ FAIL"
        print(f"${r['trade_amount']:<11.0f} | {r['final_return']:>13.2f}% | ${r['final_value']:>13,.0f} | {r['sharpe']:>8.3f} | ${r['min_cash']:>13,.0f} | {r['avg_cash_pct']:>10.1f}% | {status:<12}")

    print()
    print("RECOMMENDATION:")
    print("-" * 180)

    sustainable = [r for r in results_list if r['sustainable']]

    if sustainable:
        best = max(sustainable, key=lambda x: x['final_return'])
        print(f"✅ All tested amounts are sustainable (never run out of cash)")
        print()
        print(f"Best Performance: ${best['trade_amount']:.0f} per 1%")
        print(f"  Final Return: {best['final_return']:.2f}%")
        print(f"  Final Value: ${best['final_value']:,.0f}")
        print(f"  Sharpe: {best['sharpe']:.3f}")
        print(f"  Min Cash: ${best['min_cash']:,.0f}")
        print()
    else:
        print(f"❌ None of the tested amounts are sustainable")
        print()

    # Find the sweet spot
    optimal = max(sustainable, key=lambda x: x['final_return'])
    print(f"OPTIMAL POSITION SIZE: ${optimal['trade_amount']:.0f} per 1% daily move")
    print()


if __name__ == "__main__":
    print("Fetching sector data...")
    sector_closes = fetch_sector_closes(range_="30y")

    if len(sector_closes) < 100:
        print("Not enough data.")
        exit(1)

    # Analyze current $300 configuration
    print("\nAnalyzing current $300 configuration...")
    results, min_cash, max_invested, avg_invested_pct = analyze_capital_management(
        sector_closes,
        trade_amount=300,
        initial_capital=10000
    )

    # Test multiple amounts
    test_multiple_trade_amounts(sector_closes, initial_capital=10000)

    # Test with larger initial capital
    print("\n" + "=" * 180)
    print("TESTING WITH LARGER STARTING CAPITAL")
    print("=" * 180)
    print()

    for initial_cap in [10000, 20000, 50000]:
        print(f"\nInitial Capital: ${initial_cap:,.0f}, Trade Amount: $300 per 1%")
        analyze_capital_management(sector_closes, trade_amount=300, initial_capital=initial_cap)
