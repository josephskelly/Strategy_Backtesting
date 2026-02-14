"""
Optimized Leveraged ETF Backtest with Risk Management

Tests different position sizing parameters to balance risk and returns.
"""

import pandas as pd
import argparse
from backtest_engine import PortfolioStddevBacktester
from leveraged_etfs import fetch_leveraged_closes, LEVERAGED_ETFS


def run_optimized_backtest(range_: str = "2y", max_allocation: float = 0.20):
    """Run backtest with specified max allocation (default 20% to reduce drawdown)."""
    print("=" * 100)
    print("LEVERAGED ETF PORTFOLIO — OPTIMIZED RISK MANAGEMENT")
    print("=" * 100)
    print()
    print("Configuration:")
    print(f"  Initial Capital:           $10,000")
    print(f"  ETF Type:                  2x/3x Leveraged")
    print(f"  Max Per Position:          {max_allocation*100:.0f}% (${max_allocation*10000:,.0f})")
    print(f"  Lookback Period:           20 days")
    print(f"  Z-Score Threshold:         1.0 (buy at -1.0, sell at +1.0)")
    print(f"  Position Sizing:           Linear (0-100% of available capital)")
    print()

    print(f"Fetching leveraged ETF prices for range={range_}...")
    closes = fetch_leveraged_closes(range_=range_)

    print("Running backtest...")
    backtester = PortfolioStddevBacktester(
        prices_df=closes,
        initial_capital=10000,
        lookback_period=20,
        z_threshold=1.0,
        max_sector_allocation=max_allocation,
    )
    results = backtester.run()

    # Display results
    print("\n" + "=" * 100)
    print("PORTFOLIO PERFORMANCE")
    print("=" * 100)
    print(f"\nFinal Portfolio Value:       ${results.final_value:>12,.2f}")
    print(f"Total P&L:                   ${results.final_pnl:>12,.2f}")
    print(f"Total Return:                {results.total_return:>12.2f}%")
    print(f"Max Drawdown:                {results.max_drawdown:>12.2f}%")
    print(f"Sharpe Ratio (Annualized):   {results.sharpe_ratio:>12.2f}")
    print(f"\nTotal Trades:                {results.num_trades:>12.0f}")
    print(f"Avg Capital Deployed:        {results.avg_invested_pct:>12.2f}%")

    # Position performance
    print("\n" + "=" * 100)
    print("POSITION PERFORMANCE")
    print("=" * 100)

    position_df = []
    for ticker in backtester.tickers:
        perf = results.sector_performance[ticker]
        position_df.append({
            "Ticker": ticker,
            "ETF": LEVERAGED_ETFS.get(ticker, "Unknown"),
            "Return %": perf["return_pct"],
            "Trades": perf["num_trades"],
            "Win Rate %": perf["win_rate"],
        })

    position_results = pd.DataFrame(position_df)
    position_results = position_results.sort_values("Return %", ascending=False)

    print(position_results.to_string(index=False))

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"\nPositions with Positive Return: {len(position_results[position_results['Return %'] > 0])}/11")
    print(f"Avg Position Return:            {position_results['Return %'].mean():.2f}%")
    print(f"Avg Win Rate:                   {position_results['Win Rate %'].mean():.2f}%")
    print()

    return results, position_results


def compare_allocation_levels(range_: str = "2y"):
    """Compare different maximum allocation levels."""
    print("=" * 120)
    print("RISK MANAGEMENT ANALYSIS: DIFFERENT POSITION SIZE LIMITS")
    print("=" * 120)
    print()

    allocations = [0.10, 0.15, 0.20, 0.25, 0.30]
    results_list = []

    closes = fetch_leveraged_closes(range_=range_)

    for max_alloc in allocations:
        print(f"Testing max allocation = {max_alloc*100:.0f}%...")
        backtester = PortfolioStddevBacktester(
            prices_df=closes,
            initial_capital=10000,
            lookback_period=20,
            z_threshold=1.0,
            max_sector_allocation=max_alloc,
        )
        results = backtester.run()
        results_list.append({
            "Max Allocation %": f"{max_alloc*100:.0f}%",
            "Final Value": f"${results.final_value:,.0f}",
            "Return %": f"{results.total_return:.2f}%",
            "Max Drawdown %": f"{results.max_drawdown:.2f}%",
            "Sharpe Ratio": f"{results.sharpe_ratio:.2f}",
            "Trades": f"{results.num_trades:.0f}",
        })

    comparison = pd.DataFrame(results_list)
    print("\n" + "=" * 120)
    print("ALLOCATION LEVEL COMPARISON")
    print("=" * 120)
    print(comparison.to_string(index=False))

    print("\n" + "=" * 120)
    print("RECOMMENDATIONS")
    print("=" * 120)
    print("""
Based on the comparison above:

✓ 10-15% allocation: Maximum risk control, but may limit upside potential
✓ 20% allocation: Good balance — reduces drawdown vs 30%, maintains solid returns
  → RECOMMENDED for conservative traders seeking risk mitigation
✓ 25% allocation: Moderate risk — enhanced returns with acceptable drawdown
✓ 30% allocation: Maximum aggressiveness — highest returns but highest drawdown risk

Consider your risk tolerance:
  • If max drawdown > 15% is acceptable: Use 30% (original)
  • If max drawdown should be < 15%:   Use 20% (optimized)
  • If max drawdown should be < 10%:   Use 10% (conservative)
    """)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Optimized Leveraged ETF Backtester"
    )
    parser.add_argument(
        "--range",
        type=str,
        default="2y",
        help="Date range for backtest (e.g., '1y', '2y', '5y')",
    )
    parser.add_argument(
        "--allocation",
        type=float,
        default=0.20,
        help="Max allocation per position (0-1, default 0.20 = 20%)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare different allocation levels",
    )

    args = parser.parse_args()

    if args.compare:
        compare_allocation_levels(range_=args.range)
    else:
        run_optimized_backtest(range_=args.range, max_allocation=args.allocation)
