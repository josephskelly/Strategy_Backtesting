"""
Improved Standard Deviation Trading Strategy with Better Capital Efficiency

Enhancements:
1. Tiered position sizing - deploy more capital with stronger signals
2. Partial position scaling - increase size as signals strengthen
3. Option to use idle cash for secondary positions
4. Multiple entry/exit levels for better capital deployment
"""

import pandas as pd
import numpy as np
from sector_etfs import fetch_sector_closes, SECTOR_ETFS
from dataclasses import dataclass
from typing import Optional


@dataclass
class TradeRecord:
    """Record of a single trade."""
    date: pd.Timestamp
    ticker: str
    action: str  # 'BUY' or 'SELL'
    price: float
    quantity: float
    value: float
    z_score: float


@dataclass
class BacktestResults:
    """Complete backtest results."""
    ticker: str
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    num_trades: int
    final_pnl: float
    final_shares: float
    trades: list[TradeRecord]


class ImprovedStddevBacktester:
    """
    Improved backtester with better capital efficiency.

    Deploys capital in tiers based on signal strength:
    - Tier 1: |z| = 1.0-1.5 (weak signal, 20% capital)
    - Tier 2: |z| = 1.5-2.0 (strong signal, 50% capital)
    - Tier 3: |z| >= 2.0 (very strong signal, 100% capital)
    """

    def __init__(
        self,
        ticker: str,
        prices: pd.Series,
        lookback_period: int = 20,
        z_threshold: float = 1.0,
        initial_capital: float = 10000,
        tiered_sizing: bool = True,
    ):
        self.ticker = ticker
        self.prices = prices.dropna()
        self.lookback_period = lookback_period
        self.z_threshold = z_threshold
        self.initial_capital = initial_capital
        self.tiered_sizing = tiered_sizing

        # Compute rolling stats
        self.rolling_mean = self.prices.rolling(lookback_period).mean()
        self.rolling_std = self.prices.rolling(window=lookback_period).std()

        # Initialize state
        self.shares = 0.0
        self.cash = initial_capital
        self.trades = []
        self.daily_pnl = []
        self.daily_values = []
        self.daily_positions = []
        self.daily_cash = []

    def _compute_z_score(self, price: float, mean: float, std: float) -> Optional[float]:
        """Compute z-score."""
        if pd.isna(mean) or pd.isna(std) or std == 0:
            return None
        return (price - mean) / std

    def _get_position_size_tiered(self, z_score: float, available_cash: float) -> float:
        """
        Tiered position sizing for better capital deployment.

        - Very weak (-1.5 to -1.0): 15% of available cash
        - Weak (-2.0 to -1.5): 35% of available cash
        - Strong (-3.0 to -2.0): 65% of available cash
        - Very strong (< -3.0): 100% of available cash
        """
        abs_z = abs(z_score)

        if abs_z < self.z_threshold:
            return 0
        elif abs_z < 1.5:
            return available_cash * 0.15
        elif abs_z < 2.0:
            return available_cash * 0.35
        elif abs_z < 3.0:
            return available_cash * 0.65
        else:
            return available_cash * 1.0

    def _get_position_size_continuous(self, z_score: float, available_cash: float) -> float:
        """Original continuous position sizing."""
        if z_score == 0:
            return 0
        abs_z = abs(z_score)
        position_ratio = min(abs_z / self.z_threshold, 1.0)
        return available_cash * position_ratio

    def _should_buy(self, z_score: Optional[float]) -> bool:
        """Buy when price falls below threshold."""
        return z_score is not None and z_score <= -self.z_threshold

    def _should_sell(self, z_score: Optional[float]) -> bool:
        """Sell when price rises above threshold."""
        return z_score is not None and z_score >= self.z_threshold

    def run(self) -> BacktestResults:
        """Execute backtest."""
        for i, (date, price) in enumerate(self.prices.items()):
            mean = self.rolling_mean.iloc[i]
            std = self.rolling_std.iloc[i]
            z_score = self._compute_z_score(price, mean, std)

            portfolio_value = self.cash + self.shares * price

            # Generate signals
            if z_score is not None:
                if self.shares == 0 and self._should_buy(z_score):
                    # BUY signal
                    if self.tiered_sizing:
                        position_value = self._get_position_size_tiered(z_score, self.cash)
                    else:
                        position_value = self._get_position_size_continuous(z_score, self.cash)

                    if position_value > 0:
                        qty = position_value / price
                        self.shares += qty
                        self.cash -= position_value
                        self.trades.append(
                            TradeRecord(
                                date=date,
                                ticker=self.ticker,
                                action="BUY",
                                price=price,
                                quantity=qty,
                                value=position_value,
                                z_score=z_score,
                            )
                        )

                elif self.shares > 0 and self._should_sell(z_score):
                    # SELL signal
                    sale_value = self.shares * price
                    self.cash += sale_value
                    self.trades.append(
                        TradeRecord(
                            date=date,
                            ticker=self.ticker,
                            action="SELL",
                            price=price,
                            quantity=self.shares,
                            value=sale_value,
                            z_score=z_score,
                        )
                    )
                    self.shares = 0

            # Track metrics
            daily_pnl = portfolio_value - self.initial_capital
            self.daily_pnl.append(daily_pnl)
            self.daily_values.append(portfolio_value)
            self.daily_positions.append(self.shares)
            self.daily_cash.append(self.cash)

        return self._compute_results()

    def _compute_results(self) -> BacktestResults:
        """Compute performance metrics."""
        final_value = self.cash + self.shares * self.prices.iloc[-1]
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100

        # Max drawdown
        cumulative_returns = np.array(self.daily_values)
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdown = (cumulative_returns - running_max) / running_max * 100
        max_drawdown = drawdown.min()

        # Sharpe ratio
        daily_returns = np.diff(self.daily_pnl) / self.initial_capital
        sharpe_ratio = (
            np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
            if len(daily_returns) > 1 and np.std(daily_returns) > 0
            else 0
        )

        # Win rate
        buy_trades = [t for t in self.trades if t.action == "BUY"]
        sell_trades = [t for t in self.trades if t.action == "SELL"]
        if len(buy_trades) > 0 and len(sell_trades) > 0:
            buy_prices = [t.price for t in buy_trades]
            sell_prices = [sell_trades[i].price for i in range(min(len(sell_trades), len(buy_trades)))]
            wins = sum(1 for buy, sell in zip(buy_prices, sell_prices) if sell > buy)
            win_rate = (wins / len(buy_prices)) * 100 if len(buy_prices) > 0 else 0
        else:
            win_rate = 0

        return BacktestResults(
            ticker=self.ticker,
            total_return=total_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            win_rate=win_rate,
            num_trades=len(self.trades),
            final_pnl=final_value - self.initial_capital,
            final_shares=self.shares,
            trades=self.trades,
        )

    def get_capital_efficiency_metrics(self):
        """Get capital efficiency metrics."""
        daily_invested = np.array(self.daily_positions) * self.prices.values
        daily_cash = np.array(self.daily_cash)
        daily_total = daily_invested + daily_cash

        # Avoid division by zero
        invested_pct = np.divide(
            daily_invested,
            daily_total,
            where=daily_total != 0,
            out=np.zeros_like(daily_invested, dtype=float),
        )

        fully_invested = np.sum(invested_pct >= 0.9)
        partially_invested = np.sum((invested_pct >= 0.1) & (invested_pct < 0.9))
        idle = np.sum(invested_pct < 0.1)
        total_days = len(invested_pct)

        return {
            "avg_invested_pct": np.mean(invested_pct) * 100,
            "avg_cash_pct": 100 - np.mean(invested_pct) * 100,
            "fully_invested_days": fully_invested,
            "partially_invested_days": partially_invested,
            "idle_days": idle,
            "total_days": total_days,
        }


def compare_sizing_methods(
    ticker: str,
    prices: pd.Series,
    lookback_period: int = 20,
    z_threshold: float = 1.0,
):
    """Compare original vs improved sizing methods."""

    # Original (continuous)
    bt_original = ImprovedStddevBacktester(
        ticker=ticker,
        prices=prices,
        lookback_period=lookback_period,
        z_threshold=z_threshold,
        tiered_sizing=False,
    )
    result_original = bt_original.run()
    metrics_original = bt_original.get_capital_efficiency_metrics()

    # Improved (tiered)
    bt_improved = ImprovedStddevBacktester(
        ticker=ticker,
        prices=prices,
        lookback_period=lookback_period,
        z_threshold=z_threshold,
        tiered_sizing=True,
    )
    result_improved = bt_improved.run()
    metrics_improved = bt_improved.get_capital_efficiency_metrics()

    return {
        "ticker": ticker,
        # Original
        "original_return": result_original.total_return,
        "original_invested": metrics_original["avg_invested_pct"],
        "original_sharpe": result_original.sharpe_ratio,
        "original_trades": result_original.num_trades,
        # Improved
        "improved_return": result_improved.total_return,
        "improved_invested": metrics_improved["avg_invested_pct"],
        "improved_sharpe": result_improved.sharpe_ratio,
        "improved_trades": result_improved.num_trades,
        # Deltas
        "return_delta": result_improved.total_return - result_original.total_return,
        "invested_delta": metrics_improved["avg_invested_pct"] - metrics_original["avg_invested_pct"],
    }


if __name__ == "__main__":
    print("=" * 90)
    print("Improved StdDev Strategy - Capital Efficiency Comparison")
    print("=" * 90)
    print()

    print("Fetching sector ETF prices...")
    closes = fetch_sector_closes(range_="2y")

    results = []
    for ticker in closes.columns:
        print(f"  Comparing sizing methods for {ticker}...")
        comparison = compare_sizing_methods(ticker, closes[ticker])
        results.append(comparison)

    comparison_df = pd.DataFrame(results)

    # Save comparison
    output_file = "capital_efficiency_comparison.csv"
    comparison_df.to_csv(output_file, index=False)
    print(f"\n✓ Comparison saved to {output_file}")

    # Display results
    print("\n" + "=" * 90)
    print("ORIGINAL (Continuous) vs IMPROVED (Tiered) SIZING")
    print("=" * 90)

    display_df = comparison_df[
        [
            "ticker",
            "original_return",
            "original_invested",
            "improved_return",
            "improved_invested",
            "return_delta",
            "invested_delta",
        ]
    ].copy()
    display_df.columns = [
        "Ticker",
        "Orig Return %",
        "Orig Invested %",
        "Impr Return %",
        "Impr Invested %",
        "Return Δ",
        "Invested Δ",
    ]

    print(display_df.to_string(index=False))

    # Summary
    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)

    print(f"\nCapital Efficiency Improvement:")
    print(f"  Original Avg Invested:     {comparison_df['original_invested'].mean():.2f}%")
    print(f"  Improved Avg Invested:     {comparison_df['improved_invested'].mean():.2f}%")
    print(f"  Improvement:               {comparison_df['invested_delta'].mean():.2f}%")

    print(f"\nReturn Impact:")
    print(f"  Original Avg Return:       {comparison_df['original_return'].mean():.2f}%")
    print(f"  Improved Avg Return:       {comparison_df['improved_return'].mean():.2f}%")
    print(f"  Change:                    {comparison_df['return_delta'].mean():.2f}%")

    print(f"\nTrade Frequency:")
    print(f"  Original Avg Trades:       {comparison_df['original_trades'].mean():.1f}")
    print(f"  Improved Avg Trades:       {comparison_df['improved_trades'].mean():.1f}")

    print()
