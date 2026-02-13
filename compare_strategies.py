"""
Compare Standard Deviation Trading Strategy vs Buy-and-Hold Strategy

Backtests both strategies on VOO (Vanguard S&P 500 ETF) and outputs
detailed results to CSV for analysis.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from sector_etfs import _yahoo_chart
from stddev_backtest import StddevBacktester


class BuyAndHoldBacktester:
    """Simple buy-and-hold strategy for comparison."""

    def __init__(self, ticker: str, prices: pd.Series, initial_capital: float = 10000):
        """
        Initialize buy-and-hold backtester.

        Args:
            ticker: Stock/ETF ticker symbol
            prices: Historical closing prices (pd.Series with DatetimeIndex)
            initial_capital: Starting capital
        """
        self.ticker = ticker
        self.prices = prices.dropna()
        self.initial_capital = initial_capital
        self.shares = 0
        self.cash = initial_capital
        self.daily_values = []
        self.buy_price = None
        self.buy_date = None

    def run(self):
        """Execute buy-and-hold strategy."""
        # Buy on first day
        first_price = self.prices.iloc[0]
        self.shares = self.initial_capital / first_price
        self.cash = 0
        self.buy_price = first_price
        self.buy_date = self.prices.index[0]

        # Track daily portfolio values
        for price in self.prices:
            portfolio_value = self.shares * price
            self.daily_values.append(portfolio_value)

        return self._compute_results()

    def _compute_results(self):
        """Compute performance metrics."""
        final_value = self.shares * self.prices.iloc[-1]
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100

        # Max drawdown
        cumulative_values = np.array(self.daily_values)
        running_max = np.maximum.accumulate(cumulative_values)
        drawdown = (cumulative_values - running_max) / running_max * 100
        max_drawdown = drawdown.min()

        # Sharpe ratio (annualized)
        daily_pnl = np.array(self.daily_values) - self.initial_capital
        daily_returns = np.diff(daily_pnl) / self.initial_capital
        sharpe_ratio = (
            np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
            if len(daily_returns) > 1 and np.std(daily_returns) > 0
            else 0
        )

        return {
            "ticker": self.ticker,
            "strategy": "Buy & Hold",
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
            "win_rate": None,  # Not applicable for buy & hold
            "num_trades": 1,  # One trade (buy)
            "final_pnl": final_value - self.initial_capital,
            "buy_price": self.buy_price,
            "sell_price": self.prices.iloc[-1],
            "shares_held": self.shares,
        }


def fetch_ticker_data(ticker: str, range_: str = "2y") -> pd.Series:
    """Fetch closing prices for a specific ticker."""
    rows = _yahoo_chart(ticker, range_=range_)
    df = pd.DataFrame(rows).set_index("date")
    return df["close"]


def compare_strategies(ticker: str, range_: str = "2y", lookback: int = 20, z_threshold: float = 1.0):
    """Compare stddev strategy vs buy-and-hold."""
    print(f"Fetching {ticker} data for range={range_}...")
    prices = fetch_ticker_data(ticker, range_=range_)

    print(f"Running Standard Deviation strategy...")
    stddev_backtester = StddevBacktester(
        ticker=ticker,
        prices=prices,
        lookback_period=lookback,
        z_threshold=z_threshold,
        initial_capital=10000,
    )
    stddev_results = stddev_backtester.run()

    print(f"Running Buy & Hold strategy...")
    bah_backtester = BuyAndHoldBacktester(ticker=ticker, prices=prices, initial_capital=10000)
    bah_results = bah_backtester.run()

    # Convert results to comparable format
    results = []

    # StdDev strategy
    results.append(
        {
            "Ticker": ticker,
            "Strategy": "StdDev (z=1.0, lookback=20)",
            "Total Return %": stddev_results.total_return,
            "Max Drawdown %": stddev_results.max_drawdown,
            "Sharpe Ratio": stddev_results.sharpe_ratio,
            "Win Rate %": stddev_results.win_rate,
            "Num Trades": stddev_results.num_trades,
            "Final P&L": stddev_results.final_pnl,
            "Final Shares": stddev_results.final_shares,
        }
    )

    # Buy & Hold strategy
    results.append(
        {
            "Ticker": ticker,
            "Strategy": "Buy & Hold",
            "Total Return %": bah_results["total_return"],
            "Max Drawdown %": bah_results["max_drawdown"],
            "Sharpe Ratio": bah_results["sharpe_ratio"],
            "Win Rate %": "N/A",
            "Num Trades": bah_results["num_trades"],
            "Final P&L": bah_results["final_pnl"],
            "Final Shares": bah_results["shares_held"],
        }
    )

    return pd.DataFrame(results)


def compare_multiple_tickers(tickers: list, range_: str = "2y"):
    """Compare strategies across multiple tickers."""
    all_results = []

    for ticker in tickers:
        print(f"\n{'=' * 70}")
        print(f"Comparing strategies for {ticker}")
        print('=' * 70)
        try:
            results_df = compare_strategies(ticker, range_=range_)
            all_results.append(results_df)
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

    if all_results:
        return pd.concat(all_results, ignore_index=True)
    return pd.DataFrame()


if __name__ == "__main__":
    # Compare on VOO (S&P 500) and a few sector ETFs
    tickers_to_compare = ["VOO", "VGT", "VDE", "VDC"]

    print("=" * 70)
    print("Strategy Comparison: Standard Deviation vs Buy & Hold")
    print("=" * 70)

    comparison_df = compare_multiple_tickers(tickers_to_compare, range_="2y")

    # Save to CSV
    output_file = "strategy_comparison.csv"
    comparison_df.to_csv(output_file, index=False)
    print(f"\n{'=' * 70}")
    print(f"Results saved to {output_file}")
    print('=' * 70)

    # Display results
    print("\nComparison Results:")
    print(comparison_df.to_string(index=False))

    # Summary statistics
    print("\n" + "=" * 70)
    print("Summary by Strategy")
    print("=" * 70)
    summary = comparison_df.groupby("Strategy").agg(
        {
            "Total Return %": ["mean", "min", "max"],
            "Sharpe Ratio": "mean",
            "Max Drawdown %": "mean",
        }
    )
    print(summary)
