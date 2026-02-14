"""
Simple Buy-the-Dips, Sell-the-Bounces Strategy

Strategy:
- Track rolling high for each sector (lookback_period)
- BUY when price drops X% below that high
- SELL when price recovers X% from buy price (break even on the drawdown)

Much simpler than z-score based mean reversion.
"""

import pandas as pd
import numpy as np
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
    reason: str  # Why the trade happened


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


class DipsBouncesBacktester:
    """
    Simple buy-dips, sell-bounces backtester.

    Rules:
    - Track rolling high over lookback_period
    - BUY when price drops dip_threshold% below rolling high
    - SELL when price bounces back by dip_threshold% from buy price
    - Position sizing: allocate capital proportional to distance from high
    """

    def __init__(
        self,
        prices_df: pd.DataFrame,  # columns=tickers, index=dates
        initial_capital: float = 10000,
        lookback_period: int = 20,
        dip_threshold: float = 0.05,  # 5% dip to trigger buy
        max_sector_allocation: float = 0.30,
    ):
        """
        Initialize dips/bounces backtester.

        Args:
            prices_df: Historical prices (columns=tickers, index=dates)
            initial_capital: Total starting capital
            lookback_period: Days for rolling high
            dip_threshold: Buy when price drops this % below rolling high
            max_sector_allocation: Max % of portfolio per sector
        """
        self.prices_df = prices_df
        self.tickers = sorted(prices_df.columns.tolist())
        self.initial_capital = initial_capital
        self.lookback_period = lookback_period
        self.dip_threshold = dip_threshold
        self.max_sector_allocation = max_sector_allocation

        # Compute rolling highs
        self.rolling_highs = {}
        for ticker in self.tickers:
            self.rolling_highs[ticker] = prices_df[ticker].rolling(lookback_period).max()

        # Portfolio state
        self.positions = {ticker: 0.0 for ticker in self.tickers}
        self.buy_prices = {ticker: 0.0 for ticker in self.tickers}  # Track entry price
        self.cash = initial_capital
        self.trades = []
        self.snapshots = []

        # Sector tracking
        self.sector_trades = {ticker: [] for ticker in self.tickers}

    def _get_dip_percentage(self, price: float, rolling_high: float) -> float:
        """Calculate how much the price has dipped from rolling high."""
        if rolling_high == 0 or pd.isna(rolling_high) or pd.isna(price):
            return 0
        return (rolling_high - price) / rolling_high

    def _get_position_size(self, dip_pct: float, available_cash: float) -> float:
        """
        Position size proportional to dip depth.

        At dip_threshold → 100% of available capital
        Larger dips → larger positions
        """
        if dip_pct <= 0:
            return 0

        # Scale position by how deep the dip is
        position_ratio = min(dip_pct / self.dip_threshold, 1.0)
        return available_cash * position_ratio

    def run(self) -> BacktestResults:
        """Execute portfolio backtest."""
        for i, date in enumerate(self.prices_df.index):
            # Process each ticker for this date
            for ticker in self.tickers:
                price = self.prices_df.loc[date, ticker]
                rolling_high = self.rolling_highs[ticker].loc[date]

                if pd.isna(price) or pd.isna(rolling_high):
                    continue

                dip_pct = self._get_dip_percentage(price, rolling_high)

                # BUY signal: price dropped dip_threshold% below rolling high
                if self.positions[ticker] == 0 and dip_pct >= self.dip_threshold:
                    # Calculate available capital
                    max_sector_value = self.initial_capital * self.max_sector_allocation
                    can_allocate = min(self.cash, max_sector_value)

                    if can_allocate > 0:
                        position_value = self._get_position_size(dip_pct, can_allocate)
                        if position_value > 100:  # Only trade if meaningful
                            qty = position_value / price
                            self.positions[ticker] = qty
                            self.buy_prices[ticker] = price
                            self.cash -= position_value

                            trade = TradeRecord(
                                date=date,
                                ticker=ticker,
                                action="BUY",
                                price=price,
                                quantity=qty,
                                value=position_value,
                                reason=f"Dip {dip_pct*100:.1f}% below {self.lookback_period}d high",
                            )
                            self.trades.append(trade)
                            self.sector_trades[ticker].append(trade)

                # SELL signal: price bounced back by dip_threshold% from buy price
                elif self.positions[ticker] > 0:
                    bounce_pct = (price - self.buy_prices[ticker]) / self.buy_prices[ticker]

                    # Sell when we recover the dip (break even on the drop)
                    if bounce_pct >= self.dip_threshold:
                        sale_value = self.positions[ticker] * price
                        self.cash += sale_value

                        trade = TradeRecord(
                            date=date,
                            ticker=ticker,
                            action="SELL",
                            price=price,
                            quantity=self.positions[ticker],
                            value=sale_value,
                            reason=f"Bounce +{bounce_pct*100:.1f}% from entry",
                        )
                        self.trades.append(trade)
                        self.sector_trades[ticker].append(trade)
                        self.positions[ticker] = 0
                        self.buy_prices[ticker] = 0

            # Snapshot daily state
            invested_value = 0
            position_values = {}
            for ticker in self.tickers:
                if not pd.isna(self.prices_df.loc[date, ticker]):
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
                "num_trades": len(buy_trades),
                "pnl": sector_pnl,
                "return_pct": sector_return,
                "num_wins": num_wins,
                "win_rate": (
                    (num_wins / len(buy_trades) * 100)
                    if len(buy_trades) > 0
                    else 0
                ),
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
