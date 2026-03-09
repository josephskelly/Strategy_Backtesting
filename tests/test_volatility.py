"""
Unit tests for indicators/volatility.py.

All tests mock `indicators.volatility.fetch_closes` to avoid network calls.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from indicators.volatility import Indicator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_indicator(
    vol_data: dict[str, float],
    vol_ticker: str = "^VXN",
    sell: bool = False,
) -> Indicator:
    """Build Indicator with a mocked vol_series.

    vol_data: {date_str: float} mapping of volatility readings.
    """
    dates = pd.to_datetime(list(vol_data.keys()))
    values = list(vol_data.values())
    vol_df = pd.DataFrame({vol_ticker: pd.Series(values, index=dates)})
    with patch("backtest.fetch_closes") as mock_fetch:
        mock_fetch.return_value = vol_df
        return Indicator(volatility_ticker=vol_ticker, sell=sell)


def _signal(
    indicator: Indicator,
    ticker: str = "TQQQ",
    date: str = "2024-01-02",
    current_price: float = 100.0,
    prev_price: float | None = 99.0,
    prices_history: pd.Series | None = None,
    position: float = 0.0,
    cash: float = 10_000.0,
    nlv: float = 10_000.0,
) -> tuple[str, float]:
    return indicator.signal(
        ticker=ticker,
        date=pd.Timestamp(date),
        current_price=current_price,
        prev_price=prev_price,
        prices_history=prices_history if prices_history is not None else pd.Series(dtype=float),
        position=position,
        cash=cash,
        nlv=nlv,
    )


# ---------------------------------------------------------------------------
# TestInit
# ---------------------------------------------------------------------------

class TestInit:
    def test_default_vol_ticker(self):
        ind = _make_indicator({"2024-01-02": 20.0})
        assert ind.vol_ticker == "^VXN"

    def test_custom_vol_ticker(self):
        ind = _make_indicator({"2024-01-02": 20.0}, vol_ticker="^VIX")
        assert ind.vol_ticker == "^VIX"

    def test_sell_disabled_by_default(self):
        ind = _make_indicator({"2024-01-02": 20.0})
        assert ind.sell_enabled is False

    def test_sell_enabled_flag(self):
        ind = _make_indicator({"2024-01-02": 20.0}, sell=True)
        assert ind.sell_enabled is True


# ---------------------------------------------------------------------------
# TestHoldCases
# ---------------------------------------------------------------------------

class TestHoldCases:
    def test_hold_when_vol_nan(self):
        """Date before vol series start → asof() returns NaN → HOLD."""
        ind = _make_indicator({"2024-01-02": 20.0})
        action, value = _signal(ind, date="2020-01-01")
        assert action == "HOLD"
        assert value == 0.0

    def test_hold_when_at_target(self):
        """current_value == target_value → neither BUY nor SELL → HOLD."""
        # vol=20, nlv=10_000 → target=$2000; 20 shares @ $100 = $2000
        ind = _make_indicator({"2024-01-02": 20.0})
        action, value = _signal(ind, date="2024-01-02", position=20.0, nlv=10_000.0)
        assert action == "HOLD"

    def test_hold_when_above_target_sell_disabled(self):
        """Position exceeds target but sell=False → HOLD."""
        # vol=10, nlv=10_000 → target=$1000; 20 shares @ $100 = $2000 > target
        ind = _make_indicator({"2024-01-02": 10.0}, sell=False)
        action, value = _signal(ind, date="2024-01-02", position=20.0, nlv=10_000.0)
        assert action == "HOLD"


# ---------------------------------------------------------------------------
# TestBuySignal
# ---------------------------------------------------------------------------

class TestBuySignal:
    def test_buy_when_below_target(self):
        """No position held, vol=20 → BUY full target ($2000)."""
        ind = _make_indicator({"2024-01-02": 20.0})
        action, value = _signal(ind, date="2024-01-02", position=0.0, nlv=10_000.0)
        assert action == "BUY"
        assert value == pytest.approx(2_000.0)

    def test_buy_amount_is_gap(self):
        """Partial position held → BUY only the gap to target."""
        # vol=30, nlv=10_000 → target=$3000; 10 shares @ $100 = $1000 → BUY $2000
        ind = _make_indicator({"2024-01-02": 30.0})
        action, value = _signal(ind, date="2024-01-02", position=10.0, nlv=10_000.0)
        assert action == "BUY"
        assert value == pytest.approx(2_000.0)

    def test_buy_uses_asof_for_missing_dates(self):
        """Vol indexed on 2024-01-02; signal called on 2024-01-03 → asof() returns prior value."""
        ind = _make_indicator({"2024-01-02": 20.0})
        action, value = _signal(ind, date="2024-01-03", position=0.0, nlv=10_000.0)
        assert action == "BUY"
        assert value == pytest.approx(2_000.0)


# ---------------------------------------------------------------------------
# TestSellSignal
# ---------------------------------------------------------------------------

class TestSellSignal:
    def test_sell_when_above_target_sell_enabled(self):
        """Position exceeds target with sell=True → SELL the gap."""
        # vol=10, nlv=10_000 → target=$1000; 20 shares @ $100 = $2000 → SELL $1000
        ind = _make_indicator({"2024-01-02": 10.0}, sell=True)
        action, value = _signal(ind, date="2024-01-02", position=20.0, nlv=10_000.0)
        assert action == "SELL"
        assert value == pytest.approx(1_000.0)

    def test_no_sell_when_sell_disabled(self):
        """Same over-target scenario but sell=False → HOLD."""
        ind = _make_indicator({"2024-01-02": 10.0}, sell=False)
        action, value = _signal(ind, date="2024-01-02", position=20.0, nlv=10_000.0)
        assert action == "HOLD"

    def test_sell_amount_is_gap(self):
        """Sell value equals current_value - target_value exactly."""
        # vol=20, nlv=10_000 → target=$2000; 30 shares @ $100 = $3000 → SELL $1000
        ind = _make_indicator({"2024-01-02": 20.0}, sell=True)
        action, value = _signal(ind, date="2024-01-02", position=30.0, nlv=10_000.0)
        assert action == "SELL"
        assert value == pytest.approx(1_000.0)


# ---------------------------------------------------------------------------
# TestVolLookup
# ---------------------------------------------------------------------------

class TestVolLookup:
    def test_returns_hold_for_pre_series_date(self):
        """Date before vol series start → asof() returns NaN → HOLD."""
        ind = _make_indicator({"2024-01-02": 20.0})
        action, value = _signal(ind, date="2023-01-01")
        assert action == "HOLD"
        assert value == 0.0

    def test_uses_ffill_for_gaps(self):
        """Vol series has a gap; signal on gap date returns most recent prior value."""
        # Series has only 2024-01-02; 2024-01-03 falls in a gap → asof returns 20.0
        ind = _make_indicator({"2024-01-02": 20.0})
        action, value = _signal(ind, date="2024-01-03", position=0.0, nlv=10_000.0)
        assert action == "BUY"
        assert value == pytest.approx(2_000.0)
