"""Shared test fixtures and helpers."""

import pandas as pd


def make_prices(data: dict, start: str = "2020-01-02") -> pd.DataFrame:
    """
    Build a prices DataFrame from a dict of {ticker: [price, price, ...]}.

    Uses business-day dates starting from `start`.

    Example:
        make_prices({"TQQQ": [100.0, 98.0, 102.0, 99.0]})
    """
    n = len(next(iter(data.values())))
    dates = pd.bdate_range(start, periods=n)
    return pd.DataFrame(data, index=dates)
