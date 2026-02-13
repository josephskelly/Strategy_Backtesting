"""
Portfolio-Level Standard Deviation Trading Strategy

Implements dynamic shared capital pool:
- Single $10k portfolio allocated across 11 sectors
- Each sector can hold up to 30% of portfolio
- Positions buy when signal appears, sell at profit target
- Capital shared dynamically based on signal strength
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


@dataclass
class PortfolioSnapshot:
    """Daily portfolio state."""
    date: pd.Timestamp
    total_value: float
    cash: float
    invested_value: float
    positions: dict = field(default_factory=dict)  # {ticker: shares}
    position_values: dict = field(default_factory=dict)  # {ticker: value}
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
    sector_performance: dict  # {ticker: {trades, pnl, return_pct}}
    snapshots: list = field(default_factory=list)


class PortfolioStddevBacktester:
    """
    Portfolio-level backtester with dynamic shared capital pool.

    Rules:
    - Single $10k capital pool shared across all sectors
    - Max 30% per sector to avoid concentration
    - Position sizing based on z-score strength
    - Buy when z_score <= -threshold, sell when >= +threshold
    """

    def __init__(
        self,
        prices_df: pd.DataFrame,  # columns=tickers, index=dates
        initial_capital: float = 10000,
        lookback_period: int = 20,
        z_threshold: float = 1.0,
        max_sector_allocation: float = 0.30,  # 30% max per sector
    ):
        """
        Initialize portfolio backtester.

        Args:
            prices_df: Historical prices (columns=tickers, index=dates)
            initial_capital: Total starting capital
            lookback_period: Days for rolling mean/std
            z_threshold: Buy at -z_threshold, sell at +z_threshold
            max_sector_allocation: Max % of portfolio per sector (0.30 = 30%)
        """
        self.prices_df = prices_df
        self.tickers = sorted(prices_df.columns.tolist())
        self.initial_capital = initial_capital
        self.lookback_period = lookback_period
        self.z_threshold = z_threshold
        self.max_sector_allocation = max_sector_allocation

        # Compute rolling statistics
        self.rolling_means = {}
        self.rolling_stds = {}
        for ticker in self.tickers:
            self.rolling_means[ticker] = prices_df[ticker].rolling(lookback_period).mean()
            self.rolling_stds[ticker] = prices_df[ticker].rolling(lookback_period).std()

        # Portfolio state
        self.positions = {ticker: 0.0 for ticker in self.tickers}
        self.cash = initial_capital
        self.trades = []
        self.snapshots = []

        # Sector tracking
        self.sector_trades = {ticker: [] for ticker in self.tickers}

    def _compute_z_score(self, price: float, mean: float, std: float) -> Optional[float]:
        """Compute z-score."""
        if pd.isna(price) or pd.isna(mean) or pd.isna(std) or std == 0:
            return None
        return (price - mean) / std

    def _get_position_size(self, z_score: float, available_cash: float) -> float:
        """
        Position size proportional to z-score strength.

        Linear scaling: at z_threshold → 100% of available capital
        This matches the original high-performance implementation.
        """
        if z_score == 0:
            return 0
        abs_z = abs(z_score)
        # Scale from 0 to 100% of available cash based on z-score intensity
        position_ratio = min(abs_z / self.z_threshold, 1.0)
        return available_cash * position_ratio

    def _get_available_capital(self, ticker: str) -> float:
        """
        Calculate available capital for a sector.

        Considers:
        - Current cash in portfolio
        - Max allocation cap (30%)
        - Existing position value
        """
        max_sector_value = self.initial_capital * self.max_sector_allocation
        current_sector_value = self.positions[ticker] * self.prices_df[ticker].iloc[-1]

        # Can invest up to max, minus what's already invested
        can_add = max(0, max_sector_value - current_sector_value)

        # But only if we have cash available
        return min(self.cash, can_add)

    def run(self) -> BacktestResults:
        """Execute portfolio backtest."""
        for i, date in enumerate(self.prices_df.index):
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

                # BUY signal: price falls 1+ std devs below mean
                if self.positions[ticker] == 0 and z_score <= -self.z_threshold:
                    available_capital = self._get_available_capital(ticker)
                    if available_capital > 0:
                        position_value = self._get_position_size(z_score, available_capital)
                        if position_value > 0:
                            qty = position_value / price
                            self.positions[ticker] = qty
                            self.cash -= position_value

                            trade = TradeRecord(
                                date=date,
                                ticker=ticker,
                                action="BUY",
                                price=price,
                                quantity=qty,
                                value=position_value,
                                z_score=z_score,
                            )
                            self.trades.append(trade)
                            self.sector_trades[ticker].append(trade)

                # SELL signal: price rises 1+ std devs above mean
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
                    )
                    self.trades.append(trade)
                    self.sector_trades[ticker].append(trade)
                    self.positions[ticker] = 0

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
                # PnL = (sell_price - buy_price) * shares
                pnl_per_share = sell.price - buy.price
                sector_pnl += pnl_per_share * buy.quantity

            # Add unrealized P&L if position still open
            if self.positions[ticker] > 0 and len(buy_trades) > 0:
                current_price = self.prices_df[ticker].iloc[-1]
                last_buy = buy_trades[-1]
                # Unrealized = current value - cost basis of last buy
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


def run_portfolio_backtest(range_: str = "2y"):
    """Run portfolio backtest with dynamic allocation."""
    print("=" * 100)
    print("PORTFOLIO STANDARD DEVIATION TRADING STRATEGY - DYNAMIC SHARED POOL")
    print("=" * 100)
    print()
    print("Configuration:")
    print(f"  Initial Capital:           $10,000")
    print(f"  Allocation Method:         Dynamic Shared Pool")
    print(f"  Max Per Sector:            30% ($3,000)")
    print(f"  Lookback Period:           20 days")
    print(f"  Z-Score Threshold:         1.0 (buy at -1.0, sell at +1.0)")
    print(f"  Position Sizing:           Proportional to z-score strength")
    print()

    print(f"Fetching sector ETF prices for range={range_}...")
    closes = fetch_sector_closes(range_=range_)

    print("Running portfolio backtest...")
    backtester = PortfolioStddevBacktester(
        prices_df=closes,
        initial_capital=10000,
        lookback_period=20,
        z_threshold=1.0,
        max_sector_allocation=0.30,
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
    print("SECTOR SUMMARY STATISTICS")
    print("=" * 100)

    print(f"\nTop Performer:               {sector_results.iloc[0]['Ticker']} ({sector_results.iloc[0]['Return %']:.2f}%)")
    print(f"Worst Performer:             {sector_results.iloc[-1]['Ticker']} ({sector_results.iloc[-1]['Return %']:.2f}%)")
    print(f"Average Sector Return:       {sector_results['Return %'].mean():.2f}%")
    print(f"Sectors with Positive Return: {len(sector_results[sector_results['Return %'] > 0])}/11")
    print(f"Total Wins:                  {sector_results['Wins'].sum():.0f} trades")
    print(f"Avg Win Rate:                {sector_results['Win Rate %'].mean():.2f}%")

    # Save results
    output_file = "portfolio_backtest_results.csv"
    sector_results.to_csv(output_file, index=False)
    print(f"\n✓ Results saved to {output_file}")

    # Capital efficiency summary
    print("\n" + "=" * 100)
    print("CAPITAL EFFICIENCY")
    print("=" * 100)

    if results.snapshots:
        max_cash = max([s.cash for s in results.snapshots])
        min_cash = min([s.cash for s in results.snapshots])
        max_deployed = max([
            (s.total_value - s.cash) / s.total_value * 100
            if s.total_value > 0 else 0
            for s in results.snapshots
        ])

        print(f"\nAverage Capital Deployed:    {results.avg_invested_pct:.2f}%")
        print(f"Peak Capital Deployed:       {max_deployed:.2f}%")
        print(f"Max Cash Available:          ${max_cash:,.2f}")
        print(f"Min Cash Available:          ${min_cash:,.2f}")

    print()

    return results, backtester


if __name__ == "__main__":
    results, backtester = run_portfolio_backtest(range_="2y")
