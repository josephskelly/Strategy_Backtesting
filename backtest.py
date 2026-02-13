"""
Main Mean Reversion Portfolio Backtester

Run a single backtest on 2-year (or custom range) historical data.

Usage:
    python backtest.py                    # Default: 2 year backtest
    python backtest.py --range 1y         # 1 year backtest
    python backtest.py --range 5y         # 5 year backtest
"""

import pandas as pd
import argparse
from backtest_engine import PortfolioStddevBacktester
from sector_etfs import fetch_sector_closes, SECTOR_ETFS


def run_backtest(range_: str = "2y"):
    """Run a single portfolio backtest."""
    print("=" * 100)
    print("PORTFOLIO MEAN REVERSION BACKTEST")
    print("=" * 100)
    print()
    print("Configuration:")
    print(f"  Initial Capital:           $10,000")
    print(f"  Allocation Method:         Dynamic Shared Pool")
    print(f"  Max Per Sector:            30% ($3,000)")
    print(f"  Lookback Period:           20 days")
    print(f"  Z-Score Threshold:         1.0 (buy at -1.0, sell at +1.0)")
    print(f"  Position Sizing:           Linear (0-100% of available capital)")
    print()

    print(f"Fetching sector ETF prices for range={range_}...")
    closes = fetch_sector_closes(range_=range_)

    print("Running backtest...")
    backtester = PortfolioStddevBacktester(
        prices_df=closes,
        initial_capital=10000,
        lookback_period=20,
        z_threshold=1.0,
        max_sector_allocation=0.30,
    )
    results = backtester.run()

    # Display portfolio-level results
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
    print(f"Avg Cash Sitting Idle:       {results.avg_cash_pct:>12.2f}%")

    # Display sector performance
    print("\n" + "=" * 100)
    print("SECTOR PERFORMANCE")
    print("=" * 100)

    sector_df = []
    for ticker in backtester.tickers:
        perf = results.sector_performance[ticker]
        sector_df.append({
            "Ticker": ticker,
            "Sector": SECTOR_ETFS.get(ticker, "Unknown"),
            "Trades": perf["num_trades"],
            "P&L": perf["pnl"],
            "Return %": perf["return_pct"],
            "Wins": perf["num_wins"],
            "Win Rate %": perf["win_rate"],
        })

    sector_results = pd.DataFrame(sector_df)
    sector_results = sector_results.sort_values("Return %", ascending=False)

    print(sector_results.to_string(index=False))

    # Summary statistics
    print("\n" + "=" * 100)
    print("SECTOR SUMMARY")
    print("=" * 100)

    print(f"\nTop Performer:               {sector_results.iloc[0]['Ticker']} ({sector_results.iloc[0]['Return %']:.2f}%)")
    print(f"Worst Performer:             {sector_results.iloc[-1]['Ticker']} ({sector_results.iloc[-1]['Return %']:.2f}%)")
    print(f"Average Sector Return:       {sector_results['Return %'].mean():.2f}%")
    print(f"Sectors with Positive Return: {len(sector_results[sector_results['Return %'] > 0])}/11")
    print(f"Total Wins:                  {sector_results['Wins'].sum():.0f} trades")
    print(f"Avg Win Rate:                {sector_results['Win Rate %'].mean():.2f}%")

    # Save results
    output_file = "backtest_results.csv"
    sector_results.to_csv(output_file, index=False)
    print(f"\n✓ Results saved to {output_file}")

    # Capital efficiency summary
    print("\n" + "=" * 100)
    print("CAPITAL EFFICIENCY")
    print("=" * 100)

    if results.snapshots:
        max_cash = max([s.cash for s in results.snapshots])
        min_cash = min([s.cash for s in results.snapshots])
        max_deployed = max([
            (s.total_value - s.cash) / s.total_value * 100
            if s.total_value > 0 else 0
            for s in results.snapshots
        ])

        print(f"\nAverage Capital Deployed:    {results.avg_invested_pct:.2f}%")
        print(f"Peak Capital Deployed:       {max_deployed:.2f}%")
        print(f"Max Cash Available:          ${max_cash:,.2f}")
        print(f"Min Cash Available:          ${min_cash:,.2f}")

    print()

    return results, backtester


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Mean Reversion Portfolio Backtester"
    )
    parser.add_argument(
        "--range",
        type=str,
        default="2y",
        help="Date range for backtest (e.g., '1y', '2y', '5y')",
    )

    args = parser.parse_args()
    results, backtester = run_backtest(range_=args.range)
