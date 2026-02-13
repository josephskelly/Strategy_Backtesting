# Trading Backtesting System

Mean reversion portfolio backtester with dynamic shared capital allocation across 11 US sector ETFs.

## Strategy Overview

**Mean Reversion with Dynamic Capital Allocation:**
- **Capital:** Single $10,000 portfolio shared across all sectors
- **Max per Sector:** 30% ($3,000) to prevent concentration
- **Buy Signal:** Z-score ≤ -1.0 (price 1+ std dev below 20-day mean)
- **Sell Signal:** Z-score ≥ +1.0 (price 1+ std dev above 20-day mean)
- **Position Sizing:** Linear scaling (0-100% of available capital based on z-score)

## Performance (2-Year Backtest)

- **Final Value:** $13,116.09
- **Total Return:** 31.16%
- **Max Drawdown:** -17.36%
- **Sharpe Ratio:** 1.00
- **Total Trades:** 173
- **Capital Deployed:** 67.86% avg

## Directory Structure

```
trading_backtesting/
├── backtest_engine.py              # Core backtester class
├── backtest.py                     # Main backtest runner
├── backtest_random_periods.py      # Random period testing
├── sector_etfs.py                  # Sector ETF data fetcher
└── README.md                       # This file
```

## Usage

### Single Backtest

Run a standard 2-year backtest:

```bash
python backtest.py
```

Custom date range:

```bash
python backtest.py --range 1y   # 1 year
python backtest.py --range 5y   # 5 years
```

### Random Period Testing

Test across 10 random 2-year periods:

```bash
python backtest_random_periods.py
```

Custom number of periods:

```bash
python backtest_random_periods.py --periods 20
```

## Output Files

- `backtest_results.csv` - Sector-by-sector results from single backtest
- `mean_reversion_random_periods.csv` - Strategy results across random periods
- `buyhold_random_periods.csv` - Buy-and-hold benchmark results
- `comparison_random_periods.csv` - Side-by-side comparison

## Key Metrics Explained

- **Return %:** Total portfolio return including P&L
- **Max Drawdown:** Largest peak-to-trough decline (%)
- **Sharpe Ratio:** Risk-adjusted return (annualized, 252 trading days)
- **Win Rate %:** Percentage of trades that were profitable
- **Capital Deployed:** Average % of portfolio invested (vs idle cash)

## Module Reference

### `backtest_engine.py`

Core backtesting engine with the `PortfolioStddevBacktester` class:

```python
from backtest_engine import PortfolioStddevBacktester
from sector_etfs import fetch_sector_closes

# Fetch data
closes = fetch_sector_closes(range_="2y")

# Run backtest
backtester = PortfolioStddevBacktester(
    prices_df=closes,
    initial_capital=10000,
    lookback_period=20,
    z_threshold=1.0,
    max_sector_allocation=0.30,
)
results = backtester.run()

# Results available in results.BacktestResults
print(f"Return: {results.total_return:.2f}%")
print(f"Drawdown: {results.max_drawdown:.2f}%")
```

### `sector_etfs.py`

Fetches historical sector ETF prices:

```python
from sector_etfs import fetch_sector_closes, SECTOR_ETFS

# Fetch prices
closes = fetch_sector_closes(range_="2y")  # Returns DataFrame

# Available sectors
print(SECTOR_ETFS)  # Dict of ticker -> sector name
```

## Strategy Comparison

Tested against buy-and-hold across 10 random 2-year periods (2021-2026):

| Metric | Mean Reversion | Buy-and-Hold |
|--------|---|---|
| Avg Return | 20.18% | 21.97% |
| Max Drawdown | -16.68% | -27.37% |
| Sharpe Ratio | 0.67 | 0.00 |
| Win Rate vs B&H | 5/10 periods | — |

**Key Insight:** Mean reversion provides superior downside protection (44% better drawdown) while staying competitive on returns (only -1.79% below B&H average).

## Sector Coverage

11 US sector ETFs tracked:

- VGT (Technology)
- VHT (Health Care)
- VFH (Financials)
- VDC (Consumer Staples)
- VCR (Consumer Discretionary)
- VDE (Energy)
- VNQ (Real Estate)
- VIS (Industrials)
- VOX (Communication Services)
- VAW (Materials)
- VPU (Utilities)

## Implementation Notes

- **Lookback Period:** 20 trading days for rolling mean/std
- **Z-Score Threshold:** 1.0 (approximately 68% confidence on normal distribution)
- **Rebalancing:** None (mean reversion signals only, no forced profit-taking)
- **Slippage/Commissions:** Not included (use real prices at close)
- **Capital Tracking:** No leverage, positions maxed at 30% each

## Testing Infrastructure

All backtests include:
- Daily portfolio snapshots
- Trade-by-trade logs
- Per-sector performance tracking
- Win rate and P&L calculations
- Maximum drawdown analysis
- Sharpe ratio calculation

## Customization

To modify strategy parameters, edit `backtest.py`:

```python
backtester = PortfolioStddevBacktester(
    prices_df=closes,
    initial_capital=10000,           # Change starting capital
    lookback_period=20,              # Change lookback (20-50 recommended)
    z_threshold=1.0,                 # Change signal threshold (0.5-2.0)
    max_sector_allocation=0.30,      # Change sector cap (0.20-0.50)
)
```

## Future Enhancements

Potential improvements:
- Stop-loss on positions beyond max drawdown
- Position sizing based on volatility
- Trend filtering (don't short in uptrends)
- Machine learning for z-score thresholds
- Real-time trading integration
