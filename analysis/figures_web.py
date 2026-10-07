"""Web figure: proxy vs truth over 20 revisions, arms B and D (default tier, notes on).

    python3 -m analysis.figures_web [--summary analysis/out/<run>/summary.json] [--out findings-dynamics.png]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from optimizer.models import DEFAULT_TIER  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BLUE, ORANGE, INK, MUTED, RULE = "#2036F5", "#D9771E", "#0f1a2e", "#6b7b8d", "#e2e5ea"
TITLES = {"B": "Gatekeeper B — visible score only", "D": "Gatekeeper D — + behaviour check"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", type=Path,
                    default=ROOT / "analysis/out/confirm-01+confirm-01-opus+confirm-01-nonotes+baseline-01/summary.json")
    ap.add_argument("--out", type=Path, default=ROOT / "findings-dynamics.png")
    a = ap.parse_args(argv)
    tr = json.loads(a.summary.read_text())["trajectories"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), dpi=200, sharey=True)
    fig.patch.set_facecolor("white")
    for ax, arm in zip(axes, "BD"):
        rows = [t for t in tr if t["arm"] == arm and t["model"] == DEFAULT_TIER and t["notes_enabled"]]
        n = min(len(t["P_lineage"]) for t in rows)
        xs = list(range(n))
        for key, col in (("P_lineage", BLUE), ("G_lineage", ORANGE)):
            for t in rows:
                ax.plot(xs, [100 * v for v in t[key][:n]], color=col, alpha=0.18, lw=1)
            mean = [100 * sum(t[key][i] for t in rows) / len(rows) for i in xs]
            ax.plot(xs, mean, color=col, lw=2.6, solid_capstyle="round")
            ax.annotate(f"{mean[-1]:.0f}%", (xs[-1], mean[-1]), xytext=(6, 0), textcoords="offset points",
                        va="center", fontsize=10, color=INK, fontweight="bold")
        ax.set_title(TITLES[arm], loc="left", fontsize=12, color=INK, fontweight="bold", pad=10)
        ax.set_xlim(0, n - 1 + 2.2)
        ax.set_ylim(50, 102)
        ax.set_xticks([0, 5, 10, 15, 20])
        ax.set_xlabel("Revision", color=MUTED, fontsize=10)
        ax.tick_params(colors=MUTED, labelsize=9, length=0)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(RULE)
        ax.grid(axis="y", color=RULE, lw=0.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Accuracy (%)", color=MUTED, fontsize=10)
    axes[0].text(0.3, 97, "Score the AI could see", color=BLUE, fontsize=10, fontweight="bold")
    axes[0].text(0.3, 59, "Real accuracy (hidden from the AI)", color=ORANGE, fontsize=10, fontweight="bold")
    fig.text(0.01, -0.02, "Claude Sonnet 5, 10 runs per gatekeeper (faint lines) and their average (bold). "
             "Real accuracy = balanced accuracy on 2,000 hidden frames. Revision 0 is the shared starting program.",
             fontsize=8.5, color=MUTED)
    fig.tight_layout(w_pad=2.5)
    fig.savefig(a.out, bbox_inches="tight", facecolor="white")
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
