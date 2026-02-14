"""
Leveraged ETF Tracker — fetch previous closing prices and daily percent changes
for 11 ultra/leveraged ETFs using Yahoo Finance.
"""

import time
import requests
import pandas as pd

LEVERAGED_ETFS = {
    "UCC": "Commodities (Ultra)",
    "UYG": "Financials (Ultra)",
    "LTL": "Long-Term Treasury (3x)",
    "DIG": "Oil & Gas (3x)",
    "UGE": "Renewable Energy (3x)",
    "ROM": "Real Estate (3x)",
    "UYM": "Metals & Mining (3x)",
    "RXL": "Healthcare (3x)",
    "UXI": "Semiconductors (2x)",
    "URE": "Real Estate (3x)",
    "UPW": "Utilities (3x)",
}


def _yahoo_chart(ticker: str, range_: str = "5d", interval: str = "1d") -> list[dict]:
    """Fetch OHLCV data from Yahoo Finance's chart API for a single ticker."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?range={range_}&interval={interval}"
    )
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    quotes = result["indicators"]["quote"][0]

    rows = []
    for i, ts in enumerate(timestamps):
        rows.append({
            "date": pd.Timestamp(ts, unit="s").normalize(),
            "close": quotes["close"][i],
        })
    return rows


def fetch_leveraged_closes(range_: str = "5d") -> pd.DataFrame:
    """Fetch recent closing prices for all 11 leveraged ETFs.

    Returns:
        DataFrame with columns = ticker symbols, rows = trading dates,
        values = closing prices.
    """
    closes = pd.DataFrame()

    for ticker in LEVERAGED_ETFS:
        rows = _yahoo_chart(ticker, range_=range_)
        df = pd.DataFrame(rows).set_index("date")
        closes[ticker] = df["close"]
        time.sleep(0.2)  # be polite to the API

    closes.index.name = "Date"
    return closes


def get_previous_close() -> pd.DataFrame:
    """Return a summary table with the most recent closing price and one-day
    percent change for every leveraged ETF, sorted by percent change."""
    closes = fetch_leveraged_closes(range_="5d")

    if len(closes) < 2:
        raise ValueError("Not enough trading data available (need at least 2 days).")

    latest = closes.iloc[-1]
    prior = closes.iloc[-2]
    pct_change = ((latest - prior) / prior) * 100

    latest_date = closes.index[-1].strftime("%Y-%m-%d")
    prior_date = closes.index[-2].strftime("%Y-%m-%d")

    summary = pd.DataFrame({
        "Sector": [LEVERAGED_ETFS[t] for t in closes.columns],
        "Ticker": list(closes.columns),
        f"Close ({prior_date})": prior.values,
        f"Close ({latest_date})": latest.values,
        "% Change": pct_change.values,
    })

    summary = summary.sort_values("% Change", ascending=False).reset_index(drop=True)
    return summary


def analyze_daily_changes(range_: str = "1y") -> pd.DataFrame:
    """Compute daily percent change statistics over the given range.

    Returns a DataFrame with mean, median, std dev, min, max of daily
    percent changes for each leveraged ETF.
    """
    closes = fetch_leveraged_closes(range_=range_)
    daily_pct = closes.pct_change().dropna() * 100  # percent

    rows = []
    for ticker in daily_pct.columns:
        series = daily_pct[ticker].dropna()
        rows.append({
            "Sector": LEVERAGED_ETFS[ticker],
            "Ticker": ticker,
            "Trading Days": len(series),
            "Mean Daily %": series.mean(),
            "Median Daily %": series.median(),
            "Std Dev %": series.std(),
            "Min Daily %": series.min(),
            "Max Daily %": series.max(),
        })

    stats = pd.DataFrame(rows)
    stats = stats.sort_values("Mean Daily %", ascending=False).reset_index(drop=True)
    return stats


if __name__ == "__main__":
    print("=" * 70)
    print("  Leveraged ETF — Daily % Change Statistics (1 Year)")
    print("=" * 70)

    stats = analyze_daily_changes(range_="1y")
    print(stats.to_string(index=False, float_format="%.4f"))
