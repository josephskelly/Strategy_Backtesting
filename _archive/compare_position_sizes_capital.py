"""
Capital requirement for $100 per 1% move (no cap on position size).

Compare capital needs across different position sizing strategies.
"""

import pandas as pd
import numpy as np
import requests
import time


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


def calculate_capital_requirement(prices_df: pd.DataFrame, trade_amount_per_percent: float):
    """Calculate minimum capital needed to execute every signal."""
    tickers = sorted(prices_df.columns.tolist())
    positions = {ticker: 0.0 for ticker in tickers}
    capital_needed = 0.0
    peak_capital = 0.0

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
        capital_needed = max(0, capital_needed)

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
        })

    df_history = pd.DataFrame(daily_capital_history)

    return {
        'peak_capital': peak_capital,
        'daily_history': df_history,
        'peak_days': peak_days[-3:],
        'median': df_history['capital_needed'].median(),
        'p90': df_history['capital_needed'].quantile(0.90),
        'p95': df_history['capital_needed'].quantile(0.95),
        'p99': df_history['capital_needed'].quantile(0.99),
        'avg': df_history['capital_needed'].mean(),
        'days_over_50k': len(df_history[df_history['capital_needed'] > 50000]),
        'days_over_100k': len(df_history[df_history['capital_needed'] > 100000]),
        'days_over_200k': len(df_history[df_history['capital_needed'] > 200000]),
    }


def main():
    print("=" * 200)
    print("CAPITAL REQUIREMENT COMPARISON: Different Position Sizes (No Cap)")
    print("=" * 200)
    print("\nFetching data...")
    sector_closes = fetch_sector_closes(SECTOR_ETFS_2X, range_="30y")

    if len(sector_closes) < 100:
        print("Not enough data.")
        return

    sector_closes = sector_closes.dropna(axis=1, how='all').dropna()

    print(f"Data: {sector_closes.index.min().strftime('%Y-%m-%d')} to {sector_closes.index.max().strftime('%Y-%m-%d')}\n")

    # Test different position sizes
    position_sizes = [100, 125, 150, 165, 175, 200, 225, 250, 275, 300]

    print("Calculating capital requirements...\n")

    results = {}
    for pos_size in position_sizes:
        print(f"  ${pos_size}/1%...", end=" ", flush=True)
        result = calculate_capital_requirement(sector_closes, trade_amount_per_percent=pos_size)
        results[pos_size] = result
        print(f"Peak: ${result['peak_capital']:,.0f}")

    # Display comparison table
    print("\n" + "=" * 200)
    print("CAPITAL REQUIREMENT COMPARISON TABLE")
    print("=" * 200)

    comparison = []
    for pos_size in position_sizes:
        r = results[pos_size]
        comparison.append({
            'Position Size': f"${pos_size}",
            'Peak Capital': f"${r['peak_capital']:,.0f}",
            'Median': f"${r['median']:,.0f}",
            '90th %ile': f"${r['p90']:,.0f}",
            '99th %ile': f"${r['p99']:,.0f}",
            'Avg': f"${r['avg']:,.0f}",
            'Days >$100K': r['days_over_100k'],
            'Days >$200K': r['days_over_200k'],
        })

    df_comp = pd.DataFrame(comparison)
    print(f"\n{df_comp.to_string(index=False)}\n")

    # Detailed focus on $100
    print("=" * 200)
    print("FOCUS: $100 Per 1% Move (No Cap)")
    print("=" * 200)

    r100 = results[100]
    print(f"""
Peak Capital Needed:               ${r100['peak_capital']:,.2f}
Median Day:                        ${r100['median']:,.2f}
90th Percentile:                   ${r100['p90']:,.2f}
99th Percentile:                   ${r100['p99']:,.2f}
Average Day:                       ${r100['avg']:,.2f}

Days Needing High Capital:
  >$50,000:                        {len([d for d in r100['daily_history']['capital_needed'] if d > 50000])} days ({len([d for d in r100['daily_history']['capital_needed'] if d > 50000])/len(r100['daily_history'])*100:.1f}%)
  >$100,000:                       {r100['days_over_100k']} days ({r100['days_over_100k']/len(r100['daily_history'])*100:.1f}%)
  >$150,000:                       {len([d for d in r100['daily_history']['capital_needed'] if d > 150000])} days
  >$200,000:                       {r100['days_over_200k']} days
""")

    # Comparison of $100 vs $165
    r165 = results[165]
    print("=" * 200)
    print("COMPARISON: $100 vs $165 Per 1% Move")
    print("=" * 200)

    print(f"""
                           $100/1%              $165/1%            Difference
────────────────────────────────────────────────────────────────────────────────
Peak Capital              ${r100['peak_capital']:>13,.0f}      ${r165['peak_capital']:>13,.0f}      {r165['peak_capital'] - r100['peak_capital']:>+13,.0f}
                                                                       ({(r165['peak_capital']/r100['peak_capital'] - 1)*100:+.1f}%)

Median Day                ${r100['median']:>13,.0f}      ${r165['median']:>13,.0f}      {r165['median'] - r100['median']:>+13,.0f}
90th Percentile           ${r100['p90']:>13,.0f}      ${r165['p90']:>13,.0f}      {r165['p90'] - r100['p90']:>+13,.0f}
99th Percentile           ${r100['p99']:>13,.0f}      ${r165['p99']:>13,.0f}      {r165['p99'] - r100['p99']:>+13,.0f}

Days >$100K               {r100['days_over_100k']:>18}      {r165['days_over_100k']:>18}      {r165['days_over_100k'] - r100['days_over_100k']:>+18}
Days >$200K               {r100['days_over_200k']:>18}      {r165['days_over_200k']:>18}      {r165['days_over_200k'] - r100['days_over_200k']:>+18}
""")

    # Scaling analysis
    print("=" * 200)
    print("CAPITAL SCALING ANALYSIS")
    print("=" * 200)

    baseline_100 = results[100]['peak_capital']
    print(f"\nBased on $100/1% peak requirement of ${baseline_100:,.0f}:\n")

    scaling = []
    for pos_size in position_sizes:
        r = results[pos_size]
        ratio = r['peak_capital'] / baseline_100
        expected = baseline_100 * (pos_size / 100)
        scaling.append({
            'Position Size': f"${pos_size}",
            'Peak Capital': f"${r['peak_capital']:,.0f}",
            'Ratio to $100': f"{ratio:.3f}x",
            'Linear Expectation': f"${expected:,.0f}",
            'Extra %': f"{(ratio - pos_size/100)*100:+.1f}%"
        })

    df_scaling = pd.DataFrame(scaling)
    print(f"{df_scaling.to_string(index=False)}\n")

    # Practical recommendations
    print("=" * 200)
    print("PRACTICAL CAPITAL REQUIREMENTS")
    print("=" * 200)

    print(f"""
Using $100 Per 1% Move (No Cap):

MINIMUM TO START:
  • Capital: ${r100['peak_capital']*0.5:,.0f}
    └─ Executes ~50% of signals
    └─ Covers most normal days
    └─ Misses crisis days

PRACTICAL TARGET:
  • Capital: ${r100['p90']:,.0f}
    └─ Executes ~90% of signals
    └─ Covers 90% of all trading days
    └─ Good risk/reward balance
    └─ Recommended expansion level

SAFE CUSHION:
  • Capital: ${r100['p99']:,.0f}
    └─ Executes ~99% of signals
    └─ Only misses extreme crisis days
    └─ Excellent coverage

THEORETICAL MAXIMUM:
  • Capital: ${r100['peak_capital']:,.0f}
    └─ Executes 100% of signals
    └─ Never skips a trade
    └─ Only needed for optimization

COMPARISON TO YOUR OPTIONS:
  With $10K:
    • Can't execute all signals (need ${r100['peak_capital']:,.0f})
    • But can use smaller sizing like $50/1%
    • Or use $100/1% with cap to manage capital

  With $100K:
    • Peak need is ${r100['peak_capital']:,.0f}
    • You're ${100000 - r100['peak_capital']:,.0f} short of peak
    • But this only happens ~0.5% of days
    • 99% of days you're fine
    • Practically: Execute ~99% of signals

  With $152K+ (peak):
    • Execute 100% of signals
    • No capital worries ever
    • Maximum theoretical returns
""")

    print("=" * 200)


if __name__ == "__main__":
    main()
