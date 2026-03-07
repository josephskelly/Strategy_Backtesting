# CLAUDE.md - Trading Backtesting System

## Project Overview

**Trading Backtesting System**: A comprehensive backtester for mean reversion trading strategies across 11 US leveraged sector ETFs (2x leverage). The system tests position sizing configurations and compares returns against buy-and-hold benchmarks.

**Current Focus**: Analyzing optimal position sizing for initial capital ranging from $10K to $100K+.

### Key Metrics Being Tracked
- **Returns**: Total return % over 17.7 years (2008-05-22 to 2026-02-13)
- **Capital Requirements**: Peak margin needed for different position sizes
- **Drawdowns**: Maximum peak-to-trough declines during crises
- **Sharpe Ratio**: Risk-adjusted returns
- **Trade Statistics**: Win rates, trade frequency, sector performance

## Directory Structure

```
Strategy_Backtesting/
├── CLAUDE.md                                    # This file (AI assistant guide)
├── README.md                                    # Project overview
├── TESTING.md                                   # Test procedures
├── MARGIN_CAP_ANALYSIS.md                       # Analysis of 25% margin caps
├── CAPITAL_REQUIREMENT_ANALYSIS.md              # Capital needs by position size
├── POSITION_SIZING_CAPITAL_GUIDE.md             # Complete sizing guide
├── 10K_POSITION_SIZING_ANALYSIS.md              # $10K starting capital analysis
│
├── PRIMARY SCRIPT:
├── backtest_mean_regression.py                  # CLI runner: any ticker or all ETFs
├── proshares_leveraged_etfs.csv                 # 51 ProShares leveraged ETF tickers
│
├── BACKTESTING ENGINE:
├── backtest_daily_rebalance_no_cap.py           # Core backtester (supports margin_cap param)
├── backtest_daily_rebalance.py                  # Legacy backtester with hardcoded 25% cap
│
├── ADDITIONAL ANALYSIS SCRIPTS:
├── backtest_leveraged_30year.py                 # 30-year comparison
├── backtest_leverage_comparison.py              # Multi-strategy comparison
├── analyze_position_sizing.py                   # Position sizing analysis tool
├── backtest_annual_comparison.py                # Annual return comparisons
│
├── SUPPORTING SCRIPTS:
├── backtest.py                                  # Basic backtest runner
├── backtest_engine.py                           # Generic backtest class
├── backtest_dips_bounces.py                     # Dip/bounce analysis
│
├── OUTPUT FILES:
├── backtest_annual_comparison.csv               # Annual results by year
├── backtest_daily_rebalance_results.csv         # Daily backtest results
│
└── _archive/                                    # Old/experimental scripts
```

## Current Status & Key Findings

### The Main Question
**What's the optimal position sizing for $10K starting capital?**

### Current Answer
| Strategy | Return | Final Value | Drawdown | Recommendation |
|---|---|---|---|---|
| **$165/1% NO cap** | 912.51% | $101,251 | -58.53% | ⭐ Best Performance |
| **$165/1% WITH cap** | 814.56% | $91,455 | -57.08% | ✅ Recommended (safe) |
| $100/1% NO cap | 701.87% | $80,187 | -60.94% | ❌ Avoid |

**Key Insight**: Don't use smaller position sizing ($100/1%). It costs 211 percentage points in returns (vs $165/1% no cap) while providing NO additional safety (still hits $0.00 cash).

### Capital Requirements by Position Size
- **$50/1%**: Peak ~$76K margin
- **$100/1%**: Peak ~$152K margin
- **$165/1%**: Peak ~$251K margin
- **$250/1%**: Peak ~$381K margin

### The 25% Margin Cap
- Purpose: Prevent over-leverage during simultaneous sector crashes
- Effect: Limits maximum positions to 25% of portfolio at any time
- Trade-off: Reduces max returns by ~100 percentage points but provides safety

## Core Backtester API

### Main Class: `DailyRebalanceBacktesterNoCap`

Located in: `backtest_daily_rebalance_no_cap.py`

```python
from backtest_daily_rebalance_no_cap import DailyRebalanceBacktesterNoCap

backtester = DailyRebalanceBacktesterNoCap(
    prices_df=prices_df,            # DataFrame: index=dates, columns=tickers
    initial_capital=10000,          # Starting cash
    nlv_proportional=True,          # Scale position size with portfolio growth
    nlv_pct_per_percent=1.65,       # 1.65% of NLV per 1% daily move
    margin_cap=None,                # None = no cap, 0.25 = 25% per-trade cap
)

results = backtester.run()

# Access results
print(f"Return: {results.total_return:.2f}%")
print(f"Final Value: ${results.final_value:,.2f}")
print(f"Max Drawdown: {results.max_drawdown:.2f}%")
print(f"Sharpe: {results.sharpe_ratio:.3f}")
```

### Results Object Attributes

```python
results.total_return           # Total return %
results.final_value            # Final portfolio value $
results.final_pnl              # Profit/Loss $
results.max_drawdown           # Max DD %
results.sharpe_ratio           # Risk-adjusted return
results.num_trades             # Total trades executed
results.avg_invested_pct       # Average % invested
results.avg_cash_pct           # Average % in cash
results.min_cash               # Minimum cash reached $
results.went_negative_cash     # Boolean: did cash go negative?
results.sector_performance     # Dict of per-sector stats
results.snapshots              # List of daily portfolio snapshots
```

## Common Tasks

### Running a New Backtest

1. **Single ticker** (primary entry point):
```bash
python backtest_mean_regression.py TQQQ                          # 30y daily, default sizing
python backtest_mean_regression.py TQQQ --years 10              # last 10 years
python backtest_mean_regression.py TQQQ --interval 1wk          # weekly bars
python backtest_mean_regression.py TQQQ --cap                   # enable 25% margin cap
python backtest_mean_regression.py TQQQ --nlv-pct 2.0          # custom sizing
```

2. **All 51 ProShares ETFs** (ranked comparison):
```bash
python backtest_mean_regression.py --all
python backtest_mean_regression.py --all --nlv-pct 1.65 --years 5
```

3. **Annual breakdown**:
```bash
python backtest_annual_comparison.py      # Year-by-year results
```

### Creating a New Backtest Analysis

Template:
```python
import pandas as pd
from backtest_mean_regression import fetch_closes
from backtest_daily_rebalance_no_cap import DailyRebalanceBacktesterNoCap

# Fetch data for any ticker
prices_df = fetch_closes("TQQQ", range_="10y", interval="1d")

# Run backtest
backtester = DailyRebalanceBacktesterNoCap(
    prices_df=prices_df,
    initial_capital=10_000,
    nlv_proportional=True,
    nlv_pct_per_percent=1.65,   # 1.65% of NLV per 1% move
    margin_cap=None,             # or 0.25 for 25% cap
)
results = backtester.run()

print(f"Return: {results.total_return:.2f}%")
print(f"Final: ${results.final_value:,.2f}")
print(f"Max DD: {results.max_drawdown:.2f}%")
```

### Adding Analysis Documents

When you discover important findings:
1. Create a `.md` file with clear structure:
   - Executive summary
   - Detailed analysis
   - Comparison tables
   - Recommendations
2. Include relevant test output
3. Commit with descriptive message

Example: `10K_POSITION_SIZING_ANALYSIS.md`

## Trading Strategy Details

### Position Sizing Logic

**Position Size Calculation**:
```
For each sector on each day:
1. Calculate 20-day rolling mean and std dev
2. Calculate z-score: (price - mean) / std_dev
3. If z-score <= -1.0: BUY signal
4. If z-score >= +1.0: SELL signal
5. Size = abs(z-score) * trade_amount_per_percent
```

**Example**:
- Sector drops 3% (z-score = -1.5)
- Position size = 1.5 × $165 = $247.50
- Buy $247.50 of that sector

### Daily Rebalancing

- Prices fetched at market close each day
- Signals generated based on closing prices
- Trades executed at closing prices
- No intraday trading or slippage adjustment

### Capital Management

**Without cap** (NO CAP):
- All available cash can be deployed
- Peak requirement can reach 250%+ of starting capital
- Must have sufficient margin available

**With cap** (25%):
- Maximum position per sector: 25% of portfolio
- Limits simultaneous sector exposure
- Reduces drawdowns and margin requirements

## Sector ETFs Being Tracked

11 US leveraged (2x) sector ETFs:

| Ticker | Sector | Type |
|---|---|---|
| UCC | Commodities | 2x |
| UYG | Financials | 2x |
| LTL | Long-Term Treasury | 2x |
| DIG | Oil & Gas | 2x |
| UGE | Renewable Energy | 2x |
| ROM | Real Estate | 2x |
| UYM | Metals & Mining | 2x |
| RXL | Healthcare | 2x |
| UXI | Semiconductors | 2x |
| URE | Real Estate (alt) | 2x |
| UPW | Utilities | 2x |

Data sourced from Yahoo Finance API via `_yahoo_chart()` function.

## Git Workflow

### Branch: `claude/extract-etf-data-csv-i6lLh`

All development happens on this feature branch.

### Commit Guidelines

1. **When running backtests**, commit results with:
   ```
   Backtest: [Description of test]

   - Starting capital: $X
   - Position sizing: $X/1%
   - Cap: [None/25%]
   - Return: X%
   - Final value: $X
   ```

2. **When analyzing findings**, commit documentation with:
   ```
   Analysis: [Topic]

   - Key finding 1
   - Key finding 2
   - Recommendation
   ```

3. **Always include the session URL** at the end of commit messages:
   ```
   https://claude.ai/code/session_01Wo68NQpzmdqMkeBnsQ3FeS
   ```

### Push Commands

```bash
# Always use -u flag for new branches
git push -u origin claude/extract-etf-data-csv-i6lLh

# Regular pushes
git push origin claude/extract-etf-data-csv-i6lLh
```

## Testing & Validation

See `TESTING.md` for detailed test procedures.

Quick checks:
1. Verify data fetches (2008-2026, 4461 trading days)
2. Check final values match calculations
3. Validate performance metrics (Sharpe, drawdowns)
4. Confirm sector P&Ls sum to total

## Known Issues & Limitations

### Data Issues
- Yahoo Finance API occasionally rate-limits or times out
- Need to handle retries with exponential backoff
- Some older tickers may have missing data

### Backtest Limitations
- Assumes closing prices (no intraday trading)
- No slippage or commission modeling
- No tax implications
- Perfect execution (no partial fills)
- Historical data only (no forward testing)

### Position Sizing Constraints
- Starting capital too small ($10K) leads to tight constraints
- Peak margin requirements can be 25x+ initial capital
- Real trading requires sufficient available margin
- Leverage restrictions apply in real accounts

## Performance Benchmarks

For comparison, test results should include:

**Baseline (Buy-and-Hold S&P 500)**:
- ~10-15% annual return (historically)
- ~30-50% max drawdowns

**Your Strategy (Mean Reversion)**:
- 39-51% annualized (depending on sizing)
- 58-60% max drawdowns
- Superior risk-adjusted returns (Sharpe 0.57-0.60)

## Key Decision Framework

### For Different Starting Capitals

| Capital | Recommended Sizing | Expected Return |
|---|---|---|
| $10,000 | $165/1% with cap | 814.56% |
| $25,000 | $165/1% no cap | 912.51% |
| $50,000 | $250/1% no cap | ~1100%+ |
| $100,000+ | Full sizing | Maximum |

### Position Sizing Rules

1. **With <$25K**: Use position sizing with 25% cap
2. **With $25K-$100K**: Can use no cap, manage margin carefully
3. **With >$100K**: Full sizing recommended
4. **Never use smaller sizes**: $100/1% for $10K loses 23% returns

### When to Use Margin Cap

Use 25% cap when:
- Limited margin available
- Prefer conservative approach
- Want psychological comfort
- Can accept 100pp return reduction

Don't use cap when:
- Sufficient margin available ($250K+)
- Comfortable with leverage
- Want maximum returns
- Can handle brief $0.00 cash days

## Useful Analysis Commands

```bash
# Run full 30-year backtest
python backtest_leveraged_30year.py

# Compare multiple strategies
python backtest_leverage_comparison.py

# Analyze position sizing options
python analyze_position_sizing.py

# Test specific capital/sizing combo
python test_10k_100_per_percent.py
```

## Output Interpretation

When reviewing backtest output:

```
PERFORMANCE METRICS:
├─ Total Return:         X%        # Total gain over period
├─ Final Value:          $X        # Starting capital + profit
├─ Max Drawdown:         -X%       # Worst decline from peak
├─ Sharpe Ratio:         X.XXX     # Risk-adjusted return
│                                  # (0.5+ is good, 1.0+ is excellent)
├─ Total Trades:         X         # Number of buy/sell signals
└─ Avg Invested:         X%        # Capital deployed on average

RISK ANALYSIS:
├─ Minimum Value:        $X        # Lowest portfolio value reached
├─ Maximum Value:        $X        # Highest portfolio value
└─ Daily Volatility:     $X        # Average daily swing
```

## Future Enhancements

Potential improvements (if requested):

1. **Real-time trading integration** - Connect to brokers
2. **Stop-loss mechanisms** - Protect against catastrophic losses
3. **Machine learning** - Optimize z-score thresholds
4. **Options strategies** - Hedge leverage with puts
5. **Sector rotation** - Add trend filtering
6. **Walk-forward testing** - Optimize parameters over time
7. **Monte Carlo simulation** - Test robustness
8. **Real commission modeling** - Account for trading costs

## Questions for New Analysis

Before starting a new analysis, ask:

1. **What capital amount are we analyzing?** ($10K, $25K, $100K?)
2. **With or without the 25% margin cap?**
3. **Which position sizes to compare?** ($50, $100, $165, $250/1%?)
4. **Specific time period?** (30 years, decade, specific crisis?)
5. **Key metric to optimize?** (Return, Sharpe, Drawdown, Capital Efficiency?)

## Resources

- **Data**: Yahoo Finance API (free, 30-year history available)
- **Date Range**: 2008-05-22 to 2026-02-13 (17.7 years of data)
- **Trading Days**: 4,461 trading days
- **Sectors**: 11 leveraged US sector ETFs

## Contact & Session Info

- **Session URL**: https://claude.ai/code/session_01Wo68NQpzmdqMkeBnsQ3FeS
- **Branch**: `claude/backtest-stddev-trading-4wIY0`
- **Owner**: josephskelly

---

**Last Updated**: 2026-02-16
**Current Focus**: Optimal position sizing for $10K+ starting capital
**Status**: Active development and analysis
