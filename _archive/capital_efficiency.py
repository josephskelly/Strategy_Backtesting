"""
Analyze capital efficiency and cash allocation in StdDev trading strategy

Measures:
- Average cash utilization rate
- Percentage of time fully/partially/un-invested
- Opportunity cost of idle cash
- Comparison to leveraged strategies
"""

import pandas as pd
import numpy as np
from sector_etfs import fetch_sector_closes, SECTOR_ETFS
from stddev_backtest import StddevBacktester


class CapitalEfficiencyAnalyzer:
    """Analyze capital efficiency of backtested strategies."""

    def __init__(self, ticker: str, prices: pd.Series, initial_capital: float = 10000):
        """Initialize analyzer."""
        self.ticker = ticker
        self.prices = prices.dropna()
        self.initial_capital = initial_capital
        self.daily_cash = []
        self.daily_shares = []
        self.daily_invested_value = []

    def run_and_track(self, lookback_period: int = 20, z_threshold: float = 1.0):
        """Run backtest while tracking cash and share positions daily."""
        backtester = StddevBacktester(
            ticker=self.ticker,
            prices=self.prices,
            lookback_period=lookback_period,
            z_threshold=z_threshold,
            initial_capital=self.initial_capital,
        )

        # Manually run backtest to track daily state
        shares = 0.0
        cash = self.initial_capital

        rolling_mean = backtester.rolling_mean
        rolling_std = backtester.rolling_std

        for i, (date, price) in enumerate(self.prices.items()):
            mean = rolling_mean.iloc[i]
            std = rolling_std.iloc[i]

            if pd.isna(mean) or pd.isna(std) or std == 0:
                z_score = None
            else:
                z_score = (price - mean) / std

            # Generate signals
            if z_score is not None:
                if shares == 0 and z_score <= -z_threshold:
                    # BUY signal
                    abs_z = abs(z_score)
                    position_ratio = min(abs_z / z_threshold, 1.0)
                    position_value = self.initial_capital * position_ratio
                    if position_value > 0:
                        qty = position_value / price
                        shares += qty
                        cash -= position_value

                elif shares > 0 and z_score >= z_threshold:
                    # SELL signal
                    sale_value = shares * price
                    cash += sale_value
                    shares = 0

            # Track daily state
            invested_value = shares * price
            cash_value = cash
            total_portfolio = invested_value + cash_value

            self.daily_cash.append(cash_value)
            self.daily_shares.append(shares)
            self.daily_invested_value.append(invested_value)

        return self._compute_efficiency_metrics()

    def _compute_efficiency_metrics(self):
        """Compute capital efficiency metrics."""
        daily_cash = np.array(self.daily_cash)
        daily_invested = np.array(self.daily_invested_value)
        daily_total = daily_cash + daily_invested

        # Avoid division by zero
        cash_pct = np.divide(
            daily_cash,
            daily_total,
            where=daily_total != 0,
            out=np.zeros_like(daily_cash, dtype=float),
        )
        invested_pct = np.divide(
            daily_invested,
            daily_total,
            where=daily_total != 0,
            out=np.zeros_like(daily_invested, dtype=float),
        )

        # Days fully invested (>90%), partially (<90%), or idle
        fully_invested = np.sum(invested_pct >= 0.9)
        partially_invested = np.sum((invested_pct >= 0.1) & (invested_pct < 0.9))
        idle = np.sum(invested_pct < 0.1)
        total_days = len(invested_pct)

        return {
            "ticker": self.ticker,
            "avg_cash_pct": np.mean(cash_pct) * 100,
            "avg_invested_pct": np.mean(invested_pct) * 100,
            "max_cash_pct": np.max(cash_pct) * 100,
            "min_cash_pct": np.min(cash_pct) * 100,
            "fully_invested_days": fully_invested,
            "partially_invested_days": partially_invested,
            "idle_days": idle,
            "total_days": total_days,
            "fully_invested_pct": (fully_invested / total_days) * 100,
            "partially_invested_pct": (partially_invested / total_days) * 100,
            "idle_days_pct": (idle / total_days) * 100,
            "avg_daily_cash": np.mean(daily_cash),
            "avg_daily_invested": np.mean(daily_invested),
        }


def analyze_all_sectors(range_: str = "2y"):
    """Analyze capital efficiency across all sectors."""
    print(f"Fetching sector ETF prices for range={range_}...")
    closes = fetch_sector_closes(range_=range_)

    results = []
    for ticker in closes.columns:
        print(f"  Analyzing {ticker}...")
        analyzer = CapitalEfficiencyAnalyzer(ticker, closes[ticker])
        metrics = analyzer.run_and_track()
        results.append(metrics)

    return pd.DataFrame(results)


if __name__ == "__main__":
    print("=" * 90)
    print("Capital Efficiency Analysis: StdDev Trading Strategy")
    print("=" * 90)
    print()

    efficiency_df = analyze_all_sectors(range_="2y")

    # Save results
    output_file = "capital_efficiency.csv"
    efficiency_df.to_csv(output_file, index=False)
    print(f"\n✓ Results saved to {output_file}")

    # Display detailed results
    print("\n" + "=" * 90)
    print("CAPITAL EFFICIENCY BY SECTOR")
    print("=" * 90)
    print(
        efficiency_df[
            [
                "ticker",
                "avg_cash_pct",
                "avg_invested_pct",
                "fully_invested_pct",
                "idle_days_pct",
            ]
        ].to_string(index=False)
    )

    # Summary statistics
    print("\n" + "=" * 90)
    print("SUMMARY STATISTICS")
    print("=" * 90)

    avg_cash_pct = efficiency_df["avg_cash_pct"].mean()
    avg_invested_pct = efficiency_df["avg_invested_pct"].mean()
    avg_fully_invested = efficiency_df["fully_invested_pct"].mean()
    avg_idle = efficiency_df["idle_days_pct"].mean()

    print(f"\nAverage Across All Sectors:")
    print(f"  Average Cash Allocation:    {avg_cash_pct:>6.2f}%")
    print(f"  Average Invested Position:  {avg_invested_pct:>6.2f}%")
    print(f"  Fully Invested (>90%):      {avg_fully_invested:>6.2f}% of days")
    print(f"  Idle/Uninvested (<10%):     {avg_idle:>6.2f}% of days")

    # Best and worst efficiency
    best_efficiency = efficiency_df.loc[efficiency_df["avg_invested_pct"].idxmax()]
    worst_efficiency = efficiency_df.loc[efficiency_df["avg_invested_pct"].idxmin()]

    print(f"\nMost Efficient Capital Usage:")
    print(f"  Ticker:                     {best_efficiency['ticker']}")
    print(f"  Average Invested:           {best_efficiency['avg_invested_pct']:>6.2f}%")
    print(f"  Fully Invested Days:        {best_efficiency['fully_invested_pct']:>6.2f}%")

    print(f"\nLeast Efficient Capital Usage:")
    print(f"  Ticker:                     {worst_efficiency['ticker']}")
    print(f"  Average Invested:           {worst_efficiency['avg_invested_pct']:>6.2f}%")
    print(f"  Fully Invested Days:        {worst_efficiency['fully_invested_pct']:>6.2f}%")

    # Calculate opportunity cost (if idle cash earned risk-free rate)
    risk_free_rate = 0.045  # Current risk-free rate ~4.5%
    avg_idle_cash = efficiency_df["avg_daily_cash"].mean()
    annual_opportunity_cost = avg_idle_cash * risk_free_rate

    print(f"\n" + "=" * 90)
    print("OPPORTUNITY COST ANALYSIS")
    print("=" * 90)
    print(f"\nAssuming 4.5% annual risk-free rate:")
    print(f"  Average Idle Cash (per strategy):  ${avg_idle_cash:>10,.2f}")
    print(f"  Annual Opportunity Cost:           ${annual_opportunity_cost:>10,.2f}")
    print(f"  Over 2 years:                      ${annual_opportunity_cost * 2:>10,.2f}")

    # Capital efficiency score
    print(f"\n" + "=" * 90)
    print("CAPITAL EFFICIENCY RANKINGS")
    print("=" * 90)

    efficiency_ranked = efficiency_df[
        ["ticker", "avg_invested_pct", "fully_invested_pct", "avg_cash_pct"]
    ].copy()
    efficiency_ranked.columns = [
        "Ticker",
        "Avg Invested %",
        "Fully Invested Days %",
        "Avg Idle Cash %",
    ]
    efficiency_ranked = efficiency_ranked.sort_values("Avg Invested %", ascending=False).reset_index(drop=True)

    print(efficiency_ranked.to_string(index=False))

    # Analysis and recommendations
    print(f"\n" + "=" * 90)
    print("ANALYSIS & RECOMMENDATIONS")
    print("=" * 90)

    print(f"\n1. CAPITAL UTILIZATION:")
    if avg_invested_pct < 50:
        print(f"   ⚠️  Low utilization ({avg_invested_pct:.1f}%) - most capital sitting idle")
        print(f"   → Consider: Leverage, margin, or multiple positions")
    elif avg_invested_pct < 75:
        print(f"   ℹ️  Moderate utilization ({avg_invested_pct:.1f}%) - good balance of risk/cash")
        print(f"   → Consider: Slight position sizing increase")
    else:
        print(f"   ✓ High utilization ({avg_invested_pct:.1f}%) - capital well deployed")

    print(f"\n2. IDLE CASH PERCENTAGE:")
    if avg_idle > 50:
        print(f"   ⚠️  Very high ({avg_idle:.1f}% of time uninvested)")
        print(f"   → Strategy sits in cash between signals for extended periods")
    elif avg_idle > 25:
        print(f"   ℹ️  Moderate ({avg_idle:.1f}% of time uninvested)")
        print(f"   → Normal for mean reversion - waiting for extreme moves")
    else:
        print(f"   ✓ Low ({avg_idle:.1f}% of time uninvested)")
        print(f"   → Strategy frequently generates trading signals")

    print(f"\n3. OPPORTUNITY COST:")
    print(f"   ${annual_opportunity_cost:,.2f}/year in lost risk-free returns")
    if annual_opportunity_cost > 100:
        print(f"   → Significant - consider cash deployment strategies")
    else:
        print(f"   → Acceptable cost for mean reversion discipline")

    print()
