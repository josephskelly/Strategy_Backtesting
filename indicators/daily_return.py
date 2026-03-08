"""
Daily Return Indicator

Mean-reversion strategy based on each day's price move:
  - BUY  when sector drops: size = abs(daily_return%) * trade_amount
  - SELL when sector rises (and position held): size = daily_return% * trade_amount

Trade amount is either a fixed $ per 1% move, or a % of current NLV.

CLI flags added by this indicator:
  --nlv-pct PCT     % of NLV to trade per 1% daily move (default: 1.65)
  --cap             cap each buy to 25% of current cash

Example usage (via backtest.py):
    python backtest.py TQQQ --indicator indicators/daily_return.py
    python backtest.py TQQQ --indicator indicators/daily_return.py --nlv-pct 2.0 --cap
"""


def add_args(parser) -> None:
    """Register indicator-specific CLI flags."""
    parser.add_argument(
        "--nlv-pct",
        type=float,
        default=1.65,
        metavar="PCT",
        help="Percent of NLV to trade per 1%% daily move (default: 1.65).",
    )
    parser.add_argument(
        "--cap",
        action="store_true",
        help="Cap each buy to at most 25%% of current cash.",
    )


class Indicator:
    """Buy dips, sell rips — sized as a fraction of NLV per 1%% daily move."""

    def __init__(self, **kwargs):
        self.nlv_pct_per_percent: float = kwargs.get("nlv_pct", 1.65)
        self.margin_cap: float | None = 0.25 if kwargs.get("cap", False) else None

    def signal(
        self,
        ticker: str,
        date,
        current_price: float,
        prev_price: float | None,
        prices_history,
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
        trade_amount = (self.nlv_pct_per_percent / 100) * nlv

        if daily_return_pct < 0:
            trade_value = abs(daily_return_pct) * trade_amount
            if self.margin_cap is not None and cash > 0:
                trade_value = min(trade_value, cash * self.margin_cap)
            return ("BUY", trade_value)

        if daily_return_pct > 0 and position > 0:
            trade_value = daily_return_pct * trade_amount
            return ("SELL", trade_value)

        return ("HOLD", 0.0)
