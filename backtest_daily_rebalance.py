"""
Ultra-Simple Daily Rebalancing Strategy

Every day at close:
- If sector is DOWN X%, BUY proportional amount
- If sector is UP X% (and we have position), SELL proportional amount

Example: If ROM drops 2%, buy $20 of ROM
         If ROM gains 2% from previous close, sell $20 or max available

This is pure daily mean reversion with minimal logic.
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
    daily_return: float  # Daily return that triggered trade


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


class DailyRebalanceBacktester:
    """
    Ultra-simple daily rebalancing strategy.

    Rules:
    - Track daily price change for each sector
    - If sector DOWN: buy proportional to drop
    - If sector UP: sell proportional to gain
    - Position sizing: $X per 1% move
    """

    def __init__(
        self,
        prices_df: pd.DataFrame,  # columns=tickers, index=dates
        initial_capital: float = 10000,
        trade_amount_per_percent: float = 200,  # Buy/sell $200 per 1% move
    ):
        """
        Initialize daily rebalance backtester.

        Args:
            prices_df: Historical prices (columns=tickers, index=dates)
            initial_capital: Total starting capital
            trade_amount_per_percent: $ to trade per 1% daily move
        """
        self.prices_df = prices_df
        self.tickers = sorted(prices_df.columns.tolist())
        self.initial_capital = initial_capital
        self.trade_amount_per_percent = trade_amount_per_percent

        # Portfolio state
        self.positions = {ticker: 0.0 for ticker in self.tickers}
        self.cash = initial_capital
        self.trades = []
        self.snapshots = []

        # Sector tracking
        self.sector_trades = {ticker: [] for ticker in self.tickers}

    def run(self) -> BacktestResults:
        """Execute portfolio backtest."""
        prev_prices = {ticker: None for ticker in self.tickers}

        for i, date in enumerate(self.prices_df.index):
            # Calculate daily returns and execute trades
            for ticker in self.tickers:
                current_price = self.prices_df.loc[date, ticker]

                if pd.isna(current_price):
                    continue

                # Calculate daily return from previous close
                if prev_prices[ticker] is not None:
                    daily_return_pct = (current_price - prev_prices[ticker]) / prev_prices[ticker]
                    daily_return_pct_val = daily_return_pct * 100

                    # BUY signal: sector is DOWN
                    if daily_return_pct < 0:
                        # Buy $X per 1% drop
                        trade_value = abs(daily_return_pct_val) * self.trade_amount_per_percent
                        trade_value = min(trade_value, self.cash * 0.25)  # Max 25% in one trade

                        if trade_value > 10:  # Only trade if meaningful
                            qty = trade_value / current_price
                            self.positions[ticker] += qty
                            self.cash -= trade_value

                            trade = TradeRecord(
                                date=date,
                                ticker=ticker,
                                action="BUY",
                                price=current_price,
                                quantity=qty,
                                value=trade_value,
                                daily_return=daily_return_pct_val,
                            )
                            self.trades.append(trade)
                            self.sector_trades[ticker].append(trade)

                    # SELL signal: sector is UP and we have position
                    elif daily_return_pct > 0 and self.positions[ticker] > 0:
                        # Sell $X per 1% gain
                        trade_value = daily_return_pct_val * self.trade_amount_per_percent
                        max_sell_value = self.positions[ticker] * current_price
                        trade_value = min(trade_value, max_sell_value)

                        if trade_value > 10:  # Only trade if meaningful
                            qty = trade_value / current_price
                            self.positions[ticker] -= qty
                            self.cash += trade_value

                            trade = TradeRecord(
                                date=date,
                                ticker=ticker,
                                action="SELL",
                                price=current_price,
                                quantity=qty,
                                value=trade_value,
                                daily_return=daily_return_pct_val,
                            )
                            self.trades.append(trade)
                            self.sector_trades[ticker].append(trade)

                # Update previous price for next iteration
                prev_prices[ticker] = current_price

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
            num_positions = sum(1 for p in self.positions.values() if p > 0.001)

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
            if self.positions[ticker] > 0.001 and len(buy_trades) > 0:
                current_price = self.prices_df[ticker].iloc[-1]
                # Calculate average buy price
                total_shares_bought = sum(t.quantity for t in buy_trades)
                if total_shares_bought > 0:
                    avg_buy_price = sum(t.value for t in buy_trades) / total_shares_bought
                    unrealized_pnl = (current_price - avg_buy_price) * self.positions[ticker]
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
