"""Paper figures from the combined summary.json.

Fig 1  proxy vs truth lineages, arms A–D (default tier, notes on)
Fig 2  paired per-seed differences on G_final with HL estimates and exact CIs
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from analysis.stats import hodges_lehmann  # noqa: E402
from optimizer.models import DEFAULT_TIER, STRONG_TIER  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BLUE, ORANGE, INK, MUTED, RULE = "#2036F5", "#D9771E", "#0f1a2e", "#6b7b8d", "#e2e5ea"
TITLES = {"A": "A  self-evaluation", "B": "B  visible gate", "C": "C  + hidden holdout", "D": "D  + behavioural envelope"}


def fig1(tr, out):
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.6), dpi=200, sharey=True)
    for ax, arm in zip(axes, "ABCD"):
        rows = [t for t in tr if t["arm"] == arm and t["model"] == DEFAULT_TIER and t["notes_enabled"]]
        n = min(len(t["P_lineage"]) for t in rows); xs = list(range(n))
        for key, col in (("P_lineage", BLUE), ("G_lineage", ORANGE)):
            for t in rows:
                ax.plot(xs, [100 * v for v in t[key][:n]], color=col, alpha=0.18, lw=0.9)
            mean = [100 * sum(t[key][i] for t in rows) / len(rows) for i in xs]
            ax.plot(xs, mean, color=col, lw=2.4)
            ax.annotate(f"{mean[-1]:.0f}", (xs[-1], mean[-1]), xytext=(4, 0), textcoords="offset points", va="center", fontsize=8.5, color=INK, fontweight="bold")
        ax.set_title(TITLES[arm], loc="left", fontsize=10.5, color=INK, fontweight="bold")
        ax.set_xlim(0, n + 1.6); ax.set_ylim(55, 102); ax.set_xticks([0, 10, 20])
        ax.set_xlabel("Revision", color=MUTED, fontsize=9); ax.tick_params(colors=MUTED, labelsize=8, length=0)
        for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
        for s_ in ("left", "bottom"): ax.spines[s_].set_color(RULE)
        ax.grid(axis="y", color=RULE, lw=0.5); ax.set_axisbelow(True)
    axes[0].set_ylabel("Accuracy (%)", color=MUTED, fontsize=9)
    axes[0].text(0.4, 97.5, "P  (visible, V)", color=BLUE, fontsize=8.5, fontweight="bold")
    axes[0].text(0.4, 61, "G  (hidden, balanced accuracy on H)", color=ORANGE, fontsize=8.5, fontweight="bold")
    fig.tight_layout(w_pad=1.6); fig.savefig(out, bbox_inches="tight", facecolor="white"); plt.close(fig)


def fig2(tr, out):
    def val(arm, model, notes, seed, attr="G_final"):
        for t in tr:
            if t["arm"] == arm and t["model"] == model and t["notes_enabled"] == notes and t["seed"] == seed:
                return t[attr]
    seeds = sorted({t["seed"] for t in tr})
    S, O = DEFAULT_TIER, STRONG_TIER
    contrasts = [
        ("A − B  (self vs visible)", [val("A", S, True, s) - val("B", S, True, s) for s in seeds]),
        ("C − B  (hidden holdout)", [val("C", S, True, s) - val("B", S, True, s) for s in seeds]),
        ("D − B  (envelope; exploratory)", [val("D", S, True, s) - val("B", S, True, s) for s in seeds]),
        ("Parametric − LLM, arm B", [val("B", "parametric", True, s) - val("B", S, True, s) for s in seeds]),
        ("Parametric − LLM, arm D", [val("D", "parametric", True, s) - val("D", S, True, s) for s in seeds]),
        ("Opus − Sonnet, arm B", [val("B", O, True, s) - val("B", S, True, s) for s in seeds]),
        ("Opus − Sonnet, arm D", [val("D", O, True, s) - val("D", S, True, s) for s in seeds]),
        ("Notes on − off, arm B", [val("B", S, True, s) - val("B", S, False, s) for s in seeds]),
        ("Notes on − off, arm D", [val("D", S, True, s) - val("D", S, False, s) for s in seeds]),
    ]
    fig, ax = plt.subplots(figsize=(8.5, 5.2), dpi=200)
    ys = list(range(len(contrasts)))[::-1]
    for y, (lab, d) in zip(ys, contrasts):
        hl = hodges_lehmann(d)
        ax.scatter([100 * x for x in d], [y] * len(d), s=18, color=MUTED, alpha=0.55, zorder=2)
        ax.plot([100 * hl["ci_low"], 100 * hl["ci_high"]], [y, y], color=INK, lw=2.2, zorder=3)
        ax.scatter([100 * hl["estimate"]], [y], s=60, color=ORANGE, edgecolor=INK, zorder=4)
        ax.text(14.5, y, f"{100*hl['estimate']:+.1f}  [{100*hl['ci_low']:+.1f}, {100*hl['ci_high']:+.1f}]", va="center", fontsize=8.5, color=INK)
    ax.axvline(0, color=RULE, lw=1); ax.set_yticks(ys); ax.set_yticklabels([c[0] for c in contrasts], fontsize=9, color=INK)
    ax.set_xlabel("Paired difference in final hidden ground truth G (percentage points)", fontsize=9, color=MUTED)
    ax.set_xlim(-13, 24); ax.set_xticks([-10, -5, 0, 5, 10])
    ax.text(14.5, max(ys) + 0.7, "HL estimate  [exact 95 % CI]", fontsize=8.5, color=MUTED)
    ax.set_ylim(-0.8, max(ys) + 1.2); ax.tick_params(colors=MUTED, labelsize=8, length=0)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    for s_ in ("left", "bottom"): ax.spines[s_].set_color(RULE)
    ax.grid(axis="x", color=RULE, lw=0.5); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(out, bbox_inches="tight", facecolor="white"); plt.close(fig)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", type=Path, default=ROOT / "analysis/out/confirm-01+confirm-01-opus+confirm-01-nonotes+baseline-01/summary.json")
    ap.add_argument("--outdir", type=Path, default=ROOT / "docs" / "paper")
    a = ap.parse_args(argv)
    a.outdir.mkdir(parents=True, exist_ok=True)
    tr = json.loads(a.summary.read_text())["trajectories"]
    fig1(tr, a.outdir / "fig1-lineages.png"); fig2(tr, a.outdir / "fig2-contrasts.png")
    print("wrote", a.outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
