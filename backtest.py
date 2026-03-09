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

import numpy as np
import pandas as pd
import requests

from engine import BacktestEngine

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

DEFAULT_INDICATOR = "indicators/daily_return.py"
DEFAULT_YEARS = 30
DEFAULT_INTERVAL = "1d"
INITIAL_CAPITAL = 10_000
TRADING_DAYS_PER_YEAR: int = 252     # Annualisation factor for year calculation
ETF_CSV = "proshares_leveraged_etfs.csv"
BENCHMARK_TICKER: str = "SPY"


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
    indicator: types.ModuleType,
    years: int = DEFAULT_YEARS,
    interval: str = DEFAULT_INTERVAL,
    benchmark_df: pd.DataFrame | None = None,
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

    # Snapshot primary ticker date range before possibly expanding the index
    primary_start = prices_df.index[0]
    primary_end   = prices_df.index[-1]

    bar_label = "bars" if interval != "1d" else "trading days"
    print(
        f"  {ticker}: {len(prices_df)} {bar_label} "
        f"({primary_start.date()} to {primary_end.date()})"
    )

    # Auto-fetch hedge ticker if enabled
    hedge_ticker = getattr(indicator, "hedge_ticker", None)
    hedge_pct    = getattr(indicator, "hedge_pct", 0.0)
    if hedge_pct > 0 and hedge_ticker and hedge_ticker != ticker:
        try:
            hedge_df = fetch_closes(hedge_ticker, range_=range_, interval=interval)
            prices_df = pd.concat([prices_df, hedge_df], axis=1)
            print(f"  Hedge: {hedge_ticker} ({hedge_pct:.0f}% of NLV)")
        except Exception as e:
            print(f"  Warning: could not fetch hedge {hedge_ticker}: {e}")

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

    bh_return: float | None = None
    bh_final: float | None = None
    if benchmark_df is not None:
        spy = benchmark_df.loc[primary_start : primary_end]
        if len(spy) >= 2:
            spy_start = float(spy.iloc[0, 0])
            spy_end   = float(spy.iloc[-1, 0])
            bh_return = (spy_end / spy_start - 1) * 100
            bh_final  = INITIAL_CAPITAL * (spy_end / spy_start)

    primary_prices = prices_df[ticker]
    ticker_start = float(primary_prices.loc[primary_start])
    ticker_end   = float(primary_prices.loc[primary_end])
    ticker_bh_return = (ticker_end / ticker_start - 1) * 100
    ticker_bh_final  = INITIAL_CAPITAL * (ticker_end / ticker_start)

    bh_str = (
        f"  |  SPY B&H: {bh_return:.2f}% (${bh_final:,.0f})"
        if bh_return is not None else ""
    )
    ticker_bh_str = f"  |  {ticker} B&H: {ticker_bh_return:.2f}% (${ticker_bh_final:,.0f})"
    print(
        f"  Return: {results.total_return:.2f}%  |  "
        f"CAGR: {results.cagr:.2f}%  |  "
        f"Final: ${results.final_value:,.2f}  |  "
        f"Max DD: {results.max_drawdown:.2f}%  |  "
        f"Sharpe: {results.sharpe_ratio:.3f}{bh_str}{ticker_bh_str}"
    )

    return {
        "Ticker": ticker,
        "Return %": round(results.total_return, 2),
        "CAGR %": round(results.cagr, 2),
        "Final Value $": round(results.final_value, 2),
        "Max Drawdown %": round(results.max_drawdown, 2),
        "Sharpe": round(results.sharpe_ratio, 3),
        "Trades": results.num_trades,
        "Start Date": prices_df.index[0].date().isoformat(),
        "End Date": prices_df.index[-1].date().isoformat(),
        "Years": round(len(prices_df) / TRADING_DAYS_PER_YEAR, 1),
        "SPY B&H %": round(bh_return, 2) if bh_return is not None else "N/A",
        "SPY B&H $": round(bh_final, 2)  if bh_final  is not None else "N/A",
        "Asset B&H %": round(ticker_bh_return, 2),
        "Asset B&H $": round(ticker_bh_final, 2),
    }


# ---------------------------------------------------------------------------
# Combined two-indicator run
# ---------------------------------------------------------------------------

def run_combined(
    ticker: str,
    indicator1,
    indicator2,
    split_pct: float = 50.0,
    years: int = DEFAULT_YEARS,
    interval: str = DEFAULT_INTERVAL,
    benchmark_df: pd.DataFrame | None = None,
) -> dict | None:
    """
    Run two indicators simultaneously on *ticker*, each with a slice of
    INITIAL_CAPITAL.  Returns a combined summary dict on success, None on failure.
    """
    ticker = ticker.upper()
    range_ = f"{years}y"
    print(f"\nFetching {ticker} ({range_}, {interval}) for combined run...")
    try:
        prices_df = fetch_closes(ticker, range_=range_, interval=interval)
    except Exception as e:
        print(f"  Warning: could not fetch {ticker}: {e}")
        return None

    primary_start = prices_df.index[0]
    primary_end   = prices_df.index[-1]
    bar_label = "bars" if interval != "1d" else "trading days"
    print(
        f"  {ticker}: {len(prices_df)} {bar_label} "
        f"({primary_start.date()} to {primary_end.date()})"
    )

    # Auto-fetch hedge ticker for indicator1 if enabled
    hedge_ticker = getattr(indicator1, "hedge_ticker", None)
    hedge_pct    = getattr(indicator1, "hedge_pct", 0.0)
    prices_df1 = prices_df
    if hedge_pct > 0 and hedge_ticker and hedge_ticker != ticker:
        try:
            hedge_df = fetch_closes(hedge_ticker, range_=range_, interval=interval)
            prices_df1 = pd.concat([prices_df, hedge_df], axis=1)
            print(f"  Indicator1 hedge: {hedge_ticker} ({hedge_pct:.0f}% of NLV)")
        except Exception as e:
            print(f"  Warning: could not fetch hedge {hedge_ticker}: {e}")

    cap1 = INITIAL_CAPITAL * split_pct / 100.0
    cap2 = INITIAL_CAPITAL - cap1

    print(f"  Split: {split_pct:.0f}% (${cap1:,.0f}) / {100-split_pct:.0f}% (${cap2:,.0f})")

    results1 = BacktestEngine(prices_df=prices_df1, indicator=indicator1, initial_capital=cap1).run()
    results2 = BacktestEngine(prices_df=prices_df,  indicator=indicator2, initial_capital=cap2).run()

    print(f"  Indicator1: Return={results1.total_return:.2f}%  Final=${results1.final_value:,.2f}  MaxDD={results1.max_drawdown:.2f}%  Sharpe={results1.sharpe_ratio:.3f}")
    print(f"  Indicator2: Return={results2.total_return:.2f}%  Final=${results2.final_value:,.2f}  MaxDD={results2.max_drawdown:.2f}%  Sharpe={results2.sharpe_ratio:.3f}")

    # Build combined daily NLV series (snapshots share same dates — same prices_df)
    vals1 = {s.date: s.total_value for s in results1.snapshots}
    vals2 = {s.date: s.total_value for s in results2.snapshots}
    all_dates = sorted(set(vals1) | set(vals2))
    combined_values = np.array([
        vals1.get(d, 0.0) + vals2.get(d, 0.0) for d in all_dates
    ])

    final_value  = float(combined_values[-1])
    total_return = (final_value / INITIAL_CAPITAL - 1) * 100
    start_date, end_date = all_dates[0], all_dates[-1]
    total_years  = (end_date - start_date).days / 365.25
    cagr = ((final_value / INITIAL_CAPITAL) ** (1 / total_years) - 1) * 100 if total_years > 0 else 0.0

    running_max  = np.maximum.accumulate(combined_values)
    max_drawdown = float(((combined_values - running_max) / running_max * 100).min())

    daily_rets = np.diff(combined_values) / combined_values[:-1]
    if len(daily_rets) > 1 and np.std(daily_rets, ddof=1) > 0:
        sharpe = float(np.mean(daily_rets) / np.std(daily_rets, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    else:
        sharpe = 0.0

    num_trades = results1.num_trades + results2.num_trades

    # Merge sector performance
    merged_sector: dict = {}
    for sp in (results1.sector_performance, results2.sector_performance):
        for tkr, stats in sp.items():
            if tkr not in merged_sector:
                merged_sector[tkr] = dict(stats)
            else:
                merged_sector[tkr]["num_trades"] += stats["num_trades"]
                merged_sector[tkr]["pnl"]        += stats["pnl"]
                merged_sector[tkr]["num_wins"]   += stats["num_wins"]
    for tkr, stats in merged_sector.items():
        total_cap = stats.get("invested_capital", INITIAL_CAPITAL) or INITIAL_CAPITAL
        stats["return_pct"] = stats["pnl"] / total_cap * 100
        trades = stats["num_trades"]
        stats["win_rate"] = stats["num_wins"] / trades * 100 if trades > 0 else 0.0

    # Save combined weekly CSV
    combined_dict = {d: v for d, v in zip(all_dates, combined_values)}
    cash1 = {s.date: s.cash for s in results1.snapshots}
    cash2 = {s.date: s.cash for s in results2.snapshots}
    inv1  = {s.date: s.invested_value for s in results1.snapshots}
    inv2  = {s.date: s.invested_value for s in results2.snapshots}
    daily_records = [
        {
            "date": d,
            "positions_value": inv1.get(d, 0.0) + inv2.get(d, 0.0),
            "cash":            cash1.get(d, 0.0) + cash2.get(d, 0.0),
            "net_liq":         combined_dict[d],
        }
        for d in all_dates
    ]
    daily_df = pd.DataFrame(daily_records).set_index("date")
    weekly_df = daily_df.resample("W-FRI").last().dropna().round(2)
    out_path = f"{OUTPUT_DIR}/{ticker.lower()}_combined_weekly_balances.csv"
    weekly_df.to_csv(out_path)
    print(f"  Saved {len(weekly_df)} combined weekly rows → {out_path}")

    bh_return: float | None = None
    bh_final: float | None = None
    if benchmark_df is not None:
        spy = benchmark_df.loc[primary_start:primary_end]
        if len(spy) >= 2:
            spy_start = float(spy.iloc[0, 0])
            spy_end   = float(spy.iloc[-1, 0])
            bh_return = (spy_end / spy_start - 1) * 100
            bh_final  = INITIAL_CAPITAL * (spy_end / spy_start)

    ticker_prices   = prices_df[ticker]
    ticker_bh_return = (float(ticker_prices.iloc[-1]) / float(ticker_prices.iloc[0]) - 1) * 100
    ticker_bh_final  = INITIAL_CAPITAL * (float(ticker_prices.iloc[-1]) / float(ticker_prices.iloc[0]))

    bh_str = (
        f"  |  SPY B&H: {bh_return:.2f}% (${bh_final:,.0f})"
        if bh_return is not None else ""
    )
    ticker_bh_str = f"  |  {ticker} B&H: {ticker_bh_return:.2f}% (${ticker_bh_final:,.0f})"
    print(
        f"  COMBINED: Return: {total_return:.2f}%  |  "
        f"CAGR: {cagr:.2f}%  |  "
        f"Final: ${final_value:,.2f}  |  "
        f"Max DD: {max_drawdown:.2f}%  |  "
        f"Sharpe: {sharpe:.3f}{bh_str}{ticker_bh_str}"
    )

    return {
        "Ticker": ticker,
        "Return %": round(total_return, 2),
        "CAGR %": round(cagr, 2),
        "Final Value $": round(final_value, 2),
        "Max Drawdown %": round(max_drawdown, 2),
        "Sharpe": round(sharpe, 3),
        "Trades": num_trades,
        "Start Date": primary_start.date().isoformat(),
        "End Date": primary_end.date().isoformat(),
        "Years": round(total_years, 1),
        "SPY B&H %": round(bh_return, 2) if bh_return is not None else "N/A",
        "SPY B&H $": round(bh_final, 2)  if bh_final  is not None else "N/A",
        "Asset B&H %": round(ticker_bh_return, 2),
        "Asset B&H $": round(ticker_bh_final, 2),
    }


# ---------------------------------------------------------------------------
# All-ETFs run
# ---------------------------------------------------------------------------

def run_all(
    indicator: types.ModuleType,
    years: int = DEFAULT_YEARS,
    interval: str = DEFAULT_INTERVAL,
    benchmark_df: pd.DataFrame | None = None,
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
        result = run_single(ticker, indicator=indicator, years=years, interval=interval, benchmark_df=benchmark_df)
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
    cols = ["Rank", "Ticker", "Category", "Return %", "CAGR %", "Final Value $",
            "Max Drawdown %", "Sharpe", "Trades", "Years",
            "SPY B&H %", "SPY B&H $", "Asset B&H %", "Asset B&H $"]
    print(summary_df[cols].to_string(index=False))
    print(f"\nFull results → {out_csv}")
    print(f"Best:  {summary_df.iloc[0]['Ticker']}  {summary_df.iloc[0]['Return %']:.2f}%")
    print(f"Worst: {summary_df.iloc[-1]['Ticker']}  {summary_df.iloc[-1]['Return %']:.2f}%")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    # Phase 1: discover which indicator(s) to load (before full arg parse).
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--indicator", default=DEFAULT_INDICATOR)
    pre.add_argument("--indicator2", default=None)
    pre_args, _ = pre.parse_known_args()

    indicator_module  = _load_indicator_module(pre_args.indicator)
    indicator2_module = _load_indicator_module(pre_args.indicator2) if pre_args.indicator2 else None

    # Phase 2: build the full parser, letting both indicators add their own flags.
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
        "--indicator2",
        default=None,
        metavar="PATH",
        help="Path to a second .py indicator module (enables split-capital combined run).",
    )
    parser.add_argument(
        "--split",
        type=float,
        default=50.0,
        metavar="PCT",
        help="Percent of capital allocated to --indicator (default: 50). Remainder goes to --indicator2.",
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

    # Let each indicator register its own flags
    if hasattr(indicator_module, "add_args"):
        indicator_module.add_args(parser)
    if indicator2_module and hasattr(indicator2_module, "add_args"):
        indicator2_module.add_args(parser)

    args = parser.parse_args()

    # Instantiate indicator(s) with all parsed args as kwargs
    # (argparse uses underscores; pass them all and let each indicator pick what it needs)
    indicator = indicator_module.Indicator(**vars(args))

    print(f"Fetching {BENCHMARK_TICKER} benchmark...")
    benchmark_df: pd.DataFrame | None = None
    try:
        benchmark_df = fetch_closes(BENCHMARK_TICKER, range_=f"{args.years}y", interval=args.interval)
    except Exception as e:
        print(f"  Warning: could not fetch {BENCHMARK_TICKER} benchmark: {e}")

    if args.indicator2 and args.ticker:
        indicator2 = indicator2_module.Indicator(**vars(args))
        result = run_combined(
            args.ticker,
            indicator1=indicator,
            indicator2=indicator2,
            split_pct=args.split,
            years=args.years,
            interval=args.interval,
            benchmark_df=benchmark_df,
        )
        if result:
            print(f"\n{'=' * 50}")
            print(f"COMBINED SUMMARY  ({args.years}y, {args.interval})")
            print(f"{'=' * 50}")
            for k, v in result.items():
                print(f"{k:<20} {v}")
    elif args.all:
        run_all(indicator=indicator, years=args.years, interval=args.interval, benchmark_df=benchmark_df)
    elif args.ticker:
        result = run_single(
            args.ticker,
            indicator=indicator,
            years=args.years,
            interval=args.interval,
            benchmark_df=benchmark_df,
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
