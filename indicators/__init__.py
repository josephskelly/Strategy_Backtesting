# Indicator plugins for the backtesting engine.
#
# Each module here (or any custom .py file) must export:
#
#   class Indicator:
#       def __init__(self, **kwargs): ...
#       def signal(self, ticker, date, current_price, prev_price,
#                  prices_history, position, cash, nlv) -> tuple[str, float]: ...
#
#   def add_args(parser) -> None: ...   # optional
