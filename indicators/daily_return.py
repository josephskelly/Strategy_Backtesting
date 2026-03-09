"""
Daily Return Indicator

Mean-reversion strategy based on each day's price move:
  - BUY  when sector drops: size = abs(daily_return%) * trade_amount
  - SELL when sector rises (and position held): size = daily_return% * trade_amount

Trade amount is either a fixed $ per 1% move, or a % of current NLV.

CLI flags added by this indicator:
  --nlv-pct PCT        % of NLV to trade per 1% daily move (default: 4.5)
  --cap                cap each buy to 25% of current cash
  --hedge-pct PCT      % of NLV allocated to hedge ticker (default: 20.0, 0 to disable)
  --hedge-ticker SYM   inverse ETF to use as hedge (default: SQQQ)

When hedging is enabled the NLV is split: hedge_pct% to the hedge ticker, the
remainder to all other tickers. When running --all mode, if the primary ticker
happens to equal the hedge ticker it will receive the hedge weight (20%) rather
than the primary weight (80%) — acceptable limitation.

Example usage (via backtest.py):
    python backtest.py TQQQ --indicator indicators/daily_return.py
    python backtest.py TQQQ --indicator indicators/daily_return.py --nlv-pct 2.0 --cap
    python backtest.py TQQQ --hedge-pct 20 --hedge-ticker SQQQ
    python backtest.py TQQQ --hedge-pct 0
"""


from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

    import pandas as pd

DEFAULT_MARGIN_CAP: float = 0.25     # Max fraction of cash per buy when --cap is set


def add_args(parser: argparse.ArgumentParser) -> None:
    """Register indicator-specific CLI flags."""
    parser.add_argument(
        "--nlv-pct",
        type=float,
        default=4.5,
        metavar="PCT",
        help="Percent of NLV to trade per 1%% daily move (default: 4.5).",
    )
    parser.add_argument(
        "--cap",
        action="store_true",
        help=f"Cap each buy to at most {int(DEFAULT_MARGIN_CAP * 100)}%% of current cash.",
    )
    parser.add_argument(
        "--hedge-pct",
        type=float,
        default=0.0,
        metavar="PCT",
        help="Percent of NLV allocated to the hedge ticker (default: 0, disabled). Set > 0 to enable.",
    )
    parser.add_argument(
        "--hedge-ticker",
        type=str,
        default="SQQQ",
        metavar="TICKER",
        help="Inverse ETF to use as hedge (default: SQQQ).",
    )


class Indicator:
    """Buy dips, sell rips — sized as a fraction of NLV per 1%% daily move."""

    def __init__(self, **kwargs):
        self.nlv_pct_per_percent: float = kwargs.get("nlv_pct", 4.5)
        self.margin_cap: float | None = DEFAULT_MARGIN_CAP if kwargs.get("cap", False) else None
        self.hedge_pct: float = kwargs.get("hedge_pct", 0.0)
        self.hedge_ticker: str = (kwargs.get("hedge_ticker", "SQQQ") or "SQQQ").upper()

    def signal(
        self,
        ticker: str,
        date: pd.Timestamp,
        current_price: float,
        prev_price: float | None,
        prices_history: pd.Series,
        position: float,
        cash: float,
        nlv: float,
    ) -> tuple[str, float]:
        """
        Returns ('BUY'/'SELL'/'HOLD', trade_value_$).

        On the first bar (no prev_price) returns HOLD.
        """
        if prev_price is None or prev_price == 0:
            return ("HOLD", 0.0)

        daily_return_pct = (current_price - prev_price) / prev_price * 100

        hedge_fraction = self.hedge_pct / 100.0
        if self.hedge_pct > 0 and ticker == self.hedge_ticker:
            effective_fraction = hedge_fraction
        else:
            effective_fraction = 1.0 - hedge_fraction

        trade_amount = effective_fraction * (self.nlv_pct_per_percent / 100) * nlv

        if daily_return_pct < 0:
            trade_value = abs(daily_return_pct) * trade_amount
            if self.margin_cap is not None and cash > 0:
                trade_value = min(trade_value, cash * self.margin_cap)
            return ("BUY", trade_value)

        if daily_return_pct > 0 and position > 0:
            trade_value = daily_return_pct * trade_amount
            return ("SELL", trade_value)

        return ("HOLD", 0.0)
