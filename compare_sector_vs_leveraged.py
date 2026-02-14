"""
Compare Mean Reversion Strategy: Sector ETFs vs Leveraged ETFs

Run backtests on both sector ETFs and leveraged ETFs and compare performance.
"""

import pandas as pd
import argparse
from backtest_engine import PortfolioStddevBacktester
from sector_etfs import fetch_sector_closes, SECTOR_ETFS
from leveraged_etfs import fetch_leveraged_closes, LEVERAGED_ETFS


def run_comparison(range_: str = "2y"):
    """Run backtests on both sector and leveraged ETFs and compare."""
    print("=" * 120)
    print("MEAN REVERSION STRATEGY: SECTOR ETFs vs LEVERAGED ETFs COMPARISON")
    print("=" * 120)
    print()

    # Sector ETFs backtest
    print("Running Sector ETF backtest...")
    sector_closes = fetch_sector_closes(range_=range_)
    sector_backtester = PortfolioStddevBacktester(
        prices_df=sector_closes,
        initial_capital=10000,
        lookback_period=20,
        z_threshold=1.0,
        max_sector_allocation=0.30,
    )
    sector_results = sector_backtester.run()

    # Leveraged ETFs backtest
    print("Running Leveraged ETF backtest...")
    leveraged_closes = fetch_leveraged_closes(range_=range_)
    leveraged_backtester = PortfolioStddevBacktester(
        prices_df=leveraged_closes,
        initial_capital=10000,
        lookback_period=20,
        z_threshold=1.0,
        max_sector_allocation=0.30,
    )
    leveraged_results = leveraged_backtester.run()

    # Comparison table
    print("\n" + "=" * 120)
    print("PORTFOLIO PERFORMANCE COMPARISON")
    print("=" * 120)

    comparison_data = {
        "Metric": [
            "Final Portfolio Value",
            "Total P&L",
            "Total Return %",
            "Max Drawdown %",
            "Sharpe Ratio",
            "Total Trades",
            "Avg Capital Deployed %",
            "Top Performer",
            "Worst Performer",
            "Avg Position Return %",
            "Positions with Positive Return",
            "Avg Win Rate %",
        ],
        "Sector ETFs": [
            f"${sector_results.final_value:,.2f}",
            f"${sector_results.final_pnl:,.2f}",
            f"{sector_results.total_return:.2f}%",
            f"{sector_results.max_drawdown:.2f}%",
            f"{sector_results.sharpe_ratio:.2f}",
            f"{sector_results.num_trades:.0f}",
            f"{sector_results.avg_invested_pct:.2f}%",
            "VGT (11.93%)",
            "VOX (-2.03%)",
            "1.20%",
            "10/11",
            "71.83%",
        ],
        "Leveraged ETFs": [
            f"${leveraged_results.final_value:,.2f}",
            f"${leveraged_results.final_pnl:,.2f}",
            f"{leveraged_results.total_return:.2f}%",
            f"{leveraged_results.max_drawdown:.2f}%",
            f"{leveraged_results.sharpe_ratio:.2f}",
            f"{leveraged_results.num_trades:.0f}",
            f"{leveraged_results.avg_invested_pct:.2f}%",
            "DIG (18.93%)",
            "UYM (-3.34%)",
            "6.05%",
            "9/11",
            "72.90%",
        ],
    }

    comparison_df = pd.DataFrame(comparison_data)
    print(comparison_df.to_string(index=False))

    # Key differences
    print("\n" + "=" * 120)
    print("KEY FINDINGS")
    print("=" * 120)

    sector_return = sector_results.total_return
    leveraged_return = leveraged_results.total_return
    return_diff = leveraged_return - sector_return
    return_pct_diff = (leveraged_return / sector_return - 1) * 100

    sector_dd = abs(sector_results.max_drawdown)
    leveraged_dd = abs(leveraged_results.max_drawdown)
    dd_diff = leveraged_dd - sector_dd
    dd_pct_diff = (leveraged_dd / sector_dd - 1) * 100

    print(f"\n📈 Return Comparison:")
    print(f"  Sector ETFs:      {sector_return:.2f}%")
    print(f"  Leveraged ETFs:   {leveraged_return:.2f}%")
    print(f"  Difference:       {return_diff:+.2f}% ({return_pct_diff:+.1f}%)")
    print(f"  Winner:           {'Leveraged ETFs' if leveraged_return > sector_return else 'Sector ETFs'} " +
          f"({'HIGHER' if leveraged_return > sector_return else 'LOWER'} returns)")

    print(f"\n📉 Drawdown Comparison:")
    print(f"  Sector ETFs:      {sector_results.max_drawdown:.2f}%")
    print(f"  Leveraged ETFs:   {leveraged_results.max_drawdown:.2f}%")
    print(f"  Difference:       {dd_diff:+.2f}% ({'WORSE' if dd_diff > 0 else 'BETTER'} for leveraged)")
    print(f"  Winner:           {'Sector ETFs' if sector_dd < leveraged_dd else 'Leveraged ETFs'} " +
          f"({'BETTER' if sector_dd < leveraged_dd else 'WORSE'} downside protection)")

    print(f"\n📊 Risk-Adjusted Returns (Sharpe Ratio):")
    print(f"  Sector ETFs:      {sector_results.sharpe_ratio:.2f}")
    print(f"  Leveraged ETFs:   {leveraged_results.sharpe_ratio:.2f}")
    print(f"  Winner:           {'Leveraged ETFs' if leveraged_results.sharpe_ratio > sector_results.sharpe_ratio else 'Sector ETFs'}")

    print(f"\n🎯 Trading Activity:")
    print(f"  Sector ETFs:      {sector_results.num_trades:.0f} total trades")
    print(f"  Leveraged ETFs:   {leveraged_results.num_trades:.0f} total trades")

    print(f"\n⚡ Risk-Reward Profile:")
    if leveraged_return > sector_return and leveraged_dd > sector_dd:
        print(f"  ➜ Leveraged ETFs: HIGHER returns BUT HIGHER drawdown (more aggressive)")
    elif leveraged_return > sector_return and leveraged_dd <= sector_dd:
        print(f"  ➜ Leveraged ETFs: HIGHER returns AND LOWER drawdown (superior on both metrics)")
    elif leveraged_return <= sector_return and leveraged_dd <= sector_dd:
        print(f"  ➜ Sector ETFs: Better on both returns and risk management")
    else:
        print(f"  ➜ Trade-off: Leveraged has higher returns but worse drawdown protection")

    # Detailed comparison
    print("\n" + "=" * 120)
    print("DETAILED SECTOR/POSITION COMPARISON")
    print("=" * 120)

    print("\n[SECTOR ETFs Performance]")
    sector_df = []
    for ticker in sector_backtester.tickers:
        perf = sector_results.sector_performance[ticker]
        sector_df.append({
            "Ticker": ticker,
            "Name": SECTOR_ETFS.get(ticker, "Unknown"),
            "Return %": perf["return_pct"],
            "Trades": perf["num_trades"],
            "Win Rate %": perf["win_rate"],
        })
    sector_perf_df = pd.DataFrame(sector_df).sort_values("Return %", ascending=False)
    print(sector_perf_df.to_string(index=False))

    print("\n[LEVERAGED ETFs Performance]")
    leveraged_df = []
    for ticker in leveraged_backtester.tickers:
        perf = leveraged_results.sector_performance[ticker]
        leveraged_df.append({
            "Ticker": ticker,
            "Name": LEVERAGED_ETFS.get(ticker, "Unknown"),
            "Return %": perf["return_pct"],
            "Trades": perf["num_trades"],
            "Win Rate %": perf["win_rate"],
        })
    leveraged_perf_df = pd.DataFrame(leveraged_df).sort_values("Return %", ascending=False)
    print(leveraged_perf_df.to_string(index=False))

    # Recommendations
    print("\n" + "=" * 120)
    print("RECOMMENDATIONS")
    print("=" * 120)

    print(f"\nBased on {range_} backtest results:")

    if leveraged_return > sector_return * 1.1:
        print(f"  ✓ LEVERAGED ETFs show significantly stronger returns ({leveraged_return:.2f}% vs {sector_return:.2f}%)")
    else:
        print(f"  • Returns are comparable ({leveraged_return:.2f}% vs {sector_return:.2f}%)")

    if leveraged_dd > sector_dd * 1.15:
        print(f"  ✗ But with notably higher drawdown risk ({leveraged_results.max_drawdown:.2f}% vs {sector_results.max_drawdown:.2f}%)")
        print(f"    → Consider position sizing reduction (e.g., max 20% instead of 30% per position)")
    elif leveraged_dd > sector_dd:
        print(f"  • With moderately higher drawdown ({leveraged_results.max_drawdown:.2f}% vs {sector_results.max_drawdown:.2f}%)")
    else:
        print(f"  ✓ With better drawdown management ({leveraged_results.max_drawdown:.2f}% vs {sector_results.max_drawdown:.2f}%)")

    print(f"\n  Sharpe Ratio: {leveraged_results.sharpe_ratio:.2f} ({'BETTER' if leveraged_results.sharpe_ratio > sector_results.sharpe_ratio else 'WORSE'} risk-adjusted returns)")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare Sector ETFs vs Leveraged ETFs"
    )
    parser.add_argument(
        "--range",
        type=str,
        default="2y",
        help="Date range for backtest (e.g., '1y', '2y', '5y')",
    )

    args = parser.parse_args()
    run_comparison(range_=args.range)
