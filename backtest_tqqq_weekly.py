"""
TQQQ Weekly Balance Backtest

Runs the mean reversion strategy on TQQQ and outputs weekly snapshots:
- positions_value: market value of held shares
- cash: uninvested cash
- net_liq: total account value (positions + cash)
"""

import pandas as pd
import numpy as np
import requests
from backtest_daily_rebalance_no_cap import DailyRebalanceBacktesterNoCap


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


def fetch_tqqq_closes() -> pd.DataFrame:
    """Fetch closing prices for TQQQ."""
    print("Fetching TQQQ data from Yahoo Finance...")
    rows = _yahoo_chart("TQQQ", range_="30y")
    df = pd.DataFrame(rows).set_index("date")
    df.columns = ["TQQQ"]
    df = df.sort_index()
    print(f"  TQQQ: {len(df)} trading days ({df.index[0].date()} to {df.index[-1].date()})")
    return df


def main():
    # Fetch data
    prices_df = fetch_tqqq_closes()

    # Run backtest with default sizing ($165/1% move, $10K capital)
    INITIAL_CAPITAL = 10_000
    TRADE_AMOUNT_PER_PERCENT = 165

    print(f"\nRunning backtest: ${INITIAL_CAPITAL:,} capital, ${TRADE_AMOUNT_PER_PERCENT}/1% move")

    backtester = DailyRebalanceBacktesterNoCap(
        prices_df=prices_df,
        initial_capital=INITIAL_CAPITAL,
        trade_amount_per_percent=TRADE_AMOUNT_PER_PERCENT,
    )
    results = backtester.run()

    # Build daily DataFrame from snapshots
    daily_records = []
    for snap in results.snapshots:
        daily_records.append({
            "date": snap.date,
            "positions_value": snap.invested_value,
            "cash": snap.cash,
            "net_liq": snap.total_value,
        })

    daily_df = pd.DataFrame(daily_records).set_index("date")

    # Resample to weekly (Friday close / last trading day of week)
    weekly_df = daily_df.resample("W-FRI").last().dropna()

    # Round to 2 decimal places
    weekly_df = weekly_df.round(2)

    # Save to CSV
    output_path = "tqqq_weekly_balances.csv"
    weekly_df.to_csv(output_path)
    print(f"\nWeekly balances saved to: {output_path}")
    print(f"Weeks: {len(weekly_df)}")

    # Print summary metrics
    print(f"\n{'='*50}")
    print("BACKTEST SUMMARY")
    print(f"{'='*50}")
    print(f"Period:       {prices_df.index[0].date()} to {prices_df.index[-1].date()}")
    print(f"Total Return: {results.total_return:.2f}%")
    print(f"Final Value:  ${results.final_value:,.2f}")
    print(f"Max Drawdown: {results.max_drawdown:.2f}%")
    print(f"Sharpe Ratio: {results.sharpe_ratio:.3f}")
    print(f"Total Trades: {results.num_trades:,}")

    # Print first and last 5 weeks
    print(f"\nFirst 5 weeks:")
    print(weekly_df.head().to_string())
    print(f"\nLast 5 weeks:")
    print(weekly_df.tail().to_string())


if __name__ == "__main__":
    main()
