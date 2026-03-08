"""
Backtesting Engine

Core portfolio engine that runs any pluggable indicator.
Owns: portfolio state, trade execution, snapshots, results computation.
The indicator module owns: signal generation logic.

Indicator Protocol
------------------
Each indicator module must export:

    class Indicator:
        def __init__(self, **kwargs):
            '''Receives all parsed CLI args as keyword arguments.'''

        def signal(
            self,
            ticker: str,
            date,
            current_price: float,
            prev_price: float | None,
            prices_history: pd.Series,  # all prices up to (including) date
            position: float,            # shares currently held in this ticker
            cash: float,
            nlv: float,
        ) -> tuple[str, float]:
            '''
            Return (action, trade_value_$) where action is:
                'BUY'  - buy trade_value_$ worth of ticker
                'SELL' - sell trade_value_$ worth of ticker
                'HOLD' - do nothing (trade_value ignored)
            '''

    def add_args(parser: argparse.ArgumentParser) -> None:
        '''Module-level: register indicator-specific CLI flags.'''
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class TradeRecord:
    """Record of a single executed trade."""
    date: pd.Timestamp
    ticker: str
    action: str       # 'BUY' or 'SELL'
    price: float
    quantity: float
    value: float


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
    """Complete backtest results."""
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
    min_cash: float = 0.0
    went_negative_cash: bool = False


class BacktestEngine:
    """
    Portfolio engine that delegates signal generation to a pluggable indicator.

    Usage:
        engine = BacktestEngine(prices_df, initial_capital=10_000, indicator=my_indicator)
        results = engine.run()
    """

    def __init__(
        self,
        prices_df: pd.DataFrame,
        indicator,
        initial_capital: float = 10_000,
    ):
        """
        Args:
            prices_df:       DataFrame of closing prices (index=dates, columns=tickers).
            indicator:       An Indicator instance exposing a signal() method.
            initial_capital: Starting cash.
        """
        self.prices_df = prices_df
        self.tickers = sorted(prices_df.columns.tolist())
        self.initial_capital = initial_capital
        self.indicator = indicator

        # Portfolio state
        self.positions = {t: 0.0 for t in self.tickers}
        self.cash = initial_capital
        self.trades: list[TradeRecord] = []
        self.snapshots: list[PortfolioSnapshot] = []
        self.sector_trades: dict[str, list[TradeRecord]] = {t: [] for t in self.tickers}
        self.min_cash = initial_capital
        self.went_negative = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> BacktestResults:
        """Execute the backtest. Returns a BacktestResults object."""
        prev_prices: dict[str, float | None] = {t: None for t in self.tickers}

        for i, date in enumerate(self.prices_df.index):
            # Compute NLV once per day (used by indicators that need it)
            nlv = self._nlv(date)

            for ticker in self.tickers:
                current_price = self.prices_df.loc[date, ticker]
                if pd.isna(current_price):
                    continue

                prices_history = self.prices_df[ticker].iloc[: i + 1]

                action, trade_value = self.indicator.signal(
                    ticker=ticker,
                    date=date,
                    current_price=float(current_price),
                    prev_price=prev_prices[ticker],
                    prices_history=prices_history,
                    position=self.positions[ticker],
                    cash=self.cash,
                    nlv=nlv,
                )

                if action == "BUY":
                    self._execute_buy(ticker, date, current_price, trade_value)
                elif action == "SELL":
                    self._execute_sell(ticker, date, current_price, trade_value)

                prev_prices[ticker] = float(current_price)

            # Track minimum cash and whether we ever went negative
            if self.cash < self.min_cash:
                self.min_cash = self.cash
            if self.cash < 0:
                self.went_negative = True

            self._take_snapshot(date)

        return self._compute_results()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _nlv(self, date) -> float:
        """Net liquidation value: cash + market value of all positions."""
        invested = sum(
            self.positions[t] * self.prices_df.loc[date, t]
            for t in self.tickers
            if not pd.isna(self.prices_df.loc[date, t])
        )
        return self.cash + invested

    def _execute_buy(self, ticker: str, date, price: float, trade_value: float) -> None:
        if trade_value <= 10 or self.cash <= 0:
            return
        trade_value = min(trade_value, self.cash)
        qty = trade_value / price
        self.positions[ticker] += qty
        self.cash -= trade_value
        record = TradeRecord(date=date, ticker=ticker, action="BUY",
                             price=price, quantity=qty, value=trade_value)
        self.trades.append(record)
        self.sector_trades[ticker].append(record)

    def _execute_sell(self, ticker: str, date, price: float, trade_value: float) -> None:
        if trade_value <= 10:
            return
        max_sell = self.positions[ticker] * price
        trade_value = min(trade_value, max_sell)
        qty = trade_value / price
        self.positions[ticker] -= qty
        self.cash += trade_value
        record = TradeRecord(date=date, ticker=ticker, action="SELL",
                             price=price, quantity=qty, value=trade_value)
        self.trades.append(record)
        self.sector_trades[ticker].append(record)

    def _take_snapshot(self, date) -> None:
        invested_value = 0.0
        position_values: dict[str, float] = {}
        for ticker in self.tickers:
            p = self.prices_df.loc[date, ticker]
            if not pd.isna(p):
                val = self.positions[ticker] * p
                invested_value += val
                position_values[ticker] = val

        total_value = self.cash + invested_value
        returns_pct = (total_value - self.initial_capital) / self.initial_capital * 100
        num_positions = sum(1 for q in self.positions.values() if q > 0.001)

        self.snapshots.append(PortfolioSnapshot(
            date=date,
            total_value=total_value,
            cash=self.cash,
            invested_value=invested_value,
            positions=self.positions.copy(),
            position_values=position_values,
            num_positions=num_positions,
            returns_pct=returns_pct,
        ))

    def _compute_results(self) -> BacktestResults:
        if not self.snapshots:
            return BacktestResults(0, 0, 0, 0, 0, 0, 0, 0, {})

        total_values = np.array([s.total_value for s in self.snapshots])
        final_value = total_values[-1]
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        final_pnl = final_value - self.initial_capital

        # Max drawdown
        running_max = np.maximum.accumulate(total_values)
        drawdowns = (total_values - running_max) / running_max * 100
        max_drawdown = float(drawdowns.min())

        # Sharpe ratio (annualised)
        daily_returns = np.diff(total_values) / total_values[:-1]
        if len(daily_returns) > 1 and np.std(daily_returns, ddof=1) > 0:
            sharpe_ratio = float(
                np.mean(daily_returns) / np.std(daily_returns, ddof=1) * np.sqrt(252)
            )
        else:
            sharpe_ratio = 0.0

        # Capital efficiency
        invested_pcts = [
            s.invested_value / s.total_value if s.total_value > 0 else 0
            for s in self.snapshots
        ]
        avg_invested_pct = float(np.mean(invested_pcts)) * 100
        avg_cash_pct = 100 - avg_invested_pct

        # Sector performance
        sector_performance: dict[str, dict] = {}
        for ticker in self.tickers:
            trades = self.sector_trades[ticker]
            buys = [t for t in trades if t.action == "BUY"]
            sells = [t for t in trades if t.action == "SELL"]

            pnl = sum(
                (sell.price - buy.price) * buy.quantity
                for buy, sell in zip(buys, sells)
            )

            # Unrealized P&L on open position
            if self.positions[ticker] > 0.001 and buys:
                last_price = float(self.prices_df[ticker].iloc[-1])
                avg_buy = sum(t.value for t in buys) / sum(t.quantity for t in buys)
                pnl += (last_price - avg_buy) * self.positions[ticker]

            num_wins = sum(1 for b, s in zip(buys, sells) if s.price > b.price)

            sector_performance[ticker] = {
                "num_trades": len(buys),
                "pnl": pnl,
                "return_pct": pnl / self.initial_capital * 100 if self.initial_capital else 0,
                "num_wins": num_wins,
                "win_rate": num_wins / len(buys) * 100 if buys else 0,
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
            min_cash=self.min_cash,
            went_negative_cash=self.went_negative,
        )
