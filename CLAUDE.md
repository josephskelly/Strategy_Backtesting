# CLAUDE.md - Trading Backtesting System

## Project Overview

**Trading Backtesting System**: A mean-reversion backtester for ProShares leveraged ETFs with a pluggable indicator architecture. The system tests position sizing configurations and compares returns against buy-and-hold benchmarks.

**Current Focus**: Analyzing optimal position sizing for initial capital ranging from $10K to $100K+.

### Key Metrics Being Tracked
- **Returns**: Total return % over 17.7 years (2008-05-22 to 2026-02-13)
- **Capital Requirements**: Peak margin needed for different position sizes
- **Drawdowns**: Maximum peak-to-trough declines during crises
- **Sharpe Ratio**: Risk-adjusted returns (annualized, ×√252)
- **Trade Statistics**: Win rates, trade frequency, sector performance

## Directory Structure

```
Strategy_Backtesting/
├── CLAUDE.md                                    # This file (AI assistant guide)
├── README.md                                    # Project overview
│
├── ENTRY POINT:
├── backtest.py                                  # Single CLI runner — any ticker or all ETFs
│
├── ENGINE:
├── engine.py                                    # BacktestEngine + dataclasses
│
├── INDICATORS:
├── indicators/
│   ├── __init__.py
│   ├── daily_return.py                          # Buy dips/sell rips (default)
│   └── zscore.py                                # Rolling z-score mean-reversion
│
├── DATA:
├── proshares_leveraged_etfs.csv                 # 51 ProShares leveraged ETF tickers
│
├── OUTPUT:
├── output/
│   ├── {ticker}_weekly_balances.csv             # Per-ETF weekly snapshots
│   └── etf_weekly_comparison.csv               # Ranked comparison (--all)
│
├── DOCUMENTATION:
├── MARGIN_CAP_ANALYSIS.md                       # Analysis of 25% margin caps
├── CAPITAL_REQUIREMENT_ANALYSIS.md              # Capital needs by position size
├── POSITION_SIZING_CAPITAL_GUIDE.md             # Complete sizing guide
├── 10K_POSITION_SIZING_ANALYSIS.md              # $10K starting capital analysis
│
└── _archive/                                    # All old/superseded scripts
```

## Current Status & Key Findings

### The Main Question
**What's the optimal position sizing for $10K starting capital?**

### Current Answer
| Strategy | Return | Final Value | Drawdown | Recommendation |
|---|---|---|---|---|
| **1.65% NLV, no cap** | 912.51% | $101,251 | -58.53% | Best Performance |
| **1.65% NLV, with cap** | 814.56% | $91,455 | -57.08% | Recommended (safe) |
| 1.00% NLV, no cap | 701.87% | $80,187 | -60.94% | Avoid |

**Key Insight**: Smaller position sizing ($100/1%) costs 211 percentage points in returns vs 1.65% NLV while providing NO additional safety (still hits $0.00 cash).

### Capital Requirements by NLV%
- **0.50% NLV**: Peak ~$76K margin
- **1.00% NLV**: Peak ~$152K margin
- **1.65% NLV**: Peak ~$251K margin
- **2.50% NLV**: Peak ~$381K margin

### The 25% Margin Cap
- Purpose: Prevent over-leverage during simultaneous sector crashes
- Effect: Limits each buy to 25% of current cash
- Trade-off: Reduces max returns by ~100 percentage points but limits margin demands

## Architecture

### `engine.py` — BacktestEngine

The core portfolio loop. Owns portfolio state, trade execution, snapshots, and results computation. Delegates signal generation entirely to the indicator.

```python
from engine import BacktestEngine, BacktestResults

engine = BacktestEngine(
    prices_df=prices_df,      # DataFrame: index=dates, columns=tickers
    indicator=indicator,       # any object with a signal() method
    initial_capital=10_000,
)
results: BacktestResults = engine.run()
```

### `BacktestResults` attributes

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
results.sector_performance  # {ticker: {num_trades, pnl, return_pct, num_wins, win_rate}}
results.snapshots           # List of daily PortfolioSnapshot objects
```

### Indicator Plugin Interface

Each indicator `.py` file must export a class `Indicator` with a `signal()` method, and optionally a module-level `add_args()` function.

```python
def add_args(parser) -> None:
    """Register indicator-specific CLI flags."""
    parser.add_argument("--my-param", type=float, default=1.0)


class Indicator:
    def __init__(self, **kwargs):
        """Receives all parsed CLI args as keyword arguments."""
        self.my_param = kwargs.get("my_param", 1.0)

    def signal(
        self,
        ticker: str,
        date,
        current_price: float,
        prev_price: float | None,
        prices_history,      # pd.Series of all closes up to (and including) date
        position: float,     # shares currently held in this ticker
        cash: float,
        nlv: float,          # net liquidation value (cash + invested)
    ) -> tuple[str, float]:
        """
        Returns (action, trade_value_$) where action is:
            'BUY'  — buy trade_value_$ worth of ticker
            'SELL' — sell trade_value_$ worth of ticker
            'HOLD' — do nothing
        """
        ...
```

## Common Tasks

### Running a New Backtest

```bash
# Single ticker — default indicator (daily_return), 30y daily
python backtest.py TQQQ

# Custom NLV sizing
python backtest.py TQQQ --nlv-pct 2.0

# Enable 25% margin cap
python backtest.py TQQQ --cap

# Switch indicator
python backtest.py TQQQ --indicator indicators/zscore.py
python backtest.py TQQQ --indicator indicators/zscore.py --z-threshold 1.5 --lookback 30

# Limit date range / bar interval
python backtest.py TQQQ --years 10
python backtest.py TQQQ --interval 1wk

# All 51 ProShares ETFs — ranked comparison
python backtest.py --all
python backtest.py --all --nlv-pct 1.65 --years 5
```

### Programmatic Usage

```python
import pandas as pd
from engine import BacktestEngine
from indicators.daily_return import Indicator

# Or fetch with the helper in backtest.py:
# from backtest import fetch_closes
# prices_df = fetch_closes("TQQQ", range_="10y", interval="1d")

indicator = Indicator(nlv_pct=1.65, cap=False)

engine = BacktestEngine(
    prices_df=prices_df,
    indicator=indicator,
    initial_capital=10_000,
)
results = engine.run()

print(f"Return: {results.total_return:.2f}%")
print(f"Final:  ${results.final_value:,.2f}")
print(f"Max DD: {results.max_drawdown:.2f}%")
```

### Writing a Custom Indicator

1. Create `my_indicator.py` implementing the plugin interface (see above).
2. Run: `python backtest.py TQQQ --indicator my_indicator.py`
3. Any flags registered in `add_args()` become available on the CLI automatically.

## Trading Strategy Details

### `indicators/daily_return.py` (default)

Signal logic:
```
For each ticker on each day:
  daily_return% = (close - prev_close) / prev_close × 100
  trade_amount  = (nlv_pct / 100) × current_NLV

  if daily_return% < 0:
      BUY  abs(daily_return%) × trade_amount
  elif daily_return% > 0 and position > 0:
      SELL daily_return% × trade_amount
  else:
      HOLD
```

Optional `--cap` limits each BUY to `min(trade_value, cash × 0.25)`.

### `indicators/zscore.py`

Signal logic:
```
For each ticker on each day:
  window   = last lookback closing prices
  z_score  = (current_price - mean(window)) / std(window)

  if position == 0 and z_score ≤ -z_threshold:
      BUY  min(cash, nlv × max_allocation) × (|z_score| / z_threshold)
  elif position > 0 and z_score ≥ +z_threshold:
      SELL entire position
  else:
      HOLD
```

### Capital Management

**Without cap** (default):
- All available cash can be deployed
- Peak requirement can reach 250%+ of starting capital

**With `--cap`** (daily_return indicator only):
- Each buy limited to 25% of current cash
- Limits simultaneous sector exposure

## Git Workflow

### Branch: `claude/extract-etf-data-csv-i6lLh`

All development happens on this feature branch.

### Commit Guidelines

1. **Backtests**:
   ```
   Backtest: [Description]

   - Indicator: daily_return / zscore / custom
   - Capital: $X  |  NLV%: X  |  Cap: yes/no
   - Return: X%  |  Final: $X  |  Max DD: X%
   ```

2. **Analysis findings**:
   ```
   Analysis: [Topic]

   - Key finding 1
   - Key finding 2
   - Recommendation
   ```

3. **Always append the session URL**:
   ```
   https://claude.ai/code/session_01JXpfWHaJDxTEiozGHRkSz4
   ```

### Push Commands

```bash
git push -u origin claude/extract-etf-data-csv-i6lLh
```

## Known Issues & Limitations

### Data Issues
- Yahoo Finance API occasionally rate-limits or times out
- Some older tickers may have limited history (< requested years)

### Backtest Limitations
- Closing prices only — no intraday trading or slippage
- No commissions or taxes modeled
- Perfect execution assumed (no partial fills)
- Historical data only (no forward testing)

### Position Sizing Constraints
- $10K starting capital is tight; peak margin can be 25× initial capital
- Real trading requires sufficient margin available at the broker
- Leverage restrictions vary by account type and jurisdiction

## Performance Benchmarks

**Baseline (Buy-and-Hold S&P 500)**:
- ~10–15% annual return (historically)
- ~30–50% max drawdowns

**Daily-return indicator, 1.65% NLV, no cap**:
- ~39–51% annualized (depending on ticker universe)
- ~58–60% max drawdowns
- Sharpe 0.57–0.60

## Key Decision Framework

| Capital | Recommended | Expected Return |
|---|---|---|
| $10,000 | 1.65% NLV with cap | 814.56% |
| $25,000 | 1.65% NLV no cap | 912.51% |
| $50,000 | 2.50% NLV no cap | ~1100%+ |
| $100,000+ | Full sizing | Maximum |

**Cap guidance:**
- Use `--cap` with < $25K available margin, or for a more conservative approach
- Skip `--cap` when sufficient margin (>$250K) is available and max returns are the goal

## Resources

- **Data**: Yahoo Finance API (free, up to 30 years of history)
- **Date Range**: 2008-05-22 to 2026-02-13 (17.7 years of data)
- **Trading Days**: ~4,461 trading days
- **ETF Universe**: 51 ProShares leveraged ETFs (`proshares_leveraged_etfs.csv`)

## Session Info

- **Session URL**: https://claude.ai/code/session_01JXpfWHaJDxTEiozGHRkSz4
- **Branch**: `claude/extract-etf-data-csv-i6lLh`
- **Owner**: josephskelly

## Code Review TODO (2026-03-08)

### HIGH Priority Bugs

- [x] **Sharpe Ratio Calculation is Wrong** (`engine.py:244`)
   - Divides daily P&L by `initial_capital` instead of prior day's portfolio value
   - Increasingly understates volatility as portfolio grows (denominator ~10x too small at 912% return)
   - Fix: `daily_returns = np.diff(total_values) / total_values[:-1]`

- [ ] **Sector P&L Uses Broken Trade Pairing** (`engine.py:267-276`)
   - `zip(buys, sells)` silently truncates to shorter list
   - Mean-reversion buys/sells at different quantities/frequencies, so positional pairing is incorrect
   - Fix: Use weighted-average cost basis approach instead

- [ ] **Win Rate Has Same Pairing Bug** (`engine.py:278`)
   - Same `zip(buys, sells)` truncation issue
   - Numerator uses paired count, denominator uses `len(buys)` — semantically inconsistent

### LOW Priority Issues

- [ ] **Sharpe uses population stddev** (`engine.py:247`) — `np.std()` defaults to `ddof=0`; finance convention uses `ddof=1`
- [ ] **`numpy` missing from `requirements.txt`** — imported directly but not listed as dependency
- [ ] **`sector_trades` naming misleading** (`engine.py:115`) — tracks per-ticker, not per-sector
- [ ] **Hardcoded magic numbers** — `$10` min trade, `0.001` position threshold, `252` trading days, `0.25` margin cap
- [ ] **No indicator `signal()` validation** (`backtest.py:55-57`) — malformed indicators crash at runtime
- [x] **No CI/CD pipeline** — tests exist but nothing runs them automatically
- [ ] **Output CSVs committed to git** — 62 reproducible files tracked in `output/`

### What's Done Well
- Clean engine/indicator plugin separation
- Proper NaN and division-by-zero guards
- Sell capping prevents negative positions
- Comprehensive documentation (2,191 lines)
- Well-managed archive (49 legacy files isolated)
- Good test suite (87 tests across 4 modules)

---

**Last Updated**: 2026-03-08
**Status**: Active development
