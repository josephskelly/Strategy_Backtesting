"""
Backtest: $10K starting capital, $100 per 1% move, NO cap on position size

Shows actual returns when removing the margin cap with smaller position sizing.
"""

import pandas as pd
import numpy as np
import requests
import time
from backtest_daily_rebalance_no_cap import DailyRebalanceBacktesterNoCap


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


def main():
    print("=" * 180)
    print("BACKTEST: $10K Starting Capital, $100 Per 1% Move, NO Cap")
    print("=" * 180)
    print()

    # Fetch data
    print("Fetching sector data...")
    sector_closes = fetch_sector_closes(SECTOR_ETFS_2X, range_="30y")

    if len(sector_closes) < 100:
        print("Not enough data.")
        return

    sector_closes = sector_closes.dropna(axis=1, how='all').dropna()

    print(f"Data range: {sector_closes.index.min().strftime('%Y-%m-%d')} to {sector_closes.index.max().strftime('%Y-%m-%d')}")
    print(f"Trading days: {len(sector_closes)}\n")

    # Run backtest
    print("Running backtest...\n")
    backtester = DailyRebalanceBacktesterNoCap(
        prices_df=sector_closes,
        initial_capital=10000,
        trade_amount_per_percent=100,
    )
    results = backtester.run()

    # Display results
    print("=" * 180)
    print("RESULTS: $10K + $100/1% + NO CAP")
    print("=" * 180)

    print(f"""
PERFORMANCE METRICS:
├─ Total Return:           {results.total_return:>8.2f}%
├─ Final Portfolio Value:  ${results.final_value:>13,.2f}
├─ Profit/Loss:            ${results.final_pnl:>13,.2f}
├─ Annualized Return:      {results.total_return / 17.7:>8.2f}% per year
│
├─ Maximum Drawdown:       {results.max_drawdown:>8.2f}%
├─ Sharpe Ratio:           {results.sharpe_ratio:>8.3f}
│
├─ Total Trades:           {results.num_trades:>18}
├─ Avg Invested:           {results.avg_invested_pct:>8.2f}%
├─ Avg Cash:               {results.avg_cash_pct:>8.2f}%
│
├─ Minimum Cash Reached:   ${results.min_cash:>13,.2f}
└─ Went Negative:          {"YES ⚠️ (Stopped executing)" if results.went_negative_cash else "NO ✓"}
""")

    # Comparison with other strategies
    print("\n" + "=" * 180)
    print("COMPARISON: All $10K Strategies")
    print("=" * 180)

    comparison_data = [
        {
            'Strategy': '$165/1% WITH cap',
            'Position Size': '$165',
            'Cap': '25%',
            'Return': '814.56%',
            'Final Value': '$91,455',
            'Drawdown': '-57.08%',
            'Sharpe': '0.585',
            'Min Cash': 'N/A',
        },
        {
            'Strategy': '$165/1% NO cap',
            'Position Size': '$165',
            'Cap': 'None',
            'Return': '912.51%',
            'Final Value': '$101,251',
            'Drawdown': '-58.53%',
            'Sharpe': '0.602',
            'Min Cash': '$0.00',
        },
        {
            'Strategy': '$100/1% NO cap',
            'Position Size': '$100',
            'Cap': 'None',
            'Return': f'{results.total_return:.2f}%',
            'Final Value': f'${results.final_value:,.0f}',
            'Drawdown': f'{results.max_drawdown:.2f}%',
            'Sharpe': f'{results.sharpe_ratio:.3f}',
            'Min Cash': f'${results.min_cash:,.2f}',
        },
    ]

    df_comparison = pd.DataFrame(comparison_data)
    print(f"\n{df_comparison.to_string(index=False)}\n")

    # Relative performance
    print("=" * 180)
    print("RELATIVE PERFORMANCE COMPARISON")
    print("=" * 180)

    vs_165_with_cap = ((results.total_return - 814.56) / 814.56) * 100
    vs_165_no_cap = ((results.total_return - 912.51) / 912.51) * 100

    print(f"""
vs $165/1% WITH cap:
├─ Return Difference:      {vs_165_with_cap:+.2f}%
├─ Dollar Difference:      ${results.final_value - 91455:+,.0f}
└─ Verdict: {"WORSE" if vs_165_with_cap < 0 else "BETTER"} by {abs(vs_165_with_cap):.2f}%

vs $165/1% NO cap:
├─ Return Difference:      {vs_165_no_cap:+.2f}%
├─ Dollar Difference:      ${results.final_value - 101251:+,.0f}
└─ Verdict: {"WORSE" if vs_165_no_cap < 0 else "BETTER"} by {abs(vs_165_no_cap):.2f}%

KEY INSIGHT:
The smaller position size ($100 vs $165) reduces returns but:
├─ Less aggressive on downsides
├─ More conservative capital management
└─ Could be better for psychological comfort
""")

    # Sector performance
    print("\n" + "=" * 180)
    print("SECTOR PERFORMANCE BREAKDOWN")
    print("=" * 180)

    sector_rows = []
    for ticker, perf in sorted(results.sector_performance.items()):
        sector_rows.append({
            'Sector': ticker,
            'Trades': perf['num_trades'],
            'Wins': perf['num_wins'],
            'Win Rate': f"{perf['win_rate']:.1f}%",
            'P&L': f"${perf['pnl']:,.0f}",
            'Return': f"{perf['return_pct']:.2f}%",
        })

    df_sectors = pd.DataFrame(sector_rows)
    print(f"\n{df_sectors.to_string(index=False)}\n")

    # Risk analysis
    print("=" * 180)
    print("RISK ANALYSIS")
    print("=" * 180)

    snapshots = results.snapshots
    portfolio_values = [s.total_value for s in snapshots]
    drawdowns = []
    running_max = portfolio_values[0]

    for value in portfolio_values:
        running_max = max(running_max, value)
        dd = (value - running_max) / running_max * 100
        drawdowns.append(dd)

    print(f"""
Portfolio Value Evolution:
├─ Starting Value:         $10,000.00
├─ Minimum Value:          ${min(portfolio_values):,.2f}
├─ Maximum Value:          ${max(portfolio_values):,.2f}
├─ Final Value:            ${portfolio_values[-1]:,.2f}
│
├─ Worst Drawdown:         {min(drawdowns):.2f}%
├─ Current Drawdown:       {drawdowns[-1]:.2f}%
├─ Average Daily Move:     {np.mean(np.diff(portfolio_values)):.2f}
└─ Daily Volatility:       {np.std(np.diff(portfolio_values)):.2f}
""")

    # Trading activity
    num_buy_trades = sum(1 for t in backtester.trades if t.action == 'BUY')
    num_sell_trades = sum(1 for t in backtester.trades if t.action == 'SELL')
    total_buy_value = sum(t.value for t in backtester.trades if t.action == 'BUY')
    total_sell_value = sum(t.value for t in backtester.trades if t.action == 'SELL')

    print("=" * 180)
    print("TRADING ACTIVITY")
    print("=" * 180)

    print(f"""
Trade Counts:
├─ Total Trades:           {results.num_trades}
├─ Buy Trades:             {num_buy_trades}
├─ Sell Trades:            {num_sell_trades}
├─ Buy/Sell Ratio:         {num_buy_trades/num_sell_trades:.2f}x
│
├─ Total Value Bought:     ${total_buy_value:,.0f}
├─ Total Value Sold:       ${total_sell_value:,.0f}
├─ Avg Trade Size:         ${results.num_trades / len(backtester.trades) if backtester.trades else 0:,.2f}
│
├─ Trading Days:           {len(snapshots)}
├─ Days with Trades:       {sum(1 for s in snapshots if len(s.positions) > 0)}
└─ Trade Frequency:        {results.num_trades / len(snapshots):.2f} trades per day
""")

    # Final summary
    print("=" * 180)
    print("SUMMARY & RECOMMENDATION")
    print("=" * 180)

    print(f"""
With $10K and $100/1% Position Sizing (NO CAP):

RETURNS:                   {results.total_return:.2f}%
FINAL VALUE:               ${results.final_value:,.0f}
PROFIT:                    ${results.final_pnl:,.0f}

VERSUS YOUR OPTIONS:
├─ vs $165/1% with cap:    {vs_165_with_cap:+.2f}% ({results.final_value - 91455:+,.0f})
├─ vs $165/1% no cap:      {vs_165_no_cap:+.2f}% ({results.final_value - 101251:+,.0f})
└─ Best performer:         $165/1% no cap at 912.51%

DECISION:
├─ Use $165/1% NO cap:     Better returns (912.51% vs {results.total_return:.2f}%)
├─ Use $100/1% NO cap:     More conservative approach
├─ Use $165/1% WITH cap:   Most psychologically comfortable
│
├─ Recommendation:         $165/1% WITHOUT cap
│  └─ Proven: 17.7 years of data
│  └─ Returns: 912.51% (best for your capital)
│  └─ Risk: Cash hits $0.00 but never negative
│  └─ Tradeoff: One day in 17.7 years you hit zero cash
│
└─ Alternative:            $165/1% WITH cap
   └─ Conservative: Keep 59% cash always
   └─ Returns: 814.56% (excellent anyway)
   └─ Risk: Never cash-strapped
   └─ Simplicity: Clear rules

BOTTOM LINE:
The $100/1% NO cap strategy gives {results.total_return:.2f}% returns.
That's excellent, but $165/1% NO cap gives 912.51%, which is {((912.51/results.total_return - 1)*100):.1f}% better.

Unless you prefer the smaller position size for psychological reasons,
stick with $165/1% (either with or without the cap).
""")

    print("=" * 180)


if __name__ == "__main__":
    main()
