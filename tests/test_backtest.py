"""
Unit tests for backtest.py utilities.

Tests _load_indicator_module(), fetch_closes(), and weekly resampling logic.
Network calls (_yahoo_chart) are patched with unittest.mock.
"""

import os
import sys
import tempfile
import textwrap

import pandas as pd
import pytest
from unittest.mock import patch

# Ensure repo root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backtest import _load_indicator_module, fetch_closes


# ---------------------------------------------------------------------------
# _load_indicator_module()
# ---------------------------------------------------------------------------

class TestLoadIndicatorModule:
    def test_load_daily_return(self):
        mod = _load_indicator_module("indicators/daily_return.py")
        assert hasattr(mod, "Indicator")

    def test_load_zscore(self):
        mod = _load_indicator_module("indicators/zscore.py")
        assert hasattr(mod, "Indicator")

    def test_loaded_indicator_has_add_args(self):
        mod = _load_indicator_module("indicators/daily_return.py")
        assert hasattr(mod, "add_args")
        assert callable(mod.add_args)

    def test_missing_file_exits(self):
        with pytest.raises(SystemExit):
            _load_indicator_module("nonexistent/indicator.py")

    def test_file_without_indicator_class_exits(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("# no Indicator class here\n")
            path = f.name
        try:
            with pytest.raises(SystemExit):
                _load_indicator_module(path)
        finally:
            os.unlink(path)

    def test_custom_indicator_instantiable(self):
        src = textwrap.dedent("""
            class Indicator:
                def __init__(self, **kwargs):
                    self.called = True
                def signal(self, **kwargs):
                    return ("HOLD", 0.0)
        """)
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            path = f.name
        try:
            mod = _load_indicator_module(path)
            ind = mod.Indicator()
            assert ind.called is True
            assert ind.signal() == ("HOLD", 0.0)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# fetch_closes() — patching _yahoo_chart
# ---------------------------------------------------------------------------

class TestFetchCloses:
    def _mock_yahoo_rows(self):
        """Fake rows as returned by _yahoo_chart()."""
        return [
            {"date": pd.Timestamp("2020-01-03"), "close": 100.0},
            {"date": pd.Timestamp("2020-01-06"), "close": 102.0},
            {"date": pd.Timestamp("2020-01-02"), "close": 99.0},   # out of order
        ]

    def test_returns_dataframe(self):
        with patch("backtest._yahoo_chart", return_value=self._mock_yahoo_rows()):
            df = fetch_closes("TQQQ", range_="5y", interval="1d")
        assert isinstance(df, pd.DataFrame)

    def test_column_is_ticker(self):
        with patch("backtest._yahoo_chart", return_value=self._mock_yahoo_rows()):
            df = fetch_closes("TQQQ")
        assert list(df.columns) == ["TQQQ"]

    def test_sorted_by_date(self):
        with patch("backtest._yahoo_chart", return_value=self._mock_yahoo_rows()):
            df = fetch_closes("TQQQ")
        assert df.index.is_monotonic_increasing

    def test_correct_row_count(self):
        with patch("backtest._yahoo_chart", return_value=self._mock_yahoo_rows()):
            df = fetch_closes("TQQQ")
        assert len(df) == 3

    def test_correct_values(self):
        with patch("backtest._yahoo_chart", return_value=self._mock_yahoo_rows()):
            df = fetch_closes("TQQQ")
        # After sort: 2020-01-02=99, 2020-01-03=100, 2020-01-06=102
        assert df["TQQQ"].iloc[0] == pytest.approx(99.0)
        assert df["TQQQ"].iloc[2] == pytest.approx(102.0)


# ---------------------------------------------------------------------------
# Weekly resampling (logic from run_single)
# ---------------------------------------------------------------------------

class TestWeeklyResample:
    def _make_daily(self, n_days: int = 10) -> pd.DataFrame:
        dates = pd.bdate_range("2020-01-06", periods=n_days)
        data = {
            "positions_value": range(n_days),
            "cash": [10_000.0] * n_days,
            "net_liq": [10_000.0 + i for i in range(n_days)],
        }
        return pd.DataFrame(data, index=dates)

    def test_resamples_to_weekly(self):
        daily = self._make_daily(10)
        weekly = daily.resample("W-FRI").last().dropna()
        assert len(weekly) <= len(daily)
        # Fridays only
        assert all(d.dayofweek == 4 for d in weekly.index)

    def test_weekly_uses_last_value_of_week(self):
        # 5 business days starting Monday 2020-01-06 → Friday 2020-01-10
        daily = self._make_daily(5)
        weekly = daily.resample("W-FRI").last().dropna()
        # Friday's value should be the last row's value
        assert weekly["net_liq"].iloc[0] == pytest.approx(10_004.0)

    def test_two_weeks_produces_two_rows(self):
        daily = self._make_daily(10)  # Mon–Fri week 1 + Mon–Fri week 2
        weekly = daily.resample("W-FRI").last().dropna()
        assert len(weekly) == 2
