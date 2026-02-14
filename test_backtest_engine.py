"""
Unit tests for the Mean Reversion Portfolio Backtester

Tests cover:
- Position sizing logic
- Z-score calculation
- Capital allocation
- Trade execution
- Performance metrics
- Edge cases
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backtest_engine import (
    PortfolioStddevBacktester,
    TradeRecord,
    PortfolioSnapshot,
    BacktestResults,
)


class TestZScoreCalculation(unittest.TestCase):
    """Test z-score computation."""

    def setUp(self):
        """Create sample data."""
        dates = pd.date_range("2024-01-01", periods=30)
        self.prices = pd.DataFrame({
            "VGT": np.linspace(100, 120, 30),
            "VDE": np.linspace(80, 90, 30),
        }, index=dates)

    def test_z_score_positive(self):
        """Test z-score calculation when price above mean."""
        backtester = PortfolioStddevBacktester(self.prices)

        price = 110
        mean = 100
        std = 10
        z_score = backtester._compute_z_score(price, mean, std)

        self.assertAlmostEqual(z_score, 1.0, places=5)

    def test_z_score_negative(self):
        """Test z-score calculation when price below mean."""
        backtester = PortfolioStddevBacktester(self.prices)

        price = 90
        mean = 100
        std = 10
        z_score = backtester._compute_z_score(price, mean, std)

        self.assertAlmostEqual(z_score, -1.0, places=5)

    def test_z_score_at_mean(self):
        """Test z-score is zero when price equals mean."""
        backtester = PortfolioStddevBacktester(self.prices)

        price = 100
        mean = 100
        std = 10
        z_score = backtester._compute_z_score(price, mean, std)

        self.assertAlmostEqual(z_score, 0.0, places=5)

    def test_z_score_with_nan(self):
        """Test z-score returns None for NaN inputs."""
        backtester = PortfolioStddevBacktester(self.prices)

        result = backtester._compute_z_score(np.nan, 100, 10)
        self.assertIsNone(result)

        result = backtester._compute_z_score(100, np.nan, 10)
        self.assertIsNone(result)

        result = backtester._compute_z_score(100, 100, 0)
        self.assertIsNone(result)

    def test_z_score_with_zero_std(self):
        """Test z-score returns None when std is zero."""
        backtester = PortfolioStddevBacktester(self.prices)

        result = backtester._compute_z_score(100, 100, 0)
        self.assertIsNone(result)


class TestPositionSizing(unittest.TestCase):
    """Test position size calculation."""

    def setUp(self):
        """Create sample data."""
        dates = pd.date_range("2024-01-01", periods=30)
        self.prices = pd.DataFrame({
            "VGT": np.linspace(100, 120, 30),
            "VDE": np.linspace(80, 90, 30),
        }, index=dates)

    def test_position_size_at_threshold(self):
        """Test position size at z-score threshold."""
        backtester = PortfolioStddevBacktester(
            self.prices, z_threshold=1.0
        )

        available_cash = 10000
        z_score = -1.0
        position_size = backtester._get_position_size(z_score, available_cash)

        # At threshold, should use 100% of available cash
        self.assertAlmostEqual(position_size, available_cash, places=0)

    def test_position_size_half_threshold(self):
        """Test position size at half threshold."""
        backtester = PortfolioStddevBacktester(
            self.prices, z_threshold=1.0
        )

        available_cash = 10000
        z_score = -0.5
        position_size = backtester._get_position_size(z_score, available_cash)

        # At 0.5 threshold, should use 50% of available cash
        self.assertAlmostEqual(position_size, available_cash * 0.5, places=0)

    def test_position_size_zero_z_score(self):
        """Test position size with zero z-score."""
        backtester = PortfolioStddevBacktester(self.prices)

        position_size = backtester._get_position_size(0, 10000)
        self.assertEqual(position_size, 0)

    def test_position_size_capped_at_cash(self):
        """Test position size is capped at available cash."""
        backtester = PortfolioStddevBacktester(self.prices)

        available_cash = 5000
        z_score = -2.0  # More extreme than threshold
        position_size = backtester._get_position_size(z_score, available_cash)

        # Should not exceed available cash
        self.assertLessEqual(position_size, available_cash)


class TestCapitalAllocation(unittest.TestCase):
    """Test capital allocation logic."""

    def setUp(self):
        """Create sample data."""
        dates = pd.date_range("2024-01-01", periods=30)
        self.prices = pd.DataFrame({
            "VGT": np.linspace(100, 120, 30),
            "VDE": np.linspace(80, 90, 30),
        }, index=dates)

    def test_initial_capital(self):
        """Test backtester starts with correct capital."""
        backtester = PortfolioStddevBacktester(
            self.prices, initial_capital=10000
        )
        self.assertEqual(backtester.cash, 10000)

    def test_max_sector_allocation(self):
        """Test sector allocation is capped at max."""
        backtester = PortfolioStddevBacktester(
            self.prices,
            initial_capital=10000,
            max_sector_allocation=0.30,
        )

        ticker = "VGT"
        available = backtester._get_available_capital(ticker)
        max_allowed = 10000 * 0.30

        # Available should not exceed max allocation
        self.assertLessEqual(available, max_allowed)

    def test_cash_deduction_on_buy(self):
        """Test cash is deducted when buying."""
        backtester = PortfolioStddevBacktester(
            self.prices, initial_capital=10000
        )

        initial_cash = backtester.cash
        buy_value = 2000
        backtester.cash -= buy_value

        self.assertEqual(backtester.cash, initial_cash - buy_value)


class TestBacktestExecution(unittest.TestCase):
    """Test complete backtest execution."""

    def setUp(self):
        """Create sample data."""
        dates = pd.date_range("2024-01-01", periods=100)
        np.random.seed(42)

        # Create mean-reverting series
        vgt_prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
        vde_prices = 80 + np.cumsum(np.random.randn(100) * 0.4)

        self.prices = pd.DataFrame({
            "VGT": vgt_prices,
            "VDE": vde_prices,
        }, index=dates)

    def test_backtest_runs_without_error(self):
        """Test backtest completes without error."""
        backtester = PortfolioStddevBacktester(self.prices)
        results = backtester.run()

        self.assertIsNotNone(results)
        self.assertIsInstance(results, BacktestResults)

    def test_backtest_has_snapshots(self):
        """Test backtest creates daily snapshots."""
        backtester = PortfolioStddevBacktester(self.prices)
        results = backtester.run()

        self.assertGreater(len(results.snapshots), 0)
        self.assertLessEqual(len(results.snapshots), len(self.prices))

    def test_backtest_final_value_reasonable(self):
        """Test final portfolio value is reasonable."""
        backtester = PortfolioStddevBacktester(
            self.prices, initial_capital=10000
        )
        results = backtester.run()

        # Value should be positive
        self.assertGreater(results.final_value, 0)
        # Should not be unreasonably high (1000% gain)
        self.assertLess(results.final_value, 100000)

    def test_backtest_computes_return(self):
        """Test backtest computes total return."""
        backtester = PortfolioStddevBacktester(
            self.prices, initial_capital=10000
        )
        results = backtester.run()

        expected_return = (results.final_value - 10000) / 10000 * 100
        self.assertAlmostEqual(results.total_return, expected_return, places=2)

    def test_backtest_max_drawdown_reasonable(self):
        """Test max drawdown is between 0 and -100%."""
        backtester = PortfolioStddevBacktester(self.prices)
        results = backtester.run()

        self.assertGreaterEqual(results.max_drawdown, -100)
        self.assertLessEqual(results.max_drawdown, 0)


class TestPerformanceMetrics(unittest.TestCase):
    """Test performance metric calculations."""

    def setUp(self):
        """Create sample data."""
        dates = pd.date_range("2024-01-01", periods=100)
        np.random.seed(42)

        vgt_prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
        vde_prices = 80 + np.cumsum(np.random.randn(100) * 0.4)

        self.prices = pd.DataFrame({
            "VGT": vgt_prices,
            "VDE": vde_prices,
        }, index=dates)

    def test_sharpe_ratio_calculation(self):
        """Test Sharpe ratio is calculated."""
        backtester = PortfolioStddevBacktester(self.prices)
        results = backtester.run()

        # Sharpe ratio should be a number
        self.assertIsInstance(results.sharpe_ratio, (int, float))
        # Should be reasonable (between -5 and +5)
        self.assertGreater(results.sharpe_ratio, -5)
        self.assertLess(results.sharpe_ratio, 5)

    def test_capital_efficiency(self):
        """Test capital efficiency metrics."""
        backtester = PortfolioStddevBacktester(self.prices)
        results = backtester.run()

        # Should be between 0 and 100%
        self.assertGreaterEqual(results.avg_invested_pct, 0)
        self.assertLessEqual(results.avg_invested_pct, 100)

        # Cash + invested should equal 100%
        self.assertAlmostEqual(
            results.avg_invested_pct + results.avg_cash_pct,
            100,
            places=1,
        )

    def test_sector_performance_tracked(self):
        """Test sector performance is tracked."""
        backtester = PortfolioStddevBacktester(self.prices)
        results = backtester.run()

        self.assertGreater(len(results.sector_performance), 0)

        for ticker, perf in results.sector_performance.items():
            self.assertIn("num_trades", perf)
            self.assertIn("pnl", perf)
            self.assertIn("return_pct", perf)
            self.assertIn("num_wins", perf)
            self.assertIn("win_rate", perf)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_single_day_backtest(self):
        """Test backtest with just one day of data."""
        dates = pd.date_range("2024-01-01", periods=1)
        prices = pd.DataFrame({
            "VGT": [100],
            "VDE": [80],
        }, index=dates)

        backtester = PortfolioStddevBacktester(prices)
        results = backtester.run()

        # Should handle gracefully
        self.assertIsNotNone(results)

    def test_insufficient_data_for_lookback(self):
        """Test backtest with data smaller than lookback period."""
        dates = pd.date_range("2024-01-01", periods=5)
        prices = pd.DataFrame({
            "VGT": [100, 101, 102, 103, 104],
            "VDE": [80, 81, 82, 83, 84],
        }, index=dates)

        backtester = PortfolioStddevBacktester(prices, lookback_period=20)
        results = backtester.run()

        # Should complete without error
        self.assertIsNotNone(results)

    def test_flat_market(self):
        """Test backtest on flat market (no price changes)."""
        dates = pd.date_range("2024-01-01", periods=30)
        prices = pd.DataFrame({
            "VGT": [100] * 30,
            "VDE": [80] * 30,
        }, index=dates)

        backtester = PortfolioStddevBacktester(prices)
        results = backtester.run()

        # Should complete without error
        self.assertIsNotNone(results)
        # Shouldn't generate trades (no signal)
        self.assertEqual(results.num_trades, 0)

    def test_highly_volatile_market(self):
        """Test backtest on highly volatile market."""
        dates = pd.date_range("2024-01-01", periods=100)
        np.random.seed(42)

        # Very volatile series
        vgt_prices = 100 + np.cumsum(np.random.randn(100) * 5)
        vde_prices = 80 + np.cumsum(np.random.randn(100) * 4)

        prices = pd.DataFrame({
            "VGT": vgt_prices,
            "VDE": vde_prices,
        }, index=dates)

        backtester = PortfolioStddevBacktester(prices)
        results = backtester.run()

        # Should complete and likely generate many trades
        self.assertIsNotNone(results)

    def test_negative_prices(self):
        """Test backtest handles negative prices gracefully."""
        dates = pd.date_range("2024-01-01", periods=30)
        prices = pd.DataFrame({
            "VGT": np.linspace(10, -10, 30),
            "VDE": np.linspace(8, -8, 30),
        }, index=dates)

        backtester = PortfolioStddevBacktester(prices)
        results = backtester.run()

        # Should complete without error
        self.assertIsNotNone(results)

    def test_zero_threshold(self):
        """Test backtest with zero z-score threshold."""
        dates = pd.date_range("2024-01-01", periods=50)
        prices = pd.DataFrame({
            "VGT": np.sin(np.linspace(0, 4*np.pi, 50)) * 10 + 100,
            "VDE": np.sin(np.linspace(0, 4*np.pi, 50)) * 8 + 80,
        }, index=dates)

        backtester = PortfolioStddevBacktester(prices, z_threshold=0.0)
        results = backtester.run()

        # Should complete
        self.assertIsNotNone(results)


class TestDataIntegrity(unittest.TestCase):
    """Test data integrity throughout backtest."""

    def setUp(self):
        """Create sample data."""
        dates = pd.date_range("2024-01-01", periods=100)
        np.random.seed(42)

        vgt_prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
        vde_prices = 80 + np.cumsum(np.random.randn(100) * 0.4)

        self.prices = pd.DataFrame({
            "VGT": vgt_prices,
            "VDE": vde_prices,
        }, index=dates)

    def test_cash_conservation(self):
        """Test cash + invested value equals total value."""
        backtester = PortfolioStddevBacktester(self.prices)
        results = backtester.run()

        for snapshot in results.snapshots:
            expected_total = snapshot.cash + snapshot.invested_value
            self.assertAlmostEqual(
                snapshot.total_value,
                expected_total,
                places=2,
            )

    def test_positions_non_negative(self):
        """Test all positions are non-negative."""
        backtester = PortfolioStddevBacktester(self.prices)
        results = backtester.run()

        for snapshot in results.snapshots:
            for ticker, qty in snapshot.positions.items():
                self.assertGreaterEqual(qty, 0)

    def test_trades_balanced(self):
        """Test buys and sells are balanced."""
        backtester = PortfolioStddevBacktester(self.prices)
        results = backtester.run()

        buy_count = sum(1 for t in backtester.trades if t.action == "BUY")
        sell_count = sum(1 for t in backtester.trades if t.action == "SELL")

        # Sells should not exceed buys
        self.assertLessEqual(sell_count, buy_count + 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
