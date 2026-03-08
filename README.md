# Trading Backtesting System

Mean-reversion backtester for ProShares leveraged ETFs with a pluggable indicator system.

## Architecture

```
backtest.py          ← single CLI entry point
engine.py            ← BacktestEngine + dataclasses (portfolio loop, results)
indicators/
  daily_return.py    ← buy dips / sell rips based on daily % move  (default)
  zscore.py          ← rolling z-score mean-reversion
proshares_leveraged_etfs.csv   ← 51 ProShares leveraged ETF tickers
output/              ← generated CSV files
_archive/            ← old scripts
```

## Quick Start

```bash
# Single ticker, 30-year daily backtest (default indicator: daily_return)
python backtest.py TQQQ

# Custom sizing
python backtest.py TQQQ --nlv-pct 2.0

# Enable 25% per-trade margin cap
python backtest.py TQQQ --cap

# Switch to z-score indicator
python backtest.py TQQQ --indicator indicators/zscore.py

# Use your own custom indicator
python backtest.py TQQQ --indicator path/to/my_indicator.py

# Last 10 years, weekly bars
python backtest.py TQQQ --years 10 --interval 1wk

# Run all 51 ProShares leveraged ETFs and rank by return
python backtest.py --all
python backtest.py --all --nlv-pct 1.65 --years 20
```

## CLI Reference

### Base flags (always available)

| Argument | Type | Default | Description |
|---|---|---|---|
| `ticker` | positional | — | Ticker to backtest (e.g. `TQQQ`, `URTY`) |
| `--all` | flag | off | Run all ETFs in `proshares_leveraged_etfs.csv` |
| `--indicator PATH` | str | `indicators/daily_return.py` | Path to indicator `.py` module |
| `--years N` | int | `30` | Years of history to fetch from Yahoo Finance |
| `--interval` | `1d` \| `1wk` | `1d` | Bar interval (daily or weekly) |

### `indicators/daily_return.py` flags

| Argument | Type | Default | Description |
|---|---|---|---|
| `--nlv-pct PCT` | float | `1.65` | % of NLV to trade per 1% daily move |
| `--cap` | flag | off | Cap each buy to 25% of current cash |

### `indicators/zscore.py` flags

| Argument | Type | Default | Description |
|---|---|---|---|
| `--lookback N` | int | `20` | Rolling window (bars) for mean/std |
| `--z-threshold F` | float | `1.0` | Z-score magnitude to trigger buy/sell |
| `--max-allocation F` | float | `0.30` | Max fraction of NLV per sector |

## Output Files

| File | Description |
|---|---|
| `output/{ticker}_weekly_balances.csv` | Weekly portfolio snapshot: positions, cash, net liquidation value |
| `output/etf_weekly_comparison.csv` | Ranked comparison across all ETFs (when using `--all`) |

## Engine API

```python
from engine import BacktestEngine
from indicators.daily_return import Indicator

indicator = Indicator(nlv_pct=1.65, cap=False)

engine = BacktestEngine(
    prices_df=prices_df,      # DataFrame: index=dates, columns=tickers
    indicator=indicator,
    initial_capital=10_000,
)
results = engine.run()

print(f"Return:  {results.total_return:.2f}%")
print(f"Final:   ${results.final_value:,.2f}")
print(f"Max DD:  {results.max_drawdown:.2f}%")
print(f"Sharpe:  {results.sharpe_ratio:.3f}")
print(f"Trades:  {results.num_trades}")
```

### BacktestResults attributes

```python
results.total_return        # Total return %
results.final_value         # Final portfolio value $
results.final_pnl           # Profit/Loss $
results.max_drawdown        # Max drawdown %
results.sharpe_ratio        # Risk-adjusted return (annualized, √252)
results.num_trades          # Total trades executed
results.avg_invested_pct    # Average % of portfolio deployed
results.avg_cash_pct        # Average % held as cash
results.min_cash            # Minimum cash balance reached $
results.went_negative_cash  # Did cash ever go negative?
results.sector_performance  # {ticker: {num_trades, pnl, return_pct, num_wins, win_rate}}
results.snapshots           # List of daily PortfolioSnapshot objects
```

## Writing a Custom Indicator

Create any `.py` file with:

```python
# my_indicator.py

def add_args(parser) -> None:
    """Register indicator-specific CLI flags (optional)."""
    parser.add_argument("--my-param", type=float, default=1.0)


class Indicator:
    def __init__(self, **kwargs):
        self.my_param = kwargs.get("my_param", 1.0)

    def signal(
        self,
        ticker: str,
        date,
        current_price: float,
        prev_price: float | None,
        prices_history,          # pd.Series of all closes up to today
        position: float,         # shares currently held
        cash: float,
        nlv: float,              # net liquidation value
    ) -> tuple[str, float]:
        """Return ('BUY'/'SELL'/'HOLD', trade_value_$)."""
        ...
```

Run it with:
```bash
python backtest.py TQQQ --indicator my_indicator.py --my-param 2.0
```

## Built-in Indicators

### `indicators/daily_return.py` (default)

Buys when a ticker drops and sells when it rises, proportional to the daily move:

- **Buy signal:** daily return < 0 → buy `nlv_pct × NLV × |return%|`
- **Sell signal:** daily return > 0 (with position) → sell proportionally
- **Optional cap:** `--cap` limits each buy to 25% of current cash

### `indicators/zscore.py`

Buys/sells based on how far price has deviated from its rolling mean:

- **Buy signal:** z-score ≤ −threshold → buy, sized by z-score strength × max_allocation
- **Sell signal:** z-score ≥ +threshold → sell entire position
- Requires at least `--lookback` bars of history before generating signals

## Key Findings

| Strategy | Return | Final Value | Max DD | Notes |
|---|---|---|---|---|
| 1.65% NLV, no cap | 912.51% | $101,251 | -58.53% | Best raw performance |
| 1.65% NLV, 25% cap | 814.56% | $91,455 | -57.08% | Recommended for live trading |
| 1.00% NLV, no cap | 701.87% | $80,187 | -60.94% | Underperforms — avoid |

*Tested on $10K starting capital, 2008–2026 (17.7 years), `indicators/daily_return.py`.*

**Key insight:** Smaller sizing loses ~211 percentage points of return with no meaningful reduction in drawdown. The 25% cap costs ~100pp of return but limits margin demands.

## Capital Requirements

| NLV% sizing | Peak Margin Needed |
|---|---|
| 0.50% | ~$76K |
| 1.00% | ~$152K |
| 1.65% | ~$251K |
| 2.50% | ~$381K |

Real accounts must have sufficient margin available to avoid forced liquidations.

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
