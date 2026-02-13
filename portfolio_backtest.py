"""
Portfolio-level backtester that manages a shared capital pool across sectors.

Compares two approaches:
1. EQUAL ALLOCATION: Divide capital equally among sectors ($909 each for $10k portfolio)
2. DYNAMIC ALLOCATION: Share one $10k pool - each sector buys as long as cash available
"""

import pandas as pd
import numpy as np
from sector_etfs import fetch_sector_closes, SECTOR_ETFS
from dataclasses import dataclass
from typing import Optional


@dataclass
class PortfolioSnapshot:
    """Daily portfolio state."""
    date: pd.Timestamp
    total_value: float
    cash: float
    invested_value: float
    num_positions: int
    returns_pct: float


class PortfolioBacktester:
    """Portfolio-level backtester with shared capital pool."""

    def __init__(
        self,
        prices_df: pd.DataFrame,  # DataFrame with columns as tickers, rows as dates
        initial_capital: float = 10000,
        lookback_period: int = 20,
        z_threshold: float = 1.0,
        allocation_method: str = "dynamic",  # "equal" or "dynamic"
    ):
        """
        Initialize portfolio backtester.

        Args:
            prices_df: DataFrame with ticker prices (columns=tickers, index=dates)
            initial_capital: Total starting capital
            lookback_period: Period for rolling std dev
            z_threshold: Z-score threshold for signals
            allocation_method: "equal" (divide equally) or "dynamic" (shared pool)
        """
        self.prices_df = prices_df
        self.tickers = prices_df.columns.tolist()
        self.initial_capital = initial_capital
        self.lookback_period = lookback_period
        self.z_threshold = z_threshold
        self.allocation_method = allocation_method

        # Per-ticker rolling stats
        self.rolling_means = {}
        self.rolling_stds = {}
        for ticker in self.tickers:
            self.rolling_means[ticker] = prices_df[ticker].rolling(lookback_period).mean()
            self.rolling_stds[ticker] = prices_df[ticker].rolling(lookback_period).std()

        # Portfolio state
        self.positions = {ticker: 0.0 for ticker in self.tickers}  # shares held
        self.cash = initial_capital
        self.snapshots = []
        self.trades = []

        # Allocation
        if allocation_method == "equal":
            self.per_sector_capital = initial_capital / len(self.tickers)
        else:
            self.per_sector_capital = None  # Dynamically allocated

    def _compute_z_score(self, price: float, mean: float, std: float) -> Optional[float]:
        """Compute z-score."""
        if pd.isna(mean) or pd.isna(std) or std == 0:
            return None
        return (price - mean) / std

    def _get_position_size(self, z_score: float, available_cash: float) -> float:
        """Position size proportional to z-score."""
        if z_score == 0:
            return 0
        abs_z = abs(z_score)
        position_ratio = min(abs_z / self.z_threshold, 1.0)
        return available_cash * position_ratio

    def run(self) -> list[PortfolioSnapshot]:
        """Execute portfolio backtest."""
        for date in self.prices_df.index:
            # Process each ticker
            for ticker in self.tickers:
                price = self.prices_df.loc[date, ticker]
                mean = self.rolling_means[ticker].loc[date]
                std = self.rolling_stds[ticker].loc[date]

                if pd.isna(price) or pd.isna(mean) or pd.isna(std):
                    continue

                z_score = self._compute_z_score(price, mean, std)
                if z_score is None:
                    continue

                # Determine available capital for this position
                if self.allocation_method == "equal":
                    # Fixed allocation per sector
                    available_cash = self.per_sector_capital
                else:
                    # Dynamic: share the pool, but max per sector is 30% to avoid concentration
                    available_cash = min(self.cash, self.initial_capital * 0.30)

                # BUY signal
                if self.positions[ticker] == 0 and z_score <= -self.z_threshold:
                    position_value = self._get_position_size(z_score, available_cash)
                    if position_value > 0:
                        qty = position_value / price
                        self.positions[ticker] = qty
                        self.cash -= position_value
                        self.trades.append({
                            "date": date,
                            "ticker": ticker,
                            "action": "BUY",
                            "price": price,
                            "qty": qty,
                            "value": position_value,
                            "z_score": z_score,
                        })

                # SELL signal
                elif self.positions[ticker] > 0 and z_score >= self.z_threshold:
                    sale_value = self.positions[ticker] * price
                    self.cash += sale_value
                    self.trades.append({
                        "date": date,
                        "ticker": ticker,
                        "action": "SELL",
                        "price": price,
                        "qty": self.positions[ticker],
                        "value": sale_value,
                        "z_score": z_score,
                    })
                    self.positions[ticker] = 0

            # Snapshot daily state
            invested_value = sum(self.positions[t] * self.prices_df.loc[date, t] for t in self.tickers)
            total_value = self.cash + invested_value
            returns_pct = ((total_value - self.initial_capital) / self.initial_capital) * 100

            self.snapshots.append(
                PortfolioSnapshot(
                    date=date,
                    total_value=total_value,
                    cash=self.cash,
                    invested_value=invested_value,
                    num_positions=sum(1 for p in self.positions.values() if p > 0),
                    returns_pct=returns_pct,
                )
            )

        return self.snapshots

    def get_summary(self) -> dict:
        """Compute portfolio performance metrics."""
        if not self.snapshots:
            return {}

        total_values = [s.total_value for s in self.snapshots]
        final_value = total_values[-1]
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100

        # Max drawdown
        running_max = np.maximum.accumulate(total_values)
        drawdown = (np.array(total_values) - running_max) / running_max * 100
        max_drawdown = drawdown.min()

        # Daily returns for Sharpe
        daily_returns = np.diff(total_values) / self.initial_capital
        sharpe = (
            np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
            if len(daily_returns) > 1 and np.std(daily_returns) > 0
            else 0
        )

        # Capital efficiency
        invested_pcts = [s.invested_value / s.total_value if s.total_value > 0 else 0 for s in self.snapshots]
        avg_invested_pct = np.mean(invested_pcts) * 100
        avg_cash_pct = 100 - avg_invested_pct

        return {
            "method": self.allocation_method,
            "final_value": final_value,
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe,
            "num_trades": len(self.trades),
            "avg_invested_pct": avg_invested_pct,
            "avg_cash_pct": avg_cash_pct,
            "max_cash": max([s.cash for s in self.snapshots]),
            "min_cash": min([s.cash for s in self.snapshots]),
        }


def compare_allocation_methods(range_: str = "2y"):
    """Compare equal vs dynamic allocation on full portfolio."""
    print("Fetching sector ETF prices...")
    closes = fetch_sector_closes(range_=range_)

    print("\n" + "=" * 90)
    print("EQUAL ALLOCATION: $909 per sector (11 sectors × $909 = $10,000)")
    print("=" * 90)

    bt_equal = PortfolioBacktester(
        prices_df=closes,
        initial_capital=10000,
        allocation_method="equal",
    )
    bt_equal.run()
    summary_equal = bt_equal.get_summary()

    print(f"\nFinal Portfolio Value:       ${summary_equal['final_value']:>10,.2f}")
    print(f"Total Return:                {summary_equal['total_return']:>10.2f}%")
    print(f"Max Drawdown:                {summary_equal['max_drawdown']:>10.2f}%")
    print(f"Sharpe Ratio:                {summary_equal['sharpe_ratio']:>10.2f}")
    print(f"Number of Trades:            {summary_equal['num_trades']:>10.0f}")
    print(f"Avg Capital Deployed:        {summary_equal['avg_invested_pct']:>10.2f}%")
    print(f"Avg Cash Sitting Idle:       {summary_equal['avg_cash_pct']:>10.2f}%")
    print(f"Max Cash During Period:      ${summary_equal['max_cash']:>10,.2f}")
    print(f"Min Cash During Period:      ${summary_equal['min_cash']:>10,.2f}")

    print("\n" + "=" * 90)
    print("DYNAMIC ALLOCATION: Shared $10k pool (max 30% per sector, buy as signal appears)")
    print("=" * 90)

    bt_dynamic = PortfolioBacktester(
        prices_df=closes,
        initial_capital=10000,
        allocation_method="dynamic",
    )
    bt_dynamic.run()
    summary_dynamic = bt_dynamic.get_summary()

    print(f"\nFinal Portfolio Value:       ${summary_dynamic['final_value']:>10,.2f}")
    print(f"Total Return:                {summary_dynamic['total_return']:>10.2f}%")
    print(f"Max Drawdown:                {summary_dynamic['max_drawdown']:>10.2f}%")
    print(f"Sharpe Ratio:                {summary_dynamic['sharpe_ratio']:>10.2f}")
    print(f"Number of Trades:            {summary_dynamic['num_trades']:>10.0f}")
    print(f"Avg Capital Deployed:        {summary_dynamic['avg_invested_pct']:>10.2f}%")
    print(f"Avg Cash Sitting Idle:       {summary_dynamic['avg_cash_pct']:>10.2f}%")
    print(f"Max Cash During Period:      ${summary_dynamic['max_cash']:>10,.2f}")
    print(f"Min Cash During Period:      ${summary_dynamic['min_cash']:>10,.2f}")

    print("\n" + "=" * 90)
    print("COMPARISON (Dynamic vs Equal)")
    print("=" * 90)

    print(f"\nReturn Advantage:            {summary_dynamic['total_return'] - summary_equal['total_return']:>10.2f}%")
    print(f"Drawdown Advantage:          {summary_dynamic['max_drawdown'] - summary_equal['max_drawdown']:>10.2f}%")
    print(f"Sharpe Advantage:            {summary_dynamic['sharpe_ratio'] - summary_equal['sharpe_ratio']:>10.2f}")
    print(f"Capital Deployed Advantage:  {summary_dynamic['avg_invested_pct'] - summary_equal['avg_invested_pct']:>10.2f}%")

    print("\n" + "=" * 90)
    print("INTERPRETATION")
    print("=" * 90)

    print("\nEQUAL ALLOCATION ($909/sector):")
    print("  ✓ Simple and fair - each sector gets equal capital")
    print("  ✓ Prevents concentration - protects against one sector tanking")
    print("  ✗ Underutilizes capital - wasteful if sectors trade infrequently")
    print("  ✗ Fixed allocation - can't capitalize on multiple simultaneous opportunities")

    print("\nDYNAMIC ALLOCATION (Shared pool):")
    print("  ✓ Better capital efficiency - deploys when signals appear")
    print("  ✓ Can take multiple positions - if VGT and VHT both signal, both can be funded")
    print("  ✗ Concentration risk - single sector could use 30% of portfolio")
    print("  ✗ More complex - requires position management rules")

    # Show what's actually happening
    print("\n" + "=" * 90)
    print("WHAT THE CURRENT SINGLE-SECTOR BACKTEST ASSUMES")
    print("=" * 90)
    print("\nYou're running 11 independent backtests, each with $10,000:")
    print(f"  VGT:  $10,000 → {11.66}% return")
    print(f"  VHT:  $10,000 → 12.49% return")
    print(f"  VFH:  $10,000 → 5.87% return")
    print(f"  ... (11 times)")
    print(f"\n  IMPLIED TOTAL CAPITAL: $110,000")
    print(f"  IMPLIED TOTAL RETURN: ~$15,400 (13% avg)")
    print("\n✗ This is UNREALISTIC - you don't have $110k, you have one portfolio!")
    print("\n→ Use the portfolio backtester above to see real performance with $10k total")

    return summary_equal, summary_dynamic


if __name__ == "__main__":
    compare_allocation_methods(range_="2y")
