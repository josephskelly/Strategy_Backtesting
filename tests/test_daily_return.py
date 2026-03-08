"""
Unit tests for indicators/daily_return.py — Indicator class and signal logic.

All tests are pure: no network calls, no file I/O.
"""

import pandas as pd
import pytest

from indicators.daily_return import Indicator


# Shared dummy prices_history (not used by this indicator but required by signature)
_DUMMY_HISTORY = pd.Series([100.0, 98.0, 102.0])


def _signal(indicator, current, prev, position=0.0, cash=10_000.0, nlv=10_000.0):
    """Helper to call signal() with minimal boilerplate."""
    return indicator.signal(
        ticker="TEST",
        date=pd.Timestamp("2020-01-02"),
        current_price=current,
        prev_price=prev,
        prices_history=_DUMMY_HISTORY,
        position=position,
        cash=cash,
        nlv=nlv,
    )


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_default_nlv_pct(self):
        ind = Indicator()
        assert ind.nlv_pct_per_percent == pytest.approx(4.5)

    def test_default_no_cap(self):
        ind = Indicator()
        assert ind.margin_cap is None

    def test_cap_enabled(self):
        ind = Indicator(cap=True)
        assert ind.margin_cap == pytest.approx(0.25)

    def test_cap_disabled_explicitly(self):
        ind = Indicator(cap=False)
        assert ind.margin_cap is None

    def test_custom_nlv_pct(self):
        ind = Indicator(nlv_pct=2.5)
        assert ind.nlv_pct_per_percent == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# signal() — first bar / no-signal cases
# ---------------------------------------------------------------------------

class TestSignalNoTrade:
    def test_no_prev_price_returns_hold(self):
        ind = Indicator()
        action, value = _signal(ind, current=100.0, prev=None)
        assert action == "HOLD"
        assert value == pytest.approx(0.0)

    def test_zero_prev_price_returns_hold(self):
        ind = Indicator()
        action, value = _signal(ind, current=100.0, prev=0.0)
        assert action == "HOLD"
        assert value == pytest.approx(0.0)

    def test_flat_day_returns_hold(self):
        ind = Indicator()
        action, value = _signal(ind, current=100.0, prev=100.0)
        assert action == "HOLD"
        assert value == pytest.approx(0.0)

    def test_up_day_with_no_position_returns_hold(self):
        ind = Indicator()
        action, value = _signal(ind, current=102.0, prev=100.0, position=0.0)
        assert action == "HOLD"
        assert value == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# signal() — BUY signals
# ---------------------------------------------------------------------------

class TestSignalBuy:
    def test_down_day_returns_buy(self):
        ind = Indicator(nlv_pct=1.0)
        action, _ = _signal(ind, current=98.0, prev=100.0, nlv=10_000.0)
        assert action == "BUY"

    def test_buy_size_proportional_to_drop(self):
        # 2% drop, nlv_pct=1.0 → trade_amount = 1%×10000 = 100
        # trade_value = 2 × 100 = 200
        ind = Indicator(nlv_pct=1.0)
        _, value = _signal(ind, current=98.0, prev=100.0, nlv=10_000.0)
        assert value == pytest.approx(200.0, rel=1e-6)

    def test_buy_size_scales_with_nlv(self):
        ind = Indicator(nlv_pct=1.0)
        _, value_small = _signal(ind, current=98.0, prev=100.0, nlv=5_000.0)
        _, value_large = _signal(ind, current=98.0, prev=100.0, nlv=20_000.0)
        assert value_large == pytest.approx(value_small * 4, rel=1e-6)

    def test_buy_size_scales_with_nlv_pct(self):
        ind_lo = Indicator(nlv_pct=1.0)
        ind_hi = Indicator(nlv_pct=2.0)
        _, value_lo = _signal(ind_lo, current=98.0, prev=100.0, nlv=10_000.0)
        _, value_hi = _signal(ind_hi, current=98.0, prev=100.0, nlv=10_000.0)
        assert value_hi == pytest.approx(value_lo * 2, rel=1e-6)


# ---------------------------------------------------------------------------
# signal() — SELL signals
# ---------------------------------------------------------------------------

class TestSignalSell:
    def test_up_day_with_position_returns_sell(self):
        ind = Indicator()
        action, _ = _signal(ind, current=102.0, prev=100.0, position=5.0)
        assert action == "SELL"

    def test_sell_size_proportional_to_gain(self):
        # 1% gain, nlv_pct=1.0 → trade_amount = 100
        # trade_value = 1 × 100 = 100
        ind = Indicator(nlv_pct=1.0)
        _, value = _signal(ind, current=101.0, prev=100.0, position=5.0, nlv=10_000.0)
        assert value == pytest.approx(100.0, rel=1e-6)


# ---------------------------------------------------------------------------
# signal() — margin cap
# ---------------------------------------------------------------------------

class TestMarginCap:
    def test_cap_limits_buy_to_25pct_of_cash(self):
        # 5% drop × 1.65% NLV × $10000 = $825, but cash × 0.25 = $250
        ind = Indicator(nlv_pct=1.65, cap=True)
        _, value = _signal(
            ind, current=95.0, prev=100.0, cash=1_000.0, nlv=10_000.0
        )
        assert value == pytest.approx(250.0, rel=1e-6)

    def test_cap_does_not_restrict_small_buys(self):
        # 0.1% drop → very small trade, well under 25% cap
        ind = Indicator(nlv_pct=1.0, cap=True)
        _, value = _signal(
            ind, current=99.9, prev=100.0, cash=10_000.0, nlv=10_000.0
        )
        # uncapped = 0.1 × 100 = 10; cash cap = 2500 → uncapped wins
        assert value == pytest.approx(10.0, rel=1e-3)

    def test_cap_not_applied_without_flag(self):
        # Same scenario as above but no cap — larger trade allowed
        ind = Indicator(nlv_pct=1.65, cap=False)
        _, value_no_cap = _signal(
            ind, current=95.0, prev=100.0, cash=1_000.0, nlv=10_000.0
        )
        ind_cap = Indicator(nlv_pct=1.65, cap=True)
        _, value_cap = _signal(
            ind_cap, current=95.0, prev=100.0, cash=1_000.0, nlv=10_000.0
        )
        assert value_no_cap > value_cap

    def test_cap_with_zero_cash_does_not_cap_trade_value(self):
        # The indicator itself doesn't block trades when cash=0 — that's the engine's job.
        # When cash=0 and cap=True, the cap condition `cash > 0` is False, so the
        # uncapped trade_value is returned. The engine refuses to execute it.
        ind = Indicator(cap=True)
        action, value = _signal(ind, current=98.0, prev=100.0, cash=0.0, nlv=10_000.0)
        assert action == "BUY"
        assert value > 0

    def test_cap_not_applied_to_sells(self):
        # Sell signals should not be affected by the margin cap
        ind_cap = Indicator(cap=True)
        ind_no_cap = Indicator(cap=False)
        _, v_cap = _signal(ind_cap, current=102.0, prev=100.0, position=5.0, nlv=10_000.0)
        _, v_no_cap = _signal(ind_no_cap, current=102.0, prev=100.0, position=5.0, nlv=10_000.0)
        assert v_cap == pytest.approx(v_no_cap)
