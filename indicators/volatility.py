"""
Volatility-Targeting Indicator

Targets a position size equal to the current volatility index reading as a
percentage of NLV.  For example, VXN = 20 → hold 20% of NLV in TQQQ.

  - BUY  when current position value < target % of NLV
  - SELL when current position value > target % of NLV (requires --sell)
  - HOLD otherwise

The volatility series is pre-fetched in __init__ and looked up via asof()
so weekend/holiday gaps are handled automatically without engine changes.

CLI flags added by this indicator:
  --volatility-ticker SYM   volatility index to use (default: ^VXN)
  --sell                    enable selling when position exceeds target %

Example usage (via backtest.py):
    python backtest.py TQQQ --indicator indicators/volatility.py
    python backtest.py TQQQ --indicator indicators/volatility.py --sell
    python backtest.py TQQQ --indicator indicators/volatility.py --volatility-ticker ^VIX --sell
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    import argparse


def add_args(parser: argparse.ArgumentParser) -> None:
    """Register indicator-specific CLI flags."""
    parser.add_argument(
        "--volatility-ticker",
        type=str,
        default="^VXN",
        metavar="SYM",
        help="Volatility index ticker to use as position target (default: ^VXN).",
    )
    parser.add_argument(
        "--sell",
        action="store_true",
        help="Enable selling when position exceeds the volatility-target %%.",
    )


class Indicator:
    """Volatility-targeting indicator: hold vol_index%% of NLV in the position."""

    def __init__(self, **kwargs):
        self.vol_ticker: str = kwargs.get("volatility_ticker", "^VXN")
        self.sell_enabled: bool = kwargs.get("sell", False)

        # Lazy import avoids circular import — backtest.py loads indicators
        # dynamically via importlib after it is fully initialized.
        from backtest import fetch_closes

        vol_df = fetch_closes(self.vol_ticker, range_="30y", interval="1d")
        self.vol_series: pd.Series = vol_df[self.vol_ticker].ffill()

    def _get_vol(self, date: pd.Timestamp) -> float:
        """Return the most recent vol reading on or before date."""
        return float(self.vol_series.asof(date))

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

        Target position = vol_index_value% of NLV.
        Buys the gap if under-weight; sells the gap if over-weight (--sell only).
        """
        vol_value = self._get_vol(date)
        if pd.isna(vol_value):
            return ("HOLD", 0.0)

        target_value = (vol_value / 100.0) * nlv
        current_value = position * current_price

        if current_value < target_value:
            return ("BUY", target_value - current_value)

        if self.sell_enabled and current_value > target_value:
            return ("SELL", current_value - target_value)

        return ("HOLD", 0.0)
