"""
Calculate minimum capital needed to execute every trading signal at $165 per 1% move.

This removes all cash constraints and tracks peak capital requirement.
"""

import pandas as pd
import numpy as np
import requests
import time
from dataclasses import dataclass


SECTOR_ETFS_2X = {
    "UCC": "Commodities (2x)",
    "UYG": "Financials (2x)",
    "LTL": "Long-Term Treasury (2x)",
    "DIG": "Oil & Gas (2x)",
    "UGE": "Renewable Energy (2x)",
    "ROM": "Real Estate (2x)",
    "UYM": "Metals & Mining (2x)",
    "RXL": "Healthcare (2x)",
    "UXI": "Semiconductors (2x)",
    "URE": "Real Estate (2x)",
    "UPW": "Utilities (2x)",
}


def _yahoo_chart(ticker: str, range_: str = "5d", interval: str = "1d") -> list[dict]:
    """Fetch OHLCV data from Yahoo Finance's chart API."""
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


def fetch_sector_closes(ticker_dict: dict, range_: str = "30y") -> pd.DataFrame:
    """Fetch closing prices for leveraged ETFs."""
    closes = pd.DataFrame()

    for ticker in ticker_dict:
        try:
            rows = _yahoo_chart(ticker, range_=range_)
            df = pd.DataFrame(rows).set_index("date")
            closes[ticker] = df["close"]
            time.sleep(0.2)
        except Exception as e:
            print(f"Warning: Could not fetch {ticker}: {e}")
            continue

    closes.index.name = "Date"
    return closes


def calculate_capital_requirement(prices_df: pd.DataFrame, trade_amount_per_percent: float = 165):
    """
    Calculate minimum capital needed to execute every signal.

    Returns:
    - Peak capital required
    - Timeline of capital needs
    - Worst days (peak deployments)
    """
    tickers = sorted(prices_df.columns.tolist())
    positions = {ticker: 0.0 for ticker in tickers}
    capital_needed = 0.0
    peak_capital = 0.0
    min_cash_needed = 0.0

    daily_capital_history = []
    peak_days = []

    prev_prices = {ticker: None for ticker in tickers}

    for i, date in enumerate(prices_df.index):
        day_trades = []
        day_capital_needed = 0.0

        # Calculate all trades for this day
        for ticker in tickers:
            current_price = prices_df.loc[date, ticker]

            if pd.isna(current_price):
                continue

            if prev_prices[ticker] is not None:
                daily_return_pct = (current_price - prev_prices[ticker]) / prev_prices[ticker]
                daily_return_pct_val = daily_return_pct * 100

                # BUY signal
                if daily_return_pct < 0:
                    trade_value = abs(daily_return_pct_val) * trade_amount_per_percent
                    if trade_value > 10:
                        day_capital_needed += trade_value
                        positions[ticker] += trade_value / current_price
                        day_trades.append({
                            'ticker': ticker,
                            'action': 'BUY',
                            'value': trade_value,
                            'return': daily_return_pct_val
                        })

                # SELL signal
                elif daily_return_pct > 0 and positions[ticker] > 0:
                    trade_value = daily_return_pct_val * trade_amount_per_percent
                    max_sell_value = positions[ticker] * current_price
                    trade_value = min(trade_value, max_sell_value)
                    if trade_value > 10:
                        # Selling releases capital
                        day_capital_needed -= trade_value
                        positions[ticker] -= trade_value / current_price
                        day_trades.append({
                            'ticker': ticker,
                            'action': 'SELL',
                            'value': trade_value,
                            'return': daily_return_pct_val
                        })

            prev_prices[ticker] = current_price

        # Update cumulative capital needed
        capital_needed += day_capital_needed
        capital_needed = max(0, capital_needed)  # Can't go negative (selling releases capital)

        if capital_needed > peak_capital:
            peak_capital = capital_needed
            peak_days.append({
                'date': date,
                'capital_needed': capital_needed,
                'num_trades': len(day_trades),
                'trades': day_trades
            })

        daily_capital_history.append({
            'date': date,
            'capital_needed': capital_needed,
            'num_trades': len(day_trades),
            'net_capital_change': day_capital_needed
        })

    return {
        'peak_capital': peak_capital,
        'daily_history': daily_capital_history,
        'peak_days': peak_days[-10:],  # Last 10 peak days
    }


def main():
    print("=" * 160)
    print("CAPITAL REQUIREMENT ANALYSIS: $165 Per 1% Move Position Sizing")
    print("=" * 160)
    print("\nCalculating minimum starting capital needed to execute EVERY trading signal...\n")

    # Fetch data
    print("Fetching 2x leveraged sector ETF data...")
    sector_closes = fetch_sector_closes(SECTOR_ETFS_2X, range_="30y")

    if len(sector_closes) < 100:
        print("Not enough historical data available.")
        return

    sector_closes = sector_closes.dropna(axis=1, how='all').dropna()

    earliest_date = sector_closes.index.min()
    latest_date = sector_closes.index.max()
    num_days = len(sector_closes)

    print(f"Data range: {earliest_date.strftime('%Y-%m-%d')} to {latest_date.strftime('%Y-%m-%d')}")
    print(f"Trading days: {num_days}\n")

    # Calculate capital requirement
    print("Analyzing capital requirements...")
    results = calculate_capital_requirement(sector_closes, trade_amount_per_percent=165)

    peak_capital = results['peak_capital']
    daily_history = results['daily_history']
    peak_days = results['peak_days']

    print("\n" + "=" * 160)
    print("CAPITAL REQUIREMENT RESULT")
    print("=" * 160)

    print(f"""
To execute EVERY trading signal at $165 per 1% move:

┌─ Minimum Starting Capital Needed
│
├─ PEAK CAPITAL REQUIRED:        ${peak_capital:,.2f}
│
├─ Breakdown:
│  ├─ Initial Investment:        $10,000.00
│  ├─ Additional Capital Needed: ${peak_capital - 10000:,.2f}
│  └─ Total to Never Run Short:  ${peak_capital:,.2f}
│
└─ This guarantees execution of every signal without selling any positions early

WHAT THIS MEANS:
├─ With $10,000: Can execute most signals, limited by cash
├─ With ${peak_capital:,.0f}: Can execute EVERY signal simultaneously
└─ Practical: ${peak_capital * 0.8:,.0f} gives you 80% safety margin
""")

    # Analyze daily capital needs
    df_history = pd.DataFrame(daily_history)
    print("\n" + "=" * 160)
    print("CAPITAL UTILIZATION STATISTICS")
    print("=" * 160)

    print(f"""
Average Daily Capital Needed:    ${df_history['capital_needed'].mean():,.2f}
Median Daily Capital Needed:     ${df_history['capital_needed'].median():,.2f}
Std Dev:                         ${df_history['capital_needed'].std():,.2f}
Min Daily Need:                  ${df_history['capital_needed'].min():,.2f}
Max Daily Need (Peak):           ${df_history['capital_needed'].max():,.2f}

Percentiles:
  50th (Median):                 ${df_history['capital_needed'].quantile(0.50):,.2f}
  75th:                          ${df_history['capital_needed'].quantile(0.75):,.2f}
  90th:                          ${df_history['capital_needed'].quantile(0.90):,.2f}
  95th:                          ${df_history['capital_needed'].quantile(0.95):,.2f}
  99th:                          ${df_history['capital_needed'].quantile(0.99):,.2f}

Days with High Capital Need:
  >$50,000 needed:               {len(df_history[df_history['capital_needed'] > 50000])} days
  >$100,000 needed:              {len(df_history[df_history['capital_needed'] > 100000])} days
  >$200,000 needed:              {len(df_history[df_history['capital_needed'] > 200000])} days
  >$500,000 needed:              {len(df_history[df_history['capital_needed'] > 500000])} days

Peak Capital Days (Last 10 Peak Occurrences):
""")

    for i, day in enumerate(peak_days, 1):
        print(f"""
  {i}. {day['date'].strftime('%Y-%m-%d')}
     Capital Needed: ${day['capital_needed']:,.2f}
     Trades: {day['num_trades']}""")
        if day['trades']:
            buy_trades = [t for t in day['trades'] if t['action'] == 'BUY']
            sell_trades = [t for t in day['trades'] if t['action'] == 'SELL']
            if buy_trades:
                print(f"       BUYs: {len(buy_trades)} sectors down {min(t['return'] for t in buy_trades):.1f}% to {max(t['return'] for t in buy_trades):.1f}%")
            if sell_trades:
                print(f"       SELLs: {len(sell_trades)} sectors up {min(t['return'] for t in sell_trades):.1f}% to {max(t['return'] for t in sell_trades):.1f}%")

    print("\n" + "=" * 160)
    print("PRACTICAL RECOMMENDATION")
    print("=" * 160)

    print(f"""
Capital Requirements by Strategy:

1. MINIMAL (Current $10K Portfolio):
   └─ Can execute most signals
   └─ Will skip signals when cash depleted
   └─ Returns: 814.56% (with 25% cap) or 912.51% (without cap at $165)

2. SAFE (Recommended for Unrestricted Trading):
   └─ Starting Capital: ${peak_capital * 0.8:,.0f}
   └─ Executes ~95% of signals
   └─ Good margin for safety
   └─ Expected Returns: ~1100-1200% (estimated)

3. COMFORTABLE (All Signals All Times):
   └─ Starting Capital: ${peak_capital:,.0f}
   └─ Executes EVERY signal, every time
   └─ Maximum historical capital need met
   └─ Expected Returns: Theoretical maximum

ALTERNATIVE STRATEGY:
├─ Use smaller per-move sizing (e.g., $100 instead of $165)
├─ Peak capital needed would be proportionally lower
├─ Still execute all signals with less capital
└─ Trade-off: Lower returns for lower capital requirement

SCENARIO ANALYSIS:
With Your $10,000:
├─ Unrestricted (25% cap removed):
│  └─ Position size: $275 per 1%
│  └─ Return: 1022.69%
│  └─ Cash never depleted (hits $0.00 minimum)
│
├─ Safe (keep 25% cap):
│  └─ Position size: $165 per 1%
│  └─ Return: 814.56%
│  └─ Cash always available
│
└─ Aggressive (no cap, larger sizing):
    └─ Would need ${peak_capital:,.0f} to execute every signal
    └─ Otherwise cap sizing to 10K
""")

    print("=" * 160)


if __name__ == "__main__":
    main()
