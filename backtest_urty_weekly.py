"""
Weekly Balance Backtest - Single ETF or All ETFs

Runs the mean reversion strategy on one or all ProShares leveraged ETFs and
outputs weekly snapshots: positions_value, cash, net_liq.

Usage:
    python backtest_urty_weekly.py URTY          # single ETF
    python backtest_urty_weekly.py TQQQ          # any ticker
    python backtest_urty_weekly.py --all         # all ETFs from proshares_leveraged_etfs.csv
"""

import argparse
import sys
import time

import pandas as pd
import requests

from backtest_daily_rebalance_no_cap import DailyRebalanceBacktesterNoCap

INITIAL_CAPITAL = 10_000
TRADE_AMOUNT_PER_PERCENT = 165
ETF_CSV = "proshares_leveraged_etfs.csv"


def _yahoo_chart(ticker: str, range_: str = "30y", interval: str = "1d") -> list[dict]:
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
        close = quotes["close"][i]
        if close is not None:
            rows.append({
                "date": pd.Timestamp(ts, unit="s").normalize(),
                "close": close,
            })
    return rows


def fetch_closes(ticker: str) -> pd.DataFrame:
    """Fetch closing prices for a single ticker."""
    rows = _yahoo_chart(ticker, range_="30y")
    df = pd.DataFrame(rows).set_index("date")
    df.columns = [ticker]
    return df.sort_index()


def run_single(ticker: str, category: str = "") -> dict | None:
    """
    Run backtest for one ETF, save weekly CSV, and return a summary dict.
    Returns None on failure.
    """
    ticker = ticker.upper()
    print(f"\nFetching {ticker} data from Yahoo Finance...")
    try:
        prices_df = fetch_closes(ticker)
    except Exception as e:
        print(f"  Warning: Could not fetch {ticker}: {e}")
        return None

    print(f"  {ticker}: {len(prices_df)} trading days "
          f"({prices_df.index[0].date()} to {prices_df.index[-1].date()})")

    backtester = DailyRebalanceBacktesterNoCap(
        prices_df=prices_df,
        initial_capital=INITIAL_CAPITAL,
        trade_amount_per_percent=TRADE_AMOUNT_PER_PERCENT,
    )
    results = backtester.run()

    # Build daily DataFrame from snapshots
    daily_records = [
        {
            "date": snap.date,
            "positions_value": snap.invested_value,
            "cash": snap.cash,
            "net_liq": snap.total_value,
        }
        for snap in results.snapshots
    ]
    daily_df = pd.DataFrame(daily_records).set_index("date")

    # Resample to weekly (Friday / last trading day of week)
    weekly_df = daily_df.resample("W-FRI").last().dropna().round(2)

    output_path = f"{ticker.lower()}_weekly_balances.csv"
    weekly_df.to_csv(output_path)
    print(f"  Saved {len(weekly_df)} weekly rows → {output_path}")

    print(f"  Return: {results.total_return:.2f}%  |  "
          f"Final: ${results.final_value:,.2f}  |  "
          f"Max DD: {results.max_drawdown:.2f}%  |  "
          f"Sharpe: {results.sharpe_ratio:.3f}")

    return {
        "Ticker": ticker,
        "Category": category,
        "Return %": round(results.total_return, 2),
        "Final Value $": round(results.final_value, 2),
        "Max Drawdown %": round(results.max_drawdown, 2),
        "Sharpe": round(results.sharpe_ratio, 3),
        "Trades": results.num_trades,
        "Start Date": prices_df.index[0].date().isoformat(),
        "End Date": prices_df.index[-1].date().isoformat(),
        "Years": round(len(prices_df) / 252, 1),
    }


def run_all() -> None:
    """Run backtest for every ETF in proshares_leveraged_etfs.csv."""
    try:
        etf_df = pd.read_csv(ETF_CSV)
    except FileNotFoundError:
        print(f"Error: {ETF_CSV} not found.")
        sys.exit(1)

    tickers = list(etf_df["Ticker"])
    categories = dict(zip(etf_df["Ticker"], etf_df["Category"]))

    print("=" * 60)
    print(f"Running {len(tickers)} ETFs individually")
    print(f"Capital: ${INITIAL_CAPITAL:,}  |  Sizing: ${TRADE_AMOUNT_PER_PERCENT}/1%  |  No cap")
    print("=" * 60)

    summaries = []
    for ticker in tickers:
        result = run_single(ticker, category=categories.get(ticker, ""))
        if result:
            summaries.append(result)
        time.sleep(0.3)  # avoid rate limiting

    if not summaries:
        print("\nNo results.")
        return

    # Sort by return descending
    summary_df = pd.DataFrame(summaries).sort_values("Return %", ascending=False).reset_index(drop=True)
    summary_df.insert(0, "Rank", range(1, len(summary_df) + 1))

    # Save comparison CSV
    output_csv = "etf_weekly_comparison.csv"
    summary_df.to_csv(output_csv, index=False)

    # Print table
    print("\n\n" + "=" * 90)
    print("COMPARISON: All ETFs Ranked by Return % (standalone backtest)")
    print("=" * 90)
    cols = ["Rank", "Ticker", "Category", "Return %", "Final Value $", "Max Drawdown %", "Sharpe", "Trades", "Years"]
    print(summary_df[cols].to_string(index=False))
    print(f"\nFull results saved to: {output_csv}")
    print(f"\nBest:  {summary_df.iloc[0]['Ticker']} → {summary_df.iloc[0]['Return %']:.2f}%")
    print(f"Worst: {summary_df.iloc[-1]['Ticker']} → {summary_df.iloc[-1]['Return %']:.2f}%")


def main():
    parser = argparse.ArgumentParser(
        description="Mean reversion weekly balance backtest for ProShares leveraged ETFs."
    )
    parser.add_argument(
        "ticker",
        nargs="?",
        help="ETF ticker to backtest (e.g. URTY, TQQQ). Omit when using --all.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=f"Run all ETFs listed in {ETF_CSV} and print a comparison table.",
    )
    args = parser.parse_args()

    if args.all:
        run_all()
    elif args.ticker:
        result = run_single(args.ticker)
        if result:
            print(f"\n{'='*50}")
            print("BACKTEST SUMMARY")
            print(f"{'='*50}")
            for k, v in result.items():
                print(f"{k:<20} {v}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
