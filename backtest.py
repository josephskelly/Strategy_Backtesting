"""
Backtester — single entry point

Run a mean-reversion backtest on any ticker (or all ProShares leveraged ETFs),
with a pluggable indicator module for signal generation.

Usage:
    python backtest.py TQQQ
    python backtest.py TQQQ --indicator indicators/zscore.py
    python backtest.py TQQQ --indicator indicators/daily_return.py --nlv-pct 2.0 --cap
    python backtest.py TQQQ --indicator indicators/zscore.py --z-threshold 1.5
    python backtest.py TQQQ --years 10 --interval 1wk
    python backtest.py --all
    python backtest.py --all --indicator indicators/zscore.py --years 5

Custom indicator:
    Any .py file that exports `class Indicator` and optionally `def add_args(parser)`.
    See indicators/daily_return.py for a worked example.
"""

import argparse
import importlib.util
import os
import sys
import time
import types

import pandas as pd
import requests

from engine import BacktestEngine

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

DEFAULT_INDICATOR = "indicators/daily_return.py"
DEFAULT_YEARS = 30
DEFAULT_INTERVAL = "1d"
INITIAL_CAPITAL = 10_000
ETF_CSV = "proshares_leveraged_etfs.csv"


# ---------------------------------------------------------------------------
# Indicator plugin loader
# ---------------------------------------------------------------------------

def _load_indicator_module(path: str) -> types.ModuleType:
    """Load an indicator .py file and return the module."""
    if not os.path.isfile(path):
        print(f"Error: indicator file not found: {path}")
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("_indicator", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "Indicator"):
        print(f"Error: {path} must export a class named 'Indicator'.")
        sys.exit(1)
    if not callable(getattr(mod.Indicator, "signal", None)):
        print(f"Error: {path} Indicator class must implement a signal() method.")
        sys.exit(1)
    return mod


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _yahoo_chart(ticker: str, range_: str = "30y", interval: str = "1d") -> list[dict]:
    """Fetch OHLCV data from Yahoo Finance's chart API."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?range={range_}&interval={interval}"
    )
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    return [
        {"date": pd.Timestamp(ts, unit="s").normalize(), "close": close}
        for ts, close in zip(timestamps, closes)
        if close is not None
    ]


def fetch_closes(ticker: str, range_: str = "30y", interval: str = "1d") -> pd.DataFrame:
    """Return a single-column DataFrame of closing prices for *ticker*."""
    rows = _yahoo_chart(ticker, range_=range_, interval=interval)
    df = pd.DataFrame(rows).set_index("date")
    df.columns = [ticker]
    return df.sort_index()


# ---------------------------------------------------------------------------
# Single-ticker run
# ---------------------------------------------------------------------------

def run_single(
    ticker: str,
    indicator,
    years: int = DEFAULT_YEARS,
    interval: str = DEFAULT_INTERVAL,
) -> dict | None:
    """
    Fetch data, run the backtest, save weekly CSV, return a summary dict.
    Returns None on data-fetch failure.
    """
    ticker = ticker.upper()
    range_ = f"{years}y"
    print(f"\nFetching {ticker} ({range_}, {interval})...")
    try:
        prices_df = fetch_closes(ticker, range_=range_, interval=interval)
    except Exception as e:
        print(f"  Warning: could not fetch {ticker}: {e}")
        return None

    bar_label = "bars" if interval != "1d" else "trading days"
    print(
        f"  {ticker}: {len(prices_df)} {bar_label} "
        f"({prices_df.index[0].date()} to {prices_df.index[-1].date()})"
    )

    engine = BacktestEngine(
        prices_df=prices_df,
        indicator=indicator,
        initial_capital=INITIAL_CAPITAL,
    )
    results = engine.run()

    # Save weekly snapshot CSV
    daily_records = [
        {
            "date": s.date,
            "positions_value": s.invested_value,
            "cash": s.cash,
            "net_liq": s.total_value,
        }
        for s in results.snapshots
    ]
    daily_df = pd.DataFrame(daily_records).set_index("date")
    weekly_df = daily_df.resample("W-FRI").last().dropna().round(2)
    out_path = f"{OUTPUT_DIR}/{ticker.lower()}_weekly_balances.csv"
    weekly_df.to_csv(out_path)
    print(f"  Saved {len(weekly_df)} weekly rows → {out_path}")

    print(
        f"  Return: {results.total_return:.2f}%  |  "
        f"Final: ${results.final_value:,.2f}  |  "
        f"Max DD: {results.max_drawdown:.2f}%  |  "
        f"Sharpe: {results.sharpe_ratio:.3f}"
    )

    return {
        "Ticker": ticker,
        "Return %": round(results.total_return, 2),
        "Final Value $": round(results.final_value, 2),
        "Max Drawdown %": round(results.max_drawdown, 2),
        "Sharpe": round(results.sharpe_ratio, 3),
        "Trades": results.num_trades,
        "Start Date": prices_df.index[0].date().isoformat(),
        "End Date": prices_df.index[-1].date().isoformat(),
        "Years": round(len(prices_df) / 252, 1),
    }


# ---------------------------------------------------------------------------
# All-ETFs run
# ---------------------------------------------------------------------------

def run_all(
    indicator,
    years: int = DEFAULT_YEARS,
    interval: str = DEFAULT_INTERVAL,
) -> None:
    """Run backtest for every ETF listed in proshares_leveraged_etfs.csv."""
    try:
        etf_df = pd.read_csv(ETF_CSV)
    except FileNotFoundError:
        print(f"Error: {ETF_CSV} not found.")
        sys.exit(1)

    tickers = list(etf_df["Ticker"])
    categories = dict(zip(etf_df["Ticker"], etf_df.get("Category", [""] * len(tickers))))

    print("=" * 60)
    print(f"Running {len(tickers)} ETFs  |  {years}y  |  {interval}")
    print("=" * 60)

    summaries = []
    for ticker in tickers:
        result = run_single(ticker, indicator=indicator, years=years, interval=interval)
        if result:
            result["Category"] = categories.get(ticker, "")
            summaries.append(result)
        time.sleep(0.3)

    if not summaries:
        print("\nNo results.")
        return

    summary_df = (
        pd.DataFrame(summaries)
        .sort_values("Return %", ascending=False)
        .reset_index(drop=True)
    )
    summary_df.insert(0, "Rank", range(1, len(summary_df) + 1))

    out_csv = f"{OUTPUT_DIR}/etf_weekly_comparison.csv"
    summary_df.to_csv(out_csv, index=False)

    print("\n\n" + "=" * 90)
    print("ALL ETFs — ranked by Return %")
    print("=" * 90)
    cols = ["Rank", "Ticker", "Category", "Return %", "Final Value $",
            "Max Drawdown %", "Sharpe", "Trades", "Years"]
    print(summary_df[cols].to_string(index=False))
    print(f"\nFull results → {out_csv}")
    print(f"Best:  {summary_df.iloc[0]['Ticker']}  {summary_df.iloc[0]['Return %']:.2f}%")
    print(f"Worst: {summary_df.iloc[-1]['Ticker']}  {summary_df.iloc[-1]['Return %']:.2f}%")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    # Phase 1: discover which indicator to load (before full arg parse).
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--indicator", default=DEFAULT_INDICATOR)
    pre_args, _ = pre.parse_known_args()

    indicator_module = _load_indicator_module(pre_args.indicator)

    # Phase 2: build the full parser, letting the indicator add its own flags.
    parser = argparse.ArgumentParser(
        description="Mean-reversion backtester with pluggable indicator.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "ticker",
        nargs="?",
        help="Ticker to backtest (e.g. TQQQ). Omit when using --all.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=f"Run all ETFs listed in {ETF_CSV}.",
    )
    parser.add_argument(
        "--indicator",
        default=DEFAULT_INDICATOR,
        metavar="PATH",
        help="Path to a .py indicator module.",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=DEFAULT_YEARS,
        metavar="N",
        help="Years of history to fetch from Yahoo Finance.",
    )
    parser.add_argument(
        "--interval",
        choices=["1d", "1wk"],
        default=DEFAULT_INTERVAL,
        help="Bar interval: daily (1d) or weekly (1wk).",
    )

    # Let the indicator register its own flags
    if hasattr(indicator_module, "add_args"):
        indicator_module.add_args(parser)

    args = parser.parse_args()

    # Instantiate indicator with all parsed args as kwargs
    # (argparse uses underscores; pass them all and let the indicator pick what it needs)
    indicator = indicator_module.Indicator(**vars(args))

    if args.all:
        run_all(indicator=indicator, years=args.years, interval=args.interval)
    elif args.ticker:
        result = run_single(
            args.ticker,
            indicator=indicator,
            years=args.years,
            interval=args.interval,
        )
        if result:
            print(f"\n{'=' * 50}")
            print(f"SUMMARY  ({args.years}y, {args.interval})")
            print(f"{'=' * 50}")
            for k, v in result.items():
                print(f"{k:<20} {v}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
