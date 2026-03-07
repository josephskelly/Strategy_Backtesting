# Trading Backtesting System

Mean reversion backtester for ProShares leveraged ETFs with NLV-proportional position sizing.

## Strategy Overview

**Signal:** Buy when a ticker drops X% in a day; sell when it gains X%. Position size scales with the magnitude of the move and with current portfolio value (NLV-proportional).

- **Buy signal:** ticker falls → buy `nlv_pct × NLV × |move%|`
- **Sell signal:** ticker rises → sell proportionally
- **No z-score threshold** — every move triggers a proportional trade
- **NLV-proportional sizing:** as the portfolio compounds, position sizes grow automatically

## Quick Start

```bash
# Single ticker, 30-year daily backtest
python backtest_mean_regression.py TQQQ

# Last 10 years, weekly bars
python backtest_mean_regression.py TQQQ --years 10 --interval 1wk

# Enable 25% per-trade margin cap
python backtest_mean_regression.py TQQQ --cap

# Run all 51 ProShares leveraged ETFs and rank by return
python backtest_mean_regression.py --all --nlv-pct 1.65 --years 20
```

## CLI Reference

| Argument | Type | Default | Description |
|---|---|---|---|
| `ticker` | positional | — | Ticker to backtest (e.g. `TQQQ`, `URTY`) |
| `--all` | flag | off | Run all ETFs in `proshares_leveraged_etfs.csv` |
| `--nlv-pct PCT` | float | `1.65` | % of NLV to trade per 1% daily move |
| `--years N` | int | `30` | Years of history to fetch from Yahoo Finance |
| `--interval` | `1d` \| `1wk` | `1d` | Bar interval (daily or weekly) |
| `--cap` | flag | off | Cap each buy to 25% of current cash |

## Output Files

| File | Description |
|---|---|
| `{ticker}_weekly_balances.csv` | Weekly portfolio snapshot: positions, cash, net liquidation value |
| `etf_weekly_comparison.csv` | Ranked comparison across all ETFs (when using `--all`) |

## Core Backtester API

```python
from backtest_daily_rebalance_no_cap import DailyRebalanceBacktesterNoCap

backtester = DailyRebalanceBacktesterNoCap(
    prices_df=prices_df,          # DataFrame: index=dates, columns=tickers
    initial_capital=10_000,       # Starting cash
    nlv_proportional=True,        # Scale position size with portfolio growth
    nlv_pct_per_percent=1.65,     # 1.65% of NLV per 1% daily move
    margin_cap=None,              # None = no cap, 0.25 = 25% per-trade cap
)

results = backtester.run()

print(f"Return:    {results.total_return:.2f}%")
print(f"Final:     ${results.final_value:,.2f}")
print(f"Max DD:    {results.max_drawdown:.2f}%")
print(f"Sharpe:    {results.sharpe_ratio:.3f}")
print(f"Trades:    {results.num_trades}")
```

### Results Attributes

```python
results.total_return        # Total return %
results.final_value         # Final portfolio value $
results.final_pnl           # Profit/Loss $
results.max_drawdown        # Max drawdown %
results.sharpe_ratio        # Risk-adjusted return (annualized)
results.num_trades          # Total trades executed
results.avg_invested_pct    # Average % of portfolio deployed
results.avg_cash_pct        # Average % held as cash
results.min_cash            # Minimum cash balance reached $
results.went_negative_cash  # Did cash ever go negative?
results.snapshots           # List of daily PortfolioSnapshot objects
```

## Key Findings

| Strategy | Return | Final Value | Max DD | Notes |
|---|---|---|---|---|
| 1.65% NLV, no cap | 912.51% | $101,251 | -58.53% | Best raw performance |
| 1.65% NLV, 25% cap | 814.56% | $91,455 | -57.08% | Recommended for live trading |
| 1.00% NLV, no cap | 701.87% | $80,187 | -60.94% | Underperforms — avoid |

*Tested on $10K starting capital, 2008–2026 (17.7 years).*

**Key insight:** Smaller sizing loses ~211 percentage points of return with no meaningful reduction in drawdown. The 25% cap costs ~100pp of return but limits margin demands.

## Capital Requirements

| Sizing (NLV%) | Peak Margin Needed |
|---|---|
| 0.50% | ~$76K |
| 1.00% | ~$152K |
| 1.65% | ~$251K |
| 2.50% | ~$381K |

Real accounts must have sufficient margin available to avoid forced liquidations.

## Directory Structure

```
Strategy_Backtesting/
├── backtest_mean_regression.py          # PRIMARY: CLI-driven backtest runner
├── backtest_daily_rebalance_no_cap.py   # Core backtester engine
├── backtest_daily_rebalance.py          # Backtester with fixed 25% cap (legacy)
├── proshares_leveraged_etfs.csv         # 51 ProShares leveraged ETF tickers
│
├── ADDITIONAL ANALYSIS SCRIPTS:
├── backtest_leveraged_30year.py         # 30-year comparison
├── backtest_leverage_comparison.py      # Multi-strategy comparison
├── analyze_position_sizing.py           # Position sizing analysis
├── backtest_annual_comparison.py        # Annual return breakdowns
│
├── DOCUMENTATION:
├── README.md                            # This file
├── CLAUDE.md                            # AI assistant guide
├── TESTING.md                           # Test procedures
├── MARGIN_CAP_ANALYSIS.md               # 25% cap trade-off analysis
├── CAPITAL_REQUIREMENT_ANALYSIS.md      # Capital needs by position size
├── POSITION_SIZING_CAPITAL_GUIDE.md     # Complete sizing guide
├── 10K_POSITION_SIZING_ANALYSIS.md      # $10K capital analysis
│
└── _archive/                            # Old/experimental scripts
```

## ETF Universe

`proshares_leveraged_etfs.csv` contains 51 ProShares leveraged ETFs across categories:

- **Broad Market** (UPRO, SSO, QLD, TQQQ, …)
- **Sector** (CURE, ROM, UDOW, …)
- **International** (EET, EFO, EZJ, …)
- **Fixed Income** (UBT, UST, …)
- **Commodities / Alternatives** (UGL, AGQ, …)

## Implementation Notes

- Data fetched from Yahoo Finance API (free, up to 30 years of history)
- Closing prices only — no intraday trading or slippage modeling
- No commissions or taxes modeled
- Margin/leverage constraints depend on your broker account type
