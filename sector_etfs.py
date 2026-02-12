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


def analyze_daily_changes(range_: str = "1y") -> pd.DataFrame:
    """Compute daily percent change statistics over the given range.

    Returns a DataFrame with mean, median, std dev, min, max of daily
    percent changes for each sector ETF.
    """
    closes = fetch_sector_closes(range_=range_)
    daily_pct = closes.pct_change().dropna() * 100  # percent

    rows = []
    for ticker in daily_pct.columns:
        series = daily_pct[ticker].dropna()
        rows.append({
            "Sector": SECTOR_ETFS[ticker],
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


def position_sizing(capital: float = 10_000, months: int = 3,
                    trades_per_day: int = 1) -> dict:
    """Estimate per-trade allocation to spread capital over a period.

    Assumes ~21 trading days per month.
    """
    trading_days = months * 21
    total_trades = trading_days * trades_per_day
    per_trade = capital / total_trades

    return {
        "capital": capital,
        "months": months,
        "trading_days": trading_days,
        "trades_per_day": trades_per_day,
        "total_trades": total_trades,
        "per_trade": round(per_trade, 2),
    }


if __name__ == "__main__":
    print("=" * 70)
    print("  Vanguard Sector ETF — Daily % Change Statistics (1 Year)")
    print("=" * 70)

    stats = analyze_daily_changes(range_="1y")
    print(stats.to_string(index=False, float_format="%.4f"))

    print("\n")
    print("=" * 70)
    print("  Position Sizing — $10,000 over 3 months")
    print("=" * 70)

    sizing = position_sizing(capital=10_000, months=3)
    print(f"  Capital:          ${sizing['capital']:,.2f}")
    print(f"  Period:           {sizing['months']} months ({sizing['trading_days']} trading days)")
    print(f"  Trades/day:       {sizing['trades_per_day']}")
    print(f"  Total trades:     {sizing['total_trades']}")
    print(f"  Per-trade size:   ${sizing['per_trade']:,.2f}")
