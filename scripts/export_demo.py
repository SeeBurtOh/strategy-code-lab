"""Rebuild the README's synthetic results and publication-resolution chart."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter
from strategy_lab import Strategy, REFERENCE_SOURCE, synthetic_bars, backtest

bars = synthetic_bars(seed=42)
start = int(len(bars) * 0.65)
strategy = backtest(bars, Strategy(REFERENCE_SOURCE), start=start)
baseline = backtest(bars, lambda closes: 1, start=start)
report = {
    "data": "Synthetic prices, seed=42; not market observations",
    "provenance": "Authored reference; no model called",
    "bars": len(bars),
    "holdout_start": str(bars.index[start].date()),
    "initial_cash": 10000,
    "allocation": 0.2,
    "fee_bps": 1,
    "slippage_bps": 5,
    "strategy": strategy[2],
    "buy_and_hold": baseline[2],
}
(ROOT / "assets/demo-results.json").write_text(json.dumps(report, indent=2) + "\n")
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "text.color": "#dfedf5",
        "axes.labelcolor": "#b9cbd7",
        "xtick.color": "#a1b7c6",
        "ytick.color": "#a1b7c6",
        "axes.edgecolor": "#284358",
        "axes.facecolor": "#0c2133",
        "figure.facecolor": "#071724",
    }
)
fig, axes = plt.subplots(
    2, 1, figsize=(12, 7.2), sharex=True, gridspec_kw={"height_ratios": [2, 1]}
)
fig.subplots_adjust(top=0.77, bottom=0.14, left=0.10, right=0.96, hspace=0.18)
fig.text(
    0.10, 0.93, "A reproducible test. An honest result.", fontsize=23, fontweight="bold"
)
fig.text(
    0.10,
    0.87,
    "SYNTHETIC HOLDOUT  /  112 BARS  /  $10,000 STARTING ACCOUNT",
    fontsize=10,
    color="#6edbd0",
)
fig.text(
    0.10,
    0.815,
    "Reference strategy  −0.78%     •     Buy and hold  +2.19%     •     Same 20% entry allocation",
    fontsize=11,
)
for label, result, color in [
    ("Reference strategy", strategy, "#42d6c4"),
    ("Buy and hold", baseline, "#87afff"),
]:
    equity = result[0].equity
    axes[0].plot(equity.index, equity, label=label, color=color, linewidth=2.2)
    dd = (equity / equity.cummax().clip(lower=10000) - 1) * 100
    axes[1].plot(dd.index, dd, color=color, linewidth=1.8)
axes[0].set_ylabel("Account value ($)")
axes[0].yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
axes[1].set_ylabel("Drawdown (%)")
axes[0].legend(loc="upper left", frameon=False, labelcolor="#dfedf5", ncol=2)
for ax in axes:
    ax.grid(alpha=0.12, color="#a1b7c6")
    ax.spines[["top", "right"]].set_visible(False)
fig.text(
    0.10,
    0.045,
    "Seed 42 · Next-open execution · 1 bp fees + 5 bps slippage · No real market data or API calls",
    fontsize=9,
    color="#a1b7c6",
)
fig.savefig(ROOT / "assets/backtest.png", dpi=250)
plt.close(fig)
print("Wrote assets/demo-results.json and assets/backtest.png (3000 × 1800).")
