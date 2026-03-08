"""
Unit tests for engine.py — BacktestEngine + BacktestResults.

All tests use synthetic in-memory price data; no network calls.
Indicators are replaced with simple lambda-based stubs.
"""

import math
import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_prices
from engine import BacktestEngine, BacktestResults, TradeRecord, PortfolioSnapshot


# ---------------------------------------------------------------------------
# Minimal stub indicators
# ---------------------------------------------------------------------------

class HoldIndicator:
    """Always returns HOLD — used to test engine with no trades."""
    def signal(self, **kwargs):
        return ("HOLD", 0.0)


class BuyIndicator:
    """Always returns BUY for a fixed trade value."""
    def __init__(self, trade_value: float = 100.0):
        self.trade_value = trade_value

    def signal(self, **kwargs):
        return ("BUY", self.trade_value)


class SellIndicator:
    """Always returns SELL for a fixed trade value."""
    def __init__(self, trade_value: float = 100.0):
        self.trade_value = trade_value

    def signal(self, **kwargs):
        return ("SELL", self.trade_value)


class ScriptedIndicator:
    """
    Returns pre-scripted (action, value) pairs per call, cycling if needed.
    signals: list of ("BUY"/"SELL"/"HOLD", value) tuples.
    """
    def __init__(self, signals: list):
        self._signals = signals
        self._i = 0

    def signal(self, **kwargs):
        result = self._signals[self._i % len(self._signals)]
        self._i += 1
        return result


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestInitialization:
    def test_initial_cash_equals_capital(self):
        prices = make_prices({"A": [100.0, 101.0]})
        engine = BacktestEngine(prices, HoldIndicator(), initial_capital=5_000)
        assert engine.cash == 5_000

    def test_initial_positions_are_zero(self):
        prices = make_prices({"A": [100.0], "B": [50.0]})
        engine = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000)
        assert engine.positions == {"A": 0.0, "B": 0.0}

    def test_tickers_sorted(self):
        prices = make_prices({"Z": [1.0], "A": [2.0], "M": [3.0]})
        engine = BacktestEngine(prices, HoldIndicator())
        assert engine.tickers == ["A", "M", "Z"]


# ---------------------------------------------------------------------------
# _nlv()
# ---------------------------------------------------------------------------

class TestNlv:
    def test_nlv_all_cash_no_positions(self):
        prices = make_prices({"A": [100.0, 105.0]})
        engine = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000)
        date = prices.index[0]
        assert engine._nlv(date) == pytest.approx(10_000.0)

    def test_nlv_includes_open_position(self):
        prices = make_prices({"A": [100.0, 105.0]})
        engine = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000)
        engine.positions["A"] = 10.0   # 10 shares
        engine.cash = 9_000.0
        date = prices.index[0]         # price == 100
        # NLV = 9000 + 10 * 100 = 10_000
        assert engine._nlv(date) == pytest.approx(10_000.0)

    def test_nlv_skips_nan_price(self):
        prices = make_prices({"A": [float("nan"), 100.0]})
        engine = BacktestEngine(prices, HoldIndicator(), initial_capital=5_000)
        engine.positions["A"] = 10.0
        date = prices.index[0]   # price is NaN
        assert engine._nlv(date) == pytest.approx(5_000.0)


# ---------------------------------------------------------------------------
# _execute_buy()
# ---------------------------------------------------------------------------

class TestExecuteBuy:
    def _engine(self, capital=10_000):
        prices = make_prices({"A": [100.0, 105.0]})
        return BacktestEngine(prices, HoldIndicator(), initial_capital=capital)

    def test_buy_reduces_cash(self):
        e = self._engine()
        date = make_prices({"A": [100.0]}).index[0]
        e._execute_buy("A", date, 100.0, 500.0)
        assert e.cash == pytest.approx(9_500.0)

    def test_buy_increases_position(self):
        e = self._engine()
        date = make_prices({"A": [100.0]}).index[0]
        e._execute_buy("A", date, 100.0, 500.0)   # 500 / 100 = 5 shares
        assert e.positions["A"] == pytest.approx(5.0)

    def test_buy_records_trade(self):
        e = self._engine()
        date = make_prices({"A": [100.0]}).index[0]
        e._execute_buy("A", date, 100.0, 500.0)
        assert len(e.trades) == 1
        assert e.trades[0].action == "BUY"
        assert e.trades[0].value == pytest.approx(500.0)

    def test_buy_capped_at_available_cash(self):
        e = self._engine(capital=200)
        date = make_prices({"A": [100.0]}).index[0]
        e._execute_buy("A", date, 100.0, 500.0)   # want 500, only have 200
        assert e.cash == pytest.approx(0.0)
        assert e.positions["A"] == pytest.approx(2.0)

    def test_buy_ignored_when_trade_value_too_small(self):
        e = self._engine()
        date = make_prices({"A": [100.0]}).index[0]
        e._execute_buy("A", date, 100.0, 9.99)   # below $10 minimum
        assert e.cash == pytest.approx(10_000.0)
        assert e.positions["A"] == pytest.approx(0.0)
        assert len(e.trades) == 0

    def test_buy_ignored_with_zero_cash(self):
        e = self._engine(capital=0)
        date = make_prices({"A": [100.0]}).index[0]
        e._execute_buy("A", date, 100.0, 500.0)
        assert e.positions["A"] == pytest.approx(0.0)
        assert len(e.trades) == 0


# ---------------------------------------------------------------------------
# _execute_sell()
# ---------------------------------------------------------------------------

class TestExecuteSell:
    def _engine_with_position(self, qty=10.0, price=100.0, capital=5_000):
        prices = make_prices({"A": [price, price * 1.1]})
        e = BacktestEngine(prices, HoldIndicator(), initial_capital=capital)
        e.positions["A"] = qty
        return e

    def test_sell_increases_cash(self):
        e = self._engine_with_position(qty=5.0)
        date = make_prices({"A": [100.0]}).index[0]
        e._execute_sell("A", date, 100.0, 300.0)  # sell $300 worth
        assert e.cash == pytest.approx(5_300.0)

    def test_sell_reduces_position(self):
        e = self._engine_with_position(qty=5.0)
        date = make_prices({"A": [100.0]}).index[0]
        e._execute_sell("A", date, 100.0, 300.0)  # 300 / 100 = 3 shares
        assert e.positions["A"] == pytest.approx(2.0)

    def test_sell_records_trade(self):
        e = self._engine_with_position(qty=5.0)
        date = make_prices({"A": [100.0]}).index[0]
        e._execute_sell("A", date, 100.0, 300.0)
        assert len(e.trades) == 1
        assert e.trades[0].action == "SELL"

    def test_sell_capped_at_position_value(self):
        e = self._engine_with_position(qty=2.0)  # 2 shares × $100 = $200 max
        date = make_prices({"A": [100.0]}).index[0]
        e._execute_sell("A", date, 100.0, 1_000.0)  # want to sell $1000, max $200
        assert e.positions["A"] == pytest.approx(0.0)
        assert e.cash == pytest.approx(5_200.0)

    def test_sell_ignored_when_trade_value_too_small(self):
        e = self._engine_with_position(qty=5.0)
        date = make_prices({"A": [100.0]}).index[0]
        e._execute_sell("A", date, 100.0, 5.0)   # below $10 minimum
        assert e.positions["A"] == pytest.approx(5.0)
        assert len(e.trades) == 0


# ---------------------------------------------------------------------------
# run() — integration with stub indicators
# ---------------------------------------------------------------------------

class TestRun:
    def test_hold_indicator_no_trades(self):
        prices = make_prices({"A": [100.0, 98.0, 102.0]})
        results = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000).run()
        assert results.num_trades == 0

    def test_hold_indicator_cash_unchanged(self):
        prices = make_prices({"A": [100.0, 98.0, 102.0]})
        e = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000)
        e.run()
        assert e.cash == pytest.approx(10_000.0)

    def test_buy_then_sell_produces_trades(self):
        # Day 1: BUY $500 at 100 → 5 shares
        # Day 2: SELL $500 at 105 → partial sell
        # Day 3: HOLD
        signals = [("BUY", 500.0), ("SELL", 500.0), ("HOLD", 0.0)]
        prices = make_prices({"A": [100.0, 105.0, 102.0]})
        indicator = ScriptedIndicator(signals)
        results = BacktestEngine(prices, indicator, initial_capital=10_000).run()
        assert results.num_trades == 2

    def test_snapshot_count_equals_trading_days(self):
        prices = make_prices({"A": [100.0, 101.0, 102.0, 103.0, 104.0]})
        results = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000).run()
        assert len(results.snapshots) == 5

    def test_snapshot_total_value_consistency(self):
        prices = make_prices({"A": [100.0, 98.0, 103.0]})
        results = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000).run()
        for snap in results.snapshots:
            assert snap.total_value == pytest.approx(snap.cash + snap.invested_value)

    def test_nan_price_skipped(self):
        """A NaN price on day 2 should not crash and should not generate a trade."""
        prices = make_prices({"A": [100.0, float("nan"), 102.0]})
        results = BacktestEngine(prices, BuyIndicator(500), initial_capital=10_000).run()
        # Day 1 & 3 trigger BUY; day 2 skipped → 2 trades
        assert results.num_trades == 2

    def test_min_cash_tracked(self):
        prices = make_prices({"A": [100.0, 98.0, 97.0]})
        e = BacktestEngine(prices, BuyIndicator(2_000), initial_capital=10_000)
        results = e.run()
        assert results.min_cash < 10_000

    def test_went_negative_false_with_safe_signals(self):
        prices = make_prices({"A": [100.0, 98.0]})
        results = BacktestEngine(prices, BuyIndicator(100), initial_capital=10_000).run()
        assert results.went_negative_cash is False

    def test_multiple_tickers_independent(self):
        prices = make_prices({"A": [100.0, 98.0], "B": [50.0, 52.0]})
        results = BacktestEngine(prices, BuyIndicator(100), initial_capital=10_000).run()
        # Each ticker triggers BUY on day 1 (no prev_price on day 0; buy on day 1)
        # Actually BuyIndicator always returns BUY on every bar
        assert results.num_trades > 0


# ---------------------------------------------------------------------------
# _compute_results()
# ---------------------------------------------------------------------------

class TestComputeResults:
    def test_empty_snapshots_returns_zeros(self):
        prices = make_prices({"A": [100.0]})
        e = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000)
        # Don't run — call _compute_results directly on empty state
        results = e._compute_results()
        assert results.total_return == 0
        assert results.num_trades == 0

    def test_total_return_flat_market(self):
        prices = make_prices({"A": [100.0, 100.0, 100.0]})
        results = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000).run()
        assert results.total_return == pytest.approx(0.0)

    def test_total_return_positive_after_profitable_trade(self):
        # BUY 100 shares at 100, SELL 100 shares at 110 (+$1000 profit)
        prices = make_prices({"A": [100.0, 110.0]})
        signals = [("BUY", 10_000.0), ("SELL", 10_000.0)]
        results = BacktestEngine(
            prices, ScriptedIndicator(signals), initial_capital=10_000
        ).run()
        assert results.total_return > 0

    def test_final_value_equals_initial_with_no_trades(self):
        prices = make_prices({"A": [100.0, 105.0, 110.0]})
        results = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000).run()
        assert results.final_value == pytest.approx(10_000.0)

    def test_max_drawdown_is_negative(self):
        # Prices peak then fall — must produce a negative drawdown
        prices = make_prices({"A": [100.0, 120.0, 80.0]})
        signals = [("BUY", 5_000.0), ("HOLD", 0.0), ("HOLD", 0.0)]
        results = BacktestEngine(
            prices, ScriptedIndicator(signals), initial_capital=10_000
        ).run()
        assert results.max_drawdown < 0

    def test_max_drawdown_zero_with_no_trades(self):
        prices = make_prices({"A": [100.0, 100.0, 100.0]})
        results = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000).run()
        assert results.max_drawdown == pytest.approx(0.0)

    def test_sharpe_zero_when_no_variation(self):
        prices = make_prices({"A": [100.0, 100.0, 100.0, 100.0]})
        results = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000).run()
        assert results.sharpe_ratio == pytest.approx(0.0)

    def test_sharpe_uses_percentage_returns(self):
        """Sharpe should use prior-day value as denominator, not initial capital."""
        # With HoldIndicator and no trades, total_values == [10_000] * N.
        # Prices going up don't change portfolio (no positions held).
        # Use a scripted indicator: buy on day 0, hold after.
        # Prices: 100, 110, 121 → portfolio gains from the position.
        prices = make_prices({"A": [100.0, 110.0, 121.0, 133.1]})
        signals = [("BUY", 5_000.0), ("HOLD", 0.0), ("HOLD", 0.0), ("HOLD", 0.0)]
        results = BacktestEngine(
            prices, ScriptedIndicator(signals), initial_capital=10_000
        ).run()
        # With 50 shares bought at 100 ($5000), values are:
        # Day 0: cash=5000, invested=5000, total=10000
        # Day 1: cash=5000, invested=5500, total=10500
        # Day 2: cash=5000, invested=6050, total=11050
        # Day 3: cash=5000, invested=6655, total=11655
        # daily % returns: 500/10000=5%, 550/10500≈5.238%, 605/11050≈5.475%
        # These are NOT equal — confirming the denominator varies by day
        total_values = np.array([10_000.0, 10_500.0, 11_050.0, 11_655.0])
        daily_rets = np.diff(total_values) / total_values[:-1]
        expected = float(
            np.mean(daily_rets) / np.std(daily_rets, ddof=1) * np.sqrt(252)
        )
        assert results.sharpe_ratio == pytest.approx(expected, rel=1e-4)

    def test_sector_performance_has_all_tickers(self):
        prices = make_prices({"A": [100.0, 101.0], "B": [50.0, 51.0]})
        results = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000).run()
        assert "A" in results.sector_performance
        assert "B" in results.sector_performance

    def test_sector_win_rate_100_on_profitable_round_trip(self):
        # Buy at 100, sell at 110 → 1 win, win_rate == 100
        prices = make_prices({"A": [100.0, 110.0]})
        signals = [("BUY", 1_000.0), ("SELL", 1_000.0)]
        results = BacktestEngine(
            prices, ScriptedIndicator(signals), initial_capital=10_000
        ).run()
        perf = results.sector_performance["A"]
        assert perf["num_wins"] == 1
        assert perf["win_rate"] == pytest.approx(100.0)
        assert perf["num_trades"] == 2  # 1 buy + 1 sell

    def test_sector_pnl_weighted_avg_cost(self):
        """Multiple buys at different prices, then one sell — P&L uses WAC."""
        # Buy 50 shares at 100 ($5000), buy 50 shares at 80 ($4000)
        # Avg cost = (5000 + 4000) / 100 = 90
        # Sell 50 shares at 110 → pnl = (110 - 90) * 50 = $1000
        prices = make_prices({"A": [100.0, 80.0, 110.0]})
        signals = [("BUY", 5_000.0), ("BUY", 4_000.0), ("SELL", 5_500.0)]
        results = BacktestEngine(
            prices, ScriptedIndicator(signals), initial_capital=10_000
        ).run()
        perf = results.sector_performance["A"]
        # Realized: (110 - 90) * 50 = 1000
        # Unrealized: remaining 50 shares at price 110, avg_cost 90 → (110-90)*50 = 1000
        assert perf["pnl"] == pytest.approx(2_000.0)
        assert perf["num_wins"] == 1

    def test_sector_pnl_unequal_buy_sell_counts(self):
        """More buys than sells should not lose data (old zip bug)."""
        # 3 buys, 1 sell — old code would only pair first buy with first sell
        prices = make_prices({"A": [100.0, 95.0, 90.0, 110.0]})
        signals = [("BUY", 1_000.0), ("BUY", 950.0), ("BUY", 900.0), ("SELL", 3_000.0)]
        results = BacktestEngine(
            prices, ScriptedIndicator(signals), initial_capital=10_000
        ).run()
        perf = results.sector_performance["A"]
        assert perf["num_trades"] == 4  # 3 buys + 1 sell
        # avg cost = (1000 + 950 + 900) / (10 + 10 + 10) = 2850/30 = 95
        # sell 3000/110 ≈ 27.27 shares at 110, pnl = (110 - 95) * 27.27 ≈ 409.09
        assert perf["pnl"] > 0
        assert perf["num_wins"] == 1

    def test_sector_win_rate_mixed(self):
        """Some winning sells, some losing — verify correct ratio."""
        # Buy at 100, sell at 110 (win), buy at 120, sell at 100 (loss)
        prices = make_prices({"A": [100.0, 110.0, 120.0, 100.0]})
        signals = [("BUY", 1_000.0), ("SELL", 1_100.0), ("BUY", 1_200.0), ("SELL", 1_000.0)]
        results = BacktestEngine(
            prices, ScriptedIndicator(signals), initial_capital=10_000
        ).run()
        perf = results.sector_performance["A"]
        assert perf["num_wins"] == 1
        # 2 sells total → win_rate = 1/2 * 100 = 50%
        assert perf["win_rate"] == pytest.approx(50.0)

    def test_sector_unrealized_pnl(self):
        """Buy and hold to end — unrealized P&L should be included."""
        prices = make_prices({"A": [100.0, 120.0]})
        signals = [("BUY", 5_000.0), ("HOLD", 0.0)]
        results = BacktestEngine(
            prices, ScriptedIndicator(signals), initial_capital=10_000
        ).run()
        perf = results.sector_performance["A"]
        # 50 shares bought at 100, final price 120
        # unrealized = (120 - 100) * 50 = 1000
        assert perf["pnl"] == pytest.approx(1_000.0)
        assert perf["num_wins"] == 0  # no sells occurred

    def test_avg_invested_and_cash_pct_sum_to_100(self):
        prices = make_prices({"A": [100.0, 98.0, 102.0]})
        results = BacktestEngine(prices, BuyIndicator(500), initial_capital=10_000).run()
        assert results.avg_invested_pct + results.avg_cash_pct == pytest.approx(100.0)

    def test_went_negative_cash_false_by_default(self):
        prices = make_prices({"A": [100.0, 98.0]})
        results = BacktestEngine(prices, HoldIndicator(), initial_capital=10_000).run()
        assert results.went_negative_cash is False
