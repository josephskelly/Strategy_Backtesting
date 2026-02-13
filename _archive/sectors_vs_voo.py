"""
Comprehensive Comparison: 11 Sector StdDev Strategies vs Single VOO Buy & Hold

Tests standard deviation trading strategy across all 11 Vanguard sector ETFs
and compares aggregate performance to a simple VOO buy-and-hold baseline.
"""

import pandas as pd
import numpy as np
from sector_etfs import fetch_sector_closes, SECTOR_ETFS
from stddev_backtest import backtest_stddev_strategy
from compare_strategies import fetch_ticker_data, BuyAndHoldBacktester


def backtest_all_sectors(range_: str = "2y", initial_capital: float = 10000):
    """Backtest stddev strategy on all 11 sector ETFs."""
    print(f"Fetching sector ETF prices for range={range_}...")
    closes = fetch_sector_closes(range_=range_)

    results = []
    for ticker in closes.columns:
        print(f"  Backtesting {ticker} ({SECTOR_ETFS[ticker]})...")
        result = backtest_stddev_strategy(
            ticker=ticker,
            prices=closes[ticker],
            lookback_period=20,
            z_threshold=1.0,
            initial_capital=initial_capital,
        )
        results.append(
            {
                "Ticker": ticker,
                "Sector": SECTOR_ETFS[ticker],
                "Strategy": "StdDev (Sector)",
                "Total Return %": result.total_return,
                "Max Drawdown %": result.max_drawdown,
                "Sharpe Ratio": result.sharpe_ratio,
                "Win Rate %": result.win_rate,
                "Num Trades": result.num_trades,
                "Final P&L": result.final_pnl,
                "Final Shares": result.final_shares,
            }
        )

    return pd.DataFrame(results)


def backtest_voo_hold(range_: str = "2y", initial_capital: float = 10000):
    """Backtest buy-and-hold on VOO."""
    print(f"\nFetching VOO data for range={range_}...")
    prices = fetch_ticker_data("VOO", range_=range_)

    print(f"Backtesting VOO buy-and-hold...")
    bah = BuyAndHoldBacktester("VOO", prices, initial_capital=initial_capital)
    result = bah.run()

    return pd.DataFrame(
        [
            {
                "Ticker": "VOO",
                "Sector": "S&P 500 (Benchmark)",
                "Strategy": "Buy & Hold (VOO)",
                "Total Return %": result["total_return"],
                "Max Drawdown %": result["max_drawdown"],
                "Sharpe Ratio": result["sharpe_ratio"],
                "Win Rate %": "N/A",
                "Num Trades": result["num_trades"],
                "Final P&L": result["final_pnl"],
                "Final Shares": result["shares_held"],
            }
        ]
    )


def calculate_aggregate_metrics(sectors_df, initial_capital: float = 10000):
    """Calculate aggregate metrics for equal-weighted sector portfolio."""
    # Equal weight across all 11 sectors
    per_sector_capital = initial_capital / len(sectors_df)

    # Calculate total portfolio return as weighted average
    total_return = sectors_df["Total Return %"].mean()

    # Calculate average metrics
    avg_drawdown = sectors_df["Max Drawdown %"].mean()
    avg_sharpe = sectors_df["Sharpe Ratio"].mean()
    avg_win_rate = sectors_df["Win Rate %"].mean()
    total_trades = sectors_df["Num Trades"].sum()
    total_pnl = sectors_df["Final P&L"].sum() / len(sectors_df)  # Average P&L

    return {
        "Ticker": "Portfolio",
        "Sector": "11 Sectors (Equal Weight)",
        "Strategy": "StdDev (Portfolio)",
        "Total Return %": total_return,
        "Max Drawdown %": avg_drawdown,
        "Sharpe Ratio": avg_sharpe,
        "Win Rate %": avg_win_rate,
        "Num Trades": total_trades,
        "Final P&L": total_pnl,
        "Final Shares": "N/A",
    }


if __name__ == "__main__":
    print("=" * 90)
    print("11 Sector StdDev Strategies vs VOO Buy & Hold")
    print("=" * 90)
    print()

    # Run backtests
    sectors_df = backtest_all_sectors(range_="2y", initial_capital=10000)
    voo_df = backtest_voo_hold(range_="2y", initial_capital=10000)

    # Calculate portfolio metrics
    portfolio_metrics = calculate_aggregate_metrics(sectors_df)
    portfolio_df = pd.DataFrame([portfolio_metrics])

    # Combine all results
    all_results = pd.concat(
        [sectors_df, portfolio_df, voo_df], ignore_index=True
    )

    # Save detailed results
    output_file = "sectors_vs_voo_detailed.csv"
    all_results.to_csv(output_file, index=False)
    print(f"\n✓ Detailed results saved to {output_file}")

    # Create summary comparison
    summary_data = []

    # Sector portfolio aggregate
    summary_data.append(
        {
            "Strategy": "11 Sectors (StdDev, Equal Weight)",
            "Avg Return %": sectors_df["Total Return %"].mean(),
            "Best Sector": sectors_df.loc[sectors_df["Total Return %"].idxmax(), "Ticker"],
            "Best Return %": sectors_df["Total Return %"].max(),
            "Worst Sector": sectors_df.loc[sectors_df["Total Return %"].idxmin(), "Ticker"],
            "Worst Return %": sectors_df["Total Return %"].min(),
            "Avg Drawdown %": sectors_df["Max Drawdown %"].mean(),
            "Best Drawdown %": sectors_df["Max Drawdown %"].max(),
            "Avg Sharpe": sectors_df["Sharpe Ratio"].mean(),
            "Avg Win Rate %": sectors_df["Win Rate %"].mean(),
            "Total Trades": sectors_df["Num Trades"].sum(),
        }
    )

    # VOO comparison
    summary_data.append(
        {
            "Strategy": "VOO (Buy & Hold)",
            "Avg Return %": voo_df["Total Return %"].iloc[0],
            "Best Sector": "VOO",
            "Best Return %": voo_df["Total Return %"].iloc[0],
            "Worst Sector": "VOO",
            "Worst Return %": voo_df["Total Return %"].iloc[0],
            "Avg Drawdown %": voo_df["Max Drawdown %"].iloc[0],
            "Best Drawdown %": voo_df["Max Drawdown %"].iloc[0],
            "Avg Sharpe": voo_df["Sharpe Ratio"].iloc[0],
            "Avg Win Rate %": "N/A",
            "Total Trades": 1,
        }
    )

    summary_df = pd.DataFrame(summary_data)

    # Save summary
    summary_file = "sectors_vs_voo_summary.csv"
    summary_df.to_csv(summary_file, index=False)
    print(f"✓ Summary results saved to {summary_file}")

    # Display results
    print("\n" + "=" * 90)
    print("INDIVIDUAL SECTOR RESULTS (StdDev Strategy)")
    print("=" * 90)
    print(
        sectors_df[
            [
                "Ticker",
                "Sector",
                "Total Return %",
                "Max Drawdown %",
                "Sharpe Ratio",
                "Win Rate %",
                "Num Trades",
            ]
        ].to_string(index=False)
    )

    print("\n" + "=" * 90)
    print("PORTFOLIO AGGREGATE (11 Sectors, Equal Weight)")
    print("=" * 90)
    print(
        portfolio_df[
            [
                "Sector",
                "Total Return %",
                "Max Drawdown %",
                "Sharpe Ratio",
                "Win Rate %",
                "Num Trades",
            ]
        ].to_string(index=False)
    )

    print("\n" + "=" * 90)
    print("VOO BENCHMARK (Buy & Hold)")
    print("=" * 90)
    print(
        voo_df[
            ["Ticker", "Sector", "Total Return %", "Max Drawdown %", "Sharpe Ratio"]
        ].to_string(index=False)
    )

    print("\n" + "=" * 90)
    print("STRATEGY COMPARISON SUMMARY")
    print("=" * 90)
    print(summary_df.to_string(index=False))

    # Calculate performance differences
    print("\n" + "=" * 90)
    print("PERFORMANCE ANALYSIS")
    print("=" * 90)

    portfolio_return = sectors_df["Total Return %"].mean()
    voo_return = voo_df["Total Return %"].iloc[0]
    return_diff = portfolio_return - voo_return

    portfolio_drawdown = sectors_df["Max Drawdown %"].mean()
    voo_drawdown = voo_df["Max Drawdown %"].iloc[0]
    drawdown_diff = portfolio_drawdown - voo_drawdown

    portfolio_sharpe = sectors_df["Sharpe Ratio"].mean()
    voo_sharpe = voo_df["Sharpe Ratio"].iloc[0]
    sharpe_diff = portfolio_sharpe - voo_sharpe

    print(f"\nReturn Comparison:")
    print(f"  Sector Portfolio (StdDev):  {portfolio_return:>7.2f}%")
    print(f"  VOO (Buy & Hold):           {voo_return:>7.2f}%")
    print(f"  Difference:                 {return_diff:>7.2f}% {'(Sectors Win)' if return_diff > 0 else '(VOO Wins)'}")

    print(f"\nDrawdown Comparison:")
    print(f"  Sector Portfolio (StdDev):  {portfolio_drawdown:>7.2f}%")
    print(f"  VOO (Buy & Hold):           {voo_drawdown:>7.2f}%")
    print(f"  Difference:                 {drawdown_diff:>7.2f}% {'(Sectors Better)' if drawdown_diff > 0 else '(VOO Better)'}")

    print(f"\nSharpe Ratio Comparison:")
    print(f"  Sector Portfolio (StdDev):  {portfolio_sharpe:>7.3f}")
    print(f"  VOO (Buy & Hold):           {voo_sharpe:>7.3f}")
    print(f"  Difference:                 {sharpe_diff:>7.3f} {'(Sectors Win)' if sharpe_diff > 0 else '(VOO Wins)'}")

    print(f"\nTrading Activity:")
    print(f"  Sector Portfolio Trades:    {sectors_df['Num Trades'].sum()}")
    print(f"  VOO Trades:                 1")

    # Identify best and worst performers
    best_idx = sectors_df["Total Return %"].idxmax()
    worst_idx = sectors_df["Total Return %"].idxmin()

    print(f"\nBest Performing Sector:")
    print(f"  {sectors_df.loc[best_idx, 'Ticker']}: {sectors_df.loc[best_idx, 'Total Return %']:.2f}%")

    print(f"\nWorst Performing Sector:")
    print(f"  {sectors_df.loc[worst_idx, 'Ticker']}: {sectors_df.loc[worst_idx, 'Total Return %']:.2f}%")

    print()
