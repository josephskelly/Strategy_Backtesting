"""
Z-Score Indicator

Mean-reversion strategy based on a rolling z-score:
  - BUY  when price falls >= z_threshold standard deviations below the rolling mean
  - SELL when price rises >= z_threshold standard deviations above the rolling mean

Position size is proportional to z-score strength (capped at max_allocation of NLV).

CLI flags added by this indicator:
  --lookback N          rolling window in bars (default: 20)
  --z-threshold F       buy/sell trigger (default: 1.0)
  --max-allocation F    max fraction of NLV per sector (default: 0.30)

Example usage (via backtest.py):
    python backtest.py TQQQ --indicator indicators/zscore.py
    python backtest.py TQQQ --indicator indicators/zscore.py --z-threshold 1.5 --lookback 30
"""


def add_args(parser) -> None:
    """Register indicator-specific CLI flags."""
    parser.add_argument(
        "--lookback",
        type=int,
        default=20,
        metavar="N",
        help="Rolling window (bars) for mean/std calculation (default: 20).",
    )
    parser.add_argument(
        "--z-threshold",
        type=float,
        default=1.0,
        metavar="F",
        help="Z-score magnitude to trigger buy/sell (default: 1.0).",
    )
    parser.add_argument(
        "--max-allocation",
        type=float,
        default=0.30,
        metavar="F",
        help="Max fraction of NLV to allocate per sector (default: 0.30).",
    )


class Indicator:
    """Rolling z-score mean-reversion indicator."""

    def __init__(self, **kwargs):
        self.lookback: int = kwargs.get("lookback", 20)
        self.z_threshold: float = kwargs.get("z_threshold", 1.0)
        self.max_allocation: float = kwargs.get("max_allocation", 0.30)

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

        Requires at least `lookback` bars of history.
        """
        if len(prices_history) < self.lookback:
            return ("HOLD", 0.0)

        window = prices_history.iloc[-self.lookback :]
        mean = float(window.mean())
        std = float(window.std())

        if std == 0:
            return ("HOLD", 0.0)

        z_score = (current_price - mean) / std

        # BUY: price is significantly below mean and no position held
        if position == 0 and z_score <= -self.z_threshold:
            available = min(cash, nlv * self.max_allocation)
            if available <= 0:
                return ("HOLD", 0.0)
            strength = min(abs(z_score) / self.z_threshold, 1.0)
            trade_value = available * strength
            return ("BUY", trade_value)

        # SELL: price is significantly above mean and position held
        if position > 0 and z_score >= self.z_threshold:
            trade_value = position * current_price  # sell entire position
            return ("SELL", trade_value)

        return ("HOLD", 0.0)
