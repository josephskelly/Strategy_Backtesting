"""
Detailed analysis tool for standard deviation trading strategy.

Allows testing different parameters and analyzing specific tickers.
"""

import sys
from stddev_backtest import (
    analyze_single_ticker,
    backtest_all_etfs,
    SECTOR_ETFS,
)


def print_trade_history(results, max_trades: int = 20):
    """Print detailed trade history."""
    print(f"\n  Trade History (showing first {max_trades}):")
    print("  " + "-" * 80)
    print(f"  {'Date':<12} {'Action':<6} {'Price':<10} {'Qty':<10} {'Z-Score':<10}")
    print("  " + "-" * 80)

    for i, trade in enumerate(results.trades[:max_trades]):
        print(
            f"  {str(trade.date.date()):<12} {trade.action:<6} "
            f"${trade.price:<9.2f} {trade.quantity:<9.2f} {trade.z_score:<9.2f}"
        )

    if len(results.trades) > max_trades:
        print(f"  ... and {len(results.trades) - max_trades} more trades")


def analyze_ticker_detailed(ticker: str):
    """Analyze a specific ticker with detailed output."""
    if ticker not in SECTOR_ETFS:
        print(f"Error: Ticker '{ticker}' not found")
        print(f"Available tickers: {', '.join(SECTOR_ETFS.keys())}")
        return

    print("=" * 90)
    print(f"  Detailed Analysis: {ticker} ({SECTOR_ETFS[ticker]})")
    print("=" * 90)

    results = analyze_single_ticker(ticker)

    print(f"\nPerformance Metrics:")
    print(f"  Total Return:      {results.total_return:.2f}%")
    print(f"  Max Drawdown:      {results.max_drawdown:.2f}%")
    print(f"  Sharpe Ratio:      {results.sharpe_ratio:.2f}")
    print(f"  Win Rate:          {results.win_rate:.2f}%")
    print(f"  Final P&L:         ${results.final_pnl:,.2f}")
    print(f"  Final Position:    {results.final_shares:.2f} shares")
    print(f"  Total Trades:      {results.num_trades}")

    print_trade_history(results)
    print()


def test_parameters(lookback: int, z_threshold: float):
    """Test backtest with specific parameters."""
    print("=" * 90)
    print(f"  Parameter Test: Lookback={lookback}, Z-Threshold={z_threshold}")
    print("=" * 90)
    print()

    results_df = backtest_all_etfs(
        range_="2y",
        lookback_period=lookback,
        z_threshold=z_threshold,
        initial_capital=10000,
    )

    print("\nResults:")
    print(results_df.to_string(index=False, float_format="%.2f"))
    print()

    # Summary stats
    avg_return = results_df["Total Return %"].mean()
    best_ticker = results_df["Ticker"].iloc[0]
    best_return = results_df["Total Return %"].iloc[0]
    worst_ticker = results_df["Ticker"].iloc[-1]
    worst_return = results_df["Total Return %"].iloc[-1]

    print(f"\nSummary Statistics:")
    print(f"  Average Return:   {avg_return:.2f}%")
    print(f"  Best:             {best_ticker} ({best_return:.2f}%)")
    print(f"  Worst:            {worst_ticker} ({worst_return:.2f}%)")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--ticker" and len(sys.argv) > 2:
            # Analyze specific ticker
            analyze_ticker_detailed(sys.argv[2])
        elif sys.argv[1] == "--test-params" and len(sys.argv) > 3:
            # Test specific parameters
            lookback = int(sys.argv[2])
            z_thresh = float(sys.argv[3])
            test_parameters(lookback, z_thresh)
        else:
            print("Usage:")
            print("  python analyze_stddev.py --ticker <TICKER>")
            print("    Example: python analyze_stddev.py --ticker VGT")
            print()
            print("  python analyze_stddev.py --test-params <LOOKBACK> <Z_THRESHOLD>")
            print("    Example: python analyze_stddev.py --test-params 20 1.5")
            print()
            print(f"Available tickers: {', '.join(SECTOR_ETFS.keys())}")
    else:
        print("Usage:")
        print("  python analyze_stddev.py --ticker <TICKER>")
        print("    Example: python analyze_stddev.py --ticker VGT")
        print()
        print("  python analyze_stddev.py --test-params <LOOKBACK> <Z_THRESHOLD>")
        print("    Example: python analyze_stddev.py --test-params 20 1.5")
        print()
        print(f"Available tickers: {', '.join(SECTOR_ETFS.keys())}")
