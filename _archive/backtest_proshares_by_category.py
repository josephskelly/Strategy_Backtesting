"""
Backtest: All ProShares leveraged ETFs from proshares_leveraged_etfs.csv
Grouped by category, each run on its own available date range.

Parameters: $10K initial capital, $165/1% move, no margin cap.
"""

import os

import pandas as pd
import requests
import time
from backtest_daily_rebalance_no_cap import DailyRebalanceBacktesterNoCap

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

INITIAL_CAPITAL = 10_000
TRADE_AMOUNT = 165
DATA_RANGE = "30y"
CSV_PATH = "proshares_leveraged_etfs.csv"


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


def fetch_closes(tickers: list[str], range_: str = "30y") -> pd.DataFrame:
    """Fetch closing prices for a list of tickers."""
    closes = pd.DataFrame()
    for ticker in tickers:
        try:
            rows = _yahoo_chart(ticker, range_=range_)
            df = pd.DataFrame(rows).set_index("date")
            closes[ticker] = df["close"]
            time.sleep(0.2)
        except Exception as e:
            print(f"  Warning: Could not fetch {ticker}: {e}")
    closes.index.name = "Date"
    return closes


def run_category_backtest(category: str, tickers: list[str]) -> dict | None:
    """Fetch data and run backtest for one category. Returns result dict or None."""
    print(f"\n{'─' * 60}")
    print(f"  Category: {category} ({len(tickers)} ETFs)")
    print(f"  Tickers:  {', '.join(tickers)}")

    prices = fetch_closes(tickers, range_=DATA_RANGE)

    # Drop columns that are entirely NaN, then rows with any NaN
    prices = prices.dropna(axis=1, how="all").dropna()

    if prices.empty or len(prices.columns) < 2:
        print(f"  Skipping: insufficient data (need ≥2 ETFs with overlapping history)")
        return None

    if len(prices) < 50:
        print(f"  Skipping: too few trading days ({len(prices)})")
        return None

    date_start = prices.index.min().strftime("%Y-%m-%d")
    date_end = prices.index.max().strftime("%Y-%m-%d")
    years = len(prices) / 252
    included = list(prices.columns)
    excluded = [t for t in tickers if t not in included]

    print(f"  Date range: {date_start} → {date_end} ({years:.1f} years, {len(prices)} days)")
    if excluded:
        print(f"  Excluded (no data): {', '.join(excluded)}")
    print(f"  Running backtest...")

    backtester = DailyRebalanceBacktesterNoCap(
        prices_df=prices,
        initial_capital=INITIAL_CAPITAL,
        trade_amount_per_percent=TRADE_AMOUNT,
    )
    r = backtester.run()

    ann_return = r.total_return / years if years > 0 else 0

    print(f"  Return: {r.total_return:.2f}%  |  Final: ${r.final_value:,.0f}  "
          f"|  Max DD: {r.max_drawdown:.2f}%  |  Sharpe: {r.sharpe_ratio:.3f}")

    return {
        "Category": category,
        "ETFs Included": len(included),
        "ETFs Requested": len(tickers),
        "Date Start": date_start,
        "Date End": date_end,
        "Years": round(years, 1),
        "Total Return %": round(r.total_return, 2),
        "Ann Return %": round(ann_return, 2),
        "Final Value $": round(r.final_value, 2),
        "Max Drawdown %": round(r.max_drawdown, 2),
        "Sharpe": round(r.sharpe_ratio, 3),
        "Num Trades": r.num_trades,
        "Avg Invested %": round(r.avg_invested_pct, 2),
        "Min Cash $": round(r.min_cash, 2),
        "Went Negative": r.went_negative_cash,
        "Tickers Used": ", ".join(included),
    }


def main():
    print("=" * 70)
    print("BACKTEST: ProShares Leveraged ETFs by Category")
    print(f"Parameters: ${INITIAL_CAPITAL:,} capital | ${TRADE_AMOUNT}/1% | No cap")
    print("=" * 70)

    # Load CSV and group by category
    etf_df = pd.read_csv(CSV_PATH)
    categories = etf_df.groupby("Category")["Ticker"].apply(list).to_dict()

    print(f"\nLoaded {len(etf_df)} ETFs across {len(categories)} categories from {CSV_PATH}")

    results = []
    for category, tickers in sorted(categories.items()):
        result = run_category_backtest(category, tickers)
        if result:
            results.append(result)

    if not results:
        print("\nNo results to display.")
        return

    # Summary table
    summary_cols = [
        "Category", "ETFs Included", "Years",
        "Total Return %", "Ann Return %", "Final Value $",
        "Max Drawdown %", "Sharpe", "Num Trades",
    ]
    df_summary = pd.DataFrame(results)[summary_cols]
    df_summary = df_summary.sort_values("Total Return %", ascending=False)

    print("\n\n" + "=" * 70)
    print("SUMMARY: All Categories Ranked by Total Return")
    print("=" * 70)
    print(df_summary.to_string(index=False))

    # Save full results to CSV
    df_full = pd.DataFrame(results).sort_values("Total Return %", ascending=False)
    output_csv = f"{OUTPUT_DIR}/backtest_proshares_category_results.csv"
    df_full.to_csv(output_csv, index=False)
    print(f"\nFull results saved to: {output_csv}")

    # Best / worst
    best = df_summary.iloc[0]
    worst = df_summary.iloc[-1]
    print(f"\nBest category:  {best['Category']} → {best['Total Return %']:.2f}% "
          f"({best['Years']:.1f} yrs, Sharpe {best['Sharpe']:.3f})")
    print(f"Worst category: {worst['Category']} → {worst['Total Return %']:.2f}% "
          f"({worst['Years']:.1f} yrs, Sharpe {worst['Sharpe']:.3f})")
    print()


if __name__ == "__main__":
    main()
