"""
Dynamic Rebalancing Strategy: Sell Winners to Buy Dips

When fully invested and a new signal appears, sell the best performer
to fund the dip. This keeps capital deployed and rotates gains into new opportunities.

Strategy Rules:
1. Buy on mean reversion signals (z-score <= -1.0)
2. Sell on mean reversion signals (z-score >= +1.0) OR when need cash for new signals
3. If portfolio is 95%+ invested and new buy signal appears:
   - Sell the position with highest unrealized gain
   - Use proceeds to buy the new dip
   - This prioritizes deploying capital over holding winners
"""

import pandas as pd
import numpy as np
from sector_etfs import fetch_sector_closes, SECTOR_ETFS
from dataclasses import dataclass, field
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
    reason: str = ""  # Why the trade happened


@dataclass
class PortfolioSnapshot:
    """Daily portfolio state."""
    date: pd.Timestamp
    total_value: float
    cash: float
    invested_value: float
    positions: dict = field(default_factory=dict)
    position_values: dict = field(default_factory=dict)
    num_positions: int = 0
    returns_pct: float = 0.0


@dataclass
class BacktestResults:
    """Complete portfolio backtest results."""
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    num_trades: int
    final_value: float
    final_pnl: float
    avg_invested_pct: float
    avg_cash_pct: float
    sector_performance: dict
    snapshots: list = field(default_factory=list)


class DynamicRebalancingBacktester:
    """
    Portfolio backtester with dynamic rebalancing.

    Sells best performers to fund dips when fully invested.
    Maximizes capital deployment and forces profit-taking.
    """

    def __init__(
        self,
        prices_df: pd.DataFrame,
        initial_capital: float = 10000,
        lookback_period: int = 20,
        z_threshold: float = 1.0,
        max_sector_allocation: float = 0.30,
        investment_threshold: float = 0.95,  # Sell winners when 95%+ invested
    ):
        """
        Initialize dynamic rebalancing backtester.

        Args:
            prices_df: Historical prices (columns=tickers, index=dates)
            initial_capital: Total starting capital
            lookback_period: Days for rolling mean/std
            z_threshold: Buy at -z_threshold, sell at +z_threshold
            max_sector_allocation: Max % of portfolio per sector
            investment_threshold: % invested before rebalancing triggers
        """
        self.prices_df = prices_df
        self.tickers = sorted(prices_df.columns.tolist())
        self.initial_capital = initial_capital
        self.lookback_period = lookback_period
        self.z_threshold = z_threshold
        self.max_sector_allocation = max_sector_allocation
        self.investment_threshold = investment_threshold

        # Compute rolling statistics
        self.rolling_means = {}
        self.rolling_stds = {}
        for ticker in self.tickers:
            self.rolling_means[ticker] = prices_df[ticker].rolling(lookback_period).mean()
            self.rolling_stds[ticker] = prices_df[ticker].rolling(lookback_period).std()

        # Portfolio state
        self.positions = {ticker: 0.0 for ticker in self.tickers}
        self.entry_prices = {ticker: 0.0 for ticker in self.tickers}  # Track entry price for P&L
        self.cash = initial_capital
        self.trades = []
        self.snapshots = []
        self.sector_trades = {ticker: [] for ticker in self.tickers}

    def _compute_z_score(self, price: float, mean: float, std: float) -> Optional[float]:
        """Compute z-score."""
        if pd.isna(price) or pd.isna(mean) or pd.isna(std) or std == 0:
            return None
        return (price - mean) / std

    def _get_position_size(self, z_score: float, available_cash: float) -> float:
        """Position size proportional to z-score (linear scaling)."""
        if z_score == 0:
            return 0
        abs_z = abs(z_score)
        position_ratio = min(abs_z / self.z_threshold, 1.0)
        return available_cash * position_ratio

    def _get_available_capital(self, ticker: str) -> float:
        """Calculate available capital for a sector."""
        max_sector_value = self.initial_capital * self.max_sector_allocation
        current_sector_value = self.positions[ticker] * self.prices_df[ticker].iloc[-1]
        can_add = max(0, max_sector_value - current_sector_value)
        return min(self.cash, can_add)

    def _get_invested_ratio(self) -> float:
        """Get percentage of portfolio currently invested."""
        total_value = sum(
            self.positions[t] * self.prices_df[t].iloc[-1]
            for t in self.tickers
        ) + self.cash
        invested = total_value - self.cash
        return invested / total_value if total_value > 0 else 0

    def _get_best_performer(self, current_date) -> Optional[tuple]:
        """
        Find position with highest unrealized gain.
        Returns (ticker, unrealized_pnl, unrealized_pct)
        """
        best_ticker = None
        best_pnl = -float('inf')

        for ticker in self.tickers:
            if self.positions[ticker] > 0:
                current_price = self.prices_df[ticker].loc[current_date]
                entry_price = self.entry_prices[ticker]
                unrealized_pnl = (current_price - entry_price) * self.positions[ticker]

                if unrealized_pnl > best_pnl:
                    best_pnl = unrealized_pnl
                    best_ticker = ticker

        if best_ticker is None:
            return None

        current_price = self.prices_df[best_ticker].loc[current_date]
        entry_price = self.entry_prices[best_ticker]
        unrealized_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

        return (best_ticker, best_pnl, unrealized_pct)

    def run(self) -> BacktestResults:
        """Execute dynamic rebalancing backtest."""
        for i, date in enumerate(self.prices_df.index):
            # Track buy signals for this date (to prioritize rebalancing)
            buy_signals = []

            # Process each ticker for this date
            for ticker in self.tickers:
                price = self.prices_df.loc[date, ticker]
                mean = self.rolling_means[ticker].loc[date]
                std = self.rolling_stds[ticker].loc[date]

                if pd.isna(price) or pd.isna(mean) or pd.isna(std):
                    continue

                z_score = self._compute_z_score(price, mean, std)
                if z_score is None:
                    continue

                # Check for buy signal
                if self.positions[ticker] == 0 and z_score <= -self.z_threshold:
                    buy_signals.append((ticker, z_score, price))

                # Check for normal sell signal (mean reversion)
                elif self.positions[ticker] > 0 and z_score >= self.z_threshold:
                    sale_value = self.positions[ticker] * price
                    self.cash += sale_value

                    trade = TradeRecord(
                        date=date,
                        ticker=ticker,
                        action="SELL",
                        price=price,
                        quantity=self.positions[ticker],
                        value=sale_value,
                        z_score=z_score,
                        reason="Mean reversion signal (z >= +1.0)",
                    )
                    self.trades.append(trade)
                    self.sector_trades[ticker].append(trade)
                    self.positions[ticker] = 0
                    self.entry_prices[ticker] = 0

            # Process buy signals with potential rebalancing
            for ticker, z_score, price in buy_signals:
                available_capital = self._get_available_capital(ticker)

                # If we have cash available, just buy
                if available_capital > 0:
                    position_value = self._get_position_size(z_score, available_capital)
                    if position_value > 0:
                        qty = position_value / price
                        self.positions[ticker] = qty
                        self.entry_prices[ticker] = price
                        self.cash -= position_value

                        trade = TradeRecord(
                            date=date,
                            ticker=ticker,
                            action="BUY",
                            price=price,
                            quantity=qty,
                            value=position_value,
                            z_score=z_score,
                            reason="Mean reversion signal (z <= -1.0)",
                        )
                        self.trades.append(trade)
                        self.sector_trades[ticker].append(trade)

                # If no cash and portfolio is highly invested, sell best performer
                elif self._get_invested_ratio() >= self.investment_threshold:
                    best = self._get_best_performer(date)

                    if best:
                        best_ticker, best_pnl, best_pnl_pct = best

                        # Only rebalance if there's a meaningful gain (at least 1%)
                        if best_pnl_pct > 1.0:
                            sale_value = self.positions[best_ticker] * self.prices_df[best_ticker].loc[date]
                            sale_price = self.prices_df[best_ticker].loc[date]
                            self.cash += sale_value

                            trade = TradeRecord(
                                date=date,
                                ticker=best_ticker,
                                action="SELL",
                                price=sale_price,
                                quantity=self.positions[best_ticker],
                                value=sale_value,
                                z_score=0,
                                reason=f"Rebalancing: selling winner (+{best_pnl_pct:.1f}%) for new dip",
                            )
                            self.trades.append(trade)
                            self.sector_trades[best_ticker].append(trade)
                            self.positions[best_ticker] = 0
                            self.entry_prices[best_ticker] = 0

                            # Now buy the new dip
                            available_capital = self._get_available_capital(ticker)
                            if available_capital > 0:
                                position_value = self._get_position_size(z_score, available_capital)
                                if position_value > 0:
                                    qty = position_value / price
                                    self.positions[ticker] = qty
                                    self.entry_prices[ticker] = price
                                    self.cash -= position_value

                                    trade = TradeRecord(
                                        date=date,
                                        ticker=ticker,
                                        action="BUY",
                                        price=price,
                                        quantity=qty,
                                        value=position_value,
                                        z_score=z_score,
                                        reason="Rebalancing: buying new dip with rebalanced capital",
                                    )
                                    self.trades.append(trade)
                                    self.sector_trades[ticker].append(trade)

            # Snapshot daily state
            invested_value = 0
            position_values = {}
            for ticker in self.tickers:
                pos_value = self.positions[ticker] * self.prices_df.loc[date, ticker]
                invested_value += pos_value
                position_values[ticker] = pos_value

            total_value = self.cash + invested_value
            returns_pct = ((total_value - self.initial_capital) / self.initial_capital) * 100
            num_positions = sum(1 for p in self.positions.values() if p > 0)

            self.snapshots.append(
                PortfolioSnapshot(
                    date=date,
                    total_value=total_value,
                    cash=self.cash,
                    invested_value=invested_value,
                    positions=self.positions.copy(),
                    position_values=position_values,
                    num_positions=num_positions,
                    returns_pct=returns_pct,
                )
            )

        return self._compute_results()

    def _compute_results(self) -> BacktestResults:
        """Compute portfolio performance metrics."""
        if not self.snapshots:
            return BacktestResults(0, 0, 0, 0, 0, 0, 0, 0, {})

        total_values = np.array([s.total_value for s in self.snapshots])
        final_value = total_values[-1]
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100
        final_pnl = final_value - self.initial_capital

        # Max drawdown
        running_max = np.maximum.accumulate(total_values)
        drawdowns = (total_values - running_max) / running_max * 100
        max_drawdown = drawdowns.min()

        # Sharpe ratio
        daily_returns = np.diff(total_values) / self.initial_capital
        if len(daily_returns) > 1 and np.std(daily_returns) > 0:
            sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
        else:
            sharpe_ratio = 0

        # Capital efficiency
        invested_pcts = [
            s.invested_value / s.total_value if s.total_value > 0 else 0
            for s in self.snapshots
        ]
        avg_invested_pct = np.mean(invested_pcts) * 100
        avg_cash_pct = 100 - avg_invested_pct

        # Sector performance
        sector_performance = {}
        for ticker in self.tickers:
            trades = self.sector_trades[ticker]
            buy_trades = [t for t in trades if t.action == "BUY"]
            sell_trades = [t for t in trades if t.action == "SELL"]

            # Calculate PnL from completed trades
            sector_pnl = 0.0
            for buy, sell in zip(buy_trades, sell_trades):
                pnl_per_share = sell.price - buy.price
                sector_pnl += pnl_per_share * buy.quantity

            # Add unrealized P&L if position still open
            if self.positions[ticker] > 0 and len(buy_trades) > 0:
                current_price = self.prices_df[ticker].iloc[-1]
                last_buy = buy_trades[-1]
                unrealized_pnl = (current_price - last_buy.price) * self.positions[ticker]
                sector_pnl += unrealized_pnl

            sector_return = (sector_pnl / self.initial_capital) * 100 if self.initial_capital > 0 else 0

            # Win rate calculation
            num_wins = 0
            for buy, sell in zip(buy_trades, sell_trades):
                if sell.price > buy.price:
                    num_wins += 1

            sector_performance[ticker] = {
                "num_trades": len(trades),
                "pnl": sector_pnl,
                "return_pct": sector_return,
                "num_wins": num_wins,
                "win_rate": (num_wins / len(buy_trades) * 100) if len(buy_trades) > 0 else 0,
            }

        return BacktestResults(
            total_return=total_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            num_trades=len(self.trades),
            final_value=final_value,
            final_pnl=final_pnl,
            avg_invested_pct=avg_invested_pct,
            avg_cash_pct=avg_cash_pct,
            sector_performance=sector_performance,
            snapshots=self.snapshots,
        )


def run_dynamic_rebalancing_backtest(range_: str = "2y"):
    """Run dynamic rebalancing backtest."""
    print("=" * 100)
    print("DYNAMIC REBALANCING STRATEGY: Sell Winners to Buy Dips")
    print("=" * 100)
    print()
    print("Configuration:")
    print(f"  Initial Capital:           $10,000")
    print(f"  Allocation Method:         Dynamic Shared Pool with Rebalancing")
    print(f"  Max Per Sector:            30% ($3,000)")
    print(f"  Lookback Period:           20 days")
    print(f"  Z-Score Threshold:         1.0 (buy at -1.0, sell at +1.0)")
    print(f"  Rebalancing Trigger:       95%+ invested")
    print(f"  Rebalancing Rule:          Sell best performer to buy new dips")
    print()

    print(f"Fetching sector ETF prices for range={range_}...")
    closes = fetch_sector_closes(range_=range_)

    print("Running dynamic rebalancing backtest...")
    backtester = DynamicRebalancingBacktester(
        prices_df=closes,
        initial_capital=10000,
        lookback_period=20,
        z_threshold=1.0,
        max_sector_allocation=0.30,
        investment_threshold=0.95,
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
    print("TRADE STATISTICS")
    print("=" * 100)

    # Analyze rebalancing trades
    rebalance_trades = [t for t in backtester.trades if "Rebalancing" in t.reason]
    normal_trades = [t for t in backtester.trades if "Rebalancing" not in t.reason]

    print(f"\nTotal Trades:                {len(backtester.trades)}")
    print(f"Normal Mean Reversion:       {len(normal_trades)}")
    print(f"Rebalancing Trades:          {len(rebalance_trades)}")
    print(f"Rebalancing Frequency:       {(len(rebalance_trades) / max(1, len(backtester.trades)) * 100):.1f}% of all trades")

    # Rebalancing effectiveness
    if rebalance_trades:
        rebalance_sell_gains = []
        for trade in rebalance_trades:
            if trade.action == "SELL" and "selling winner" in trade.reason:
                # Extract gain from reason string if possible
                rebalance_sell_gains.append(trade.value)

        if rebalance_sell_gains:
            print(f"\nRebalancing Effectiveness:")
            print(f"  - Avg gain locked in per rebalance: ${np.mean(rebalance_sell_gains):.2f}")
            print(f"  - Total gains locked in: ${sum(rebalance_sell_gains):.2f}")

    # Save results
    output_file = "dynamic_rebalancing_results.csv"
    sector_results.to_csv(output_file, index=False)
    print(f"\n✓ Results saved to {output_file}")

    print()

    return results, backtester


if __name__ == "__main__":
    results, backtester = run_dynamic_rebalancing_backtest(range_="2y")
