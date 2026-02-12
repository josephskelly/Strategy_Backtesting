"""
Sector ETF Tracker — fetch previous closing prices and daily percent changes
for the 11 Vanguard sector ETFs using Yahoo Finance.
"""

import time
import requests
import pandas as pd

SECTOR_ETFS = {
    "VGT": "Information Technology",
    "VHT": "Health Care",
    "VFH": "Financials",
    "VCR": "Consumer Discretionary",
    "VDC": "Consumer Staples",
    "VDE": "Energy",
    "VIS": "Industrials",
    "VOX": "Communication Services",
    "VNQ": "Real Estate",
    "VAW": "Materials",
    "VPU": "Utilities",
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


def fetch_sector_closes(range_: str = "5d") -> pd.DataFrame:
    """Fetch recent closing prices for all 11 sector ETFs.

    Returns:
        DataFrame with columns = ticker symbols, rows = trading dates,
        values = closing prices.
    """
    closes = pd.DataFrame()

    for ticker in SECTOR_ETFS:
        rows = _yahoo_chart(ticker, range_=range_)
        df = pd.DataFrame(rows).set_index("date")
        closes[ticker] = df["close"]
        time.sleep(0.2)  # be polite to the API

    closes.index.name = "Date"
    return closes


def get_previous_close() -> pd.DataFrame:
    """Return a summary table with the most recent closing price and one-day
    percent change for every sector ETF, sorted by percent change."""
    closes = fetch_sector_closes(range_="5d")

    if len(closes) < 2:
        raise ValueError("Not enough trading data available (need at least 2 days).")

    latest = closes.iloc[-1]
    prior = closes.iloc[-2]
    pct_change = ((latest - prior) / prior) * 100

    latest_date = closes.index[-1].strftime("%Y-%m-%d")
    prior_date = closes.index[-2].strftime("%Y-%m-%d")

    summary = pd.DataFrame({
        "Sector": [SECTOR_ETFS[t] for t in closes.columns],
        "Ticker": list(closes.columns),
        f"Close ({prior_date})": prior.values,
        f"Close ({latest_date})": latest.values,
        "% Change": pct_change.values,
    })

    summary = summary.sort_values("% Change", ascending=False).reset_index(drop=True)
    return summary


if __name__ == "__main__":
    print("Fetching Vanguard Sector ETF data...\n")
    summary = get_previous_close()
    print(summary.to_string(index=False, float_format="%.2f"))
