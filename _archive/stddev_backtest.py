"""
Standard Deviation Trading Strategy Backtest

Implements a mean-reversion strategy where:
- Buy signals when price falls below (mean - N*std_dev)
- Sell signals when price rises above (mean + N*std_dev)
- Position size is proportional to the z-score (std devs from mean)
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
    z_score: float  # How many std devs from mean


@dataclass
class BacktestResults:
    """Complete backtest results."""
    ticker: str
    total_return: float  # Percent
    max_drawdown: float  # Percent (negative)
    sharpe_ratio: float
    win_rate: float  # Percent
    num_trades: int
    final_pnl: float
    final_shares: float
    trades: list[TradeRecord]


class StddevBacktester:
    """Backtester for standard deviation-based trading strategy."""

    def __init__(
        self,
        ticker: str,
        prices: pd.Series,
        lookback_period: int = 20,
        z_threshold: float = 1.0,
        initial_capital: float = 10000,
    ):
        """
        Initialize backtester.

        Args:
            ticker: Stock/ETF ticker symbol
            prices: Historical closing prices (pd.Series with DatetimeIndex)
            lookback_period: Period for rolling std dev calculation
            z_threshold: Buy/sell when |z_score| >= z_threshold
            initial_capital: Starting capital
        """
        self.ticker = ticker
        self.prices = prices.dropna()
        self.lookback_period = lookback_period
        self.z_threshold = z_threshold
        self.initial_capital = initial_capital

        # Compute rolling stats
        self.rolling_mean = self.prices.rolling(lookback_period).mean()
        self.rolling_std = self.prices.rolling(window=lookback_period).std()

        # Initialize state
        self.shares = 0.0
        self.cash = initial_capital
        self.trades = []
        self.daily_pnl = []
        self.daily_values = []

    def _compute_z_score(self, price: float, mean: float, std: float) -> Optional[float]:
        """Compute z-score (distance from mean in std devs)."""
        if pd.isna(mean) or pd.isna(std) or std == 0:
            return None
        return (price - mean) / std

    def _get_position_size(self, z_score: float, available_cash: float) -> float:
        """
        Determine position size based on z-score.

        Position size is proportional to |z_score|.
        """
        if z_score == 0:
            return 0
        abs_z = abs(z_score)
        # Use increasing leverage with more extreme moves
        position_ratio = min(abs_z / self.z_threshold, 1.0)
        return available_cash * position_ratio

    def _should_buy(self, z_score: Optional[float]) -> bool:
        """Buy when price falls below (mean - z_threshold * std)."""
        return z_score is not None and z_score <= -self.z_threshold

    def _should_sell(self, z_score: Optional[float]) -> bool:
        """Sell when price rises above (mean + z_threshold * std)."""
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
                    position_value = self._get_position_size(z_score, self.cash)
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
                    trade_pnl = sale_value - sum(t.value for t in self.trades if t.action == "BUY")
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

            # Track daily P&L
            daily_pnl = portfolio_value - self.initial_capital
            self.daily_pnl.append(daily_pnl)
            self.daily_values.append(portfolio_value)

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

        # Sharpe ratio (annualized)
        daily_returns = np.diff(self.daily_pnl) / self.initial_capital
        sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252) if len(daily_returns) > 1 else 0

        # Win rate
        buy_trades = [t for t in self.trades if t.action == "BUY"]
        sell_trades = [t for t in self.trades if t.action == "SELL"]
        if len(buy_trades) > 0 and len(sell_trades) > 0:
            # Match buys with sells (FIFO)
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


def backtest_stddev_strategy(
    ticker: str,
    prices: pd.Series,
    lookback_period: int = 20,
    z_threshold: float = 1.0,
    initial_capital: float = 10000,
) -> BacktestResults:
    """
    Backtest standard deviation trading strategy on historical prices.

    Args:
        ticker: Stock/ETF ticker
        prices: Historical closing prices
        lookback_period: Period for rolling standard deviation
        z_threshold: Z-score threshold for buy/sell signals
        initial_capital: Starting capital

    Returns:
        BacktestResults with performance metrics and trade history
    """
    backtester = StddevBacktester(
        ticker=ticker,
        prices=prices,
        lookback_period=lookback_period,
        z_threshold=z_threshold,
        initial_capital=initial_capital,
    )
    return backtester.run()


def backtest_all_etfs(
    range_: str = "2y",
    lookback_period: int = 20,
    z_threshold: float = 1.0,
    initial_capital: float = 10000,
) -> pd.DataFrame:
    """
    Backtest strategy on all sector ETFs.

    Returns:
        DataFrame with results for each ETF
    """
    print(f"Fetching {len(SECTOR_ETFS)} sector ETF prices for range={range_}...")
    closes = fetch_sector_closes(range_=range_)

    results = []
    for ticker in closes.columns:
        print(f"  Backtesting {ticker}...")
        result = backtest_stddev_strategy(
            ticker=ticker,
            prices=closes[ticker],
            lookback_period=lookback_period,
            z_threshold=z_threshold,
            initial_capital=initial_capital,
        )
        results.append(
            {
                "Sector": SECTOR_ETFS[ticker],
                "Ticker": ticker,
                "Total Return %": result.total_return,
                "Max Drawdown %": result.max_drawdown,
                "Sharpe Ratio": result.sharpe_ratio,
                "Win Rate %": result.win_rate,
                "Num Trades": result.num_trades,
                "Final P&L": result.final_pnl,
            }
        )

    df = pd.DataFrame(results)
    df = df.sort_values("Total Return %", ascending=False).reset_index(drop=True)
    return df


def analyze_single_ticker(
    ticker: str,
    range_: str = "2y",
    lookback_period: int = 20,
    z_threshold: float = 1.0,
    initial_capital: float = 10000,
) -> BacktestResults:
    """
    Analyze a single ticker with detailed trade history.

    Returns:
        BacktestResults with all trades and metrics
    """
    closes = fetch_sector_closes(range_=range_)
    if ticker not in closes.columns:
        raise ValueError(f"Ticker {ticker} not found in data")

    return backtest_stddev_strategy(
        ticker=ticker,
        prices=closes[ticker],
        lookback_period=lookback_period,
        z_threshold=z_threshold,
        initial_capital=initial_capital,
    )


if __name__ == "__main__":
    print("=" * 90)
    print("  Standard Deviation Trading Strategy Backtest (2-Year History)")
    print("=" * 90)
    print()

    # Run backtest with default parameters
    results_df = backtest_all_etfs(
        range_="2y",
        lookback_period=20,
        z_threshold=1.0,
        initial_capital=10000,
    )

    print("\nBacktest Results Summary:")
    print(results_df.to_string(index=False, float_format="%.2f"))

    print("\n" + "=" * 90)
    print("  Strategy Parameters")
    print("=" * 90)
    print(f"  Lookback Period:  20 days")
    print(f"  Z-Score Threshold: 1.0 (buy at -1.0, sell at +1.0)")
    print(f"  Initial Capital:  $10,000")
    print(f"  Position Sizing:  Proportional to |z_score|")
    print()
    print("Strategy Details:")
    print("  • Buy Signal: Price falls to (mean - 1.0 * std_dev)")
    print("  • Sell Signal: Price rises to (mean + 1.0 * std_dev)")
    print("  • Position Size: Proportional to distance from mean")
    print("  • Mean Reversion: Strategy profits from price reverting to mean")
    print()
