"""Figures, if matplotlib is installed; otherwise a note is written instead.
Colours are fixed per arm so every figure reads the same way."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence

ARM_COLOURS = {"A": "#b3261e", "B": "#e07b00", "C": "#1f6feb", "D": "#1a7f37"}


def _mpl():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except Exception:  # noqa: BLE001
        return None


def lineage_curves(metrics: Sequence[object], out: Path, quantity: str = "G_lineage", title: str = "") -> Path:
    plt = _mpl()
    if plt is None:
        (out.with_suffix(".txt")).write_text("matplotlib not installed; figure skipped\n")
        return out.with_suffix(".txt")
    fig, ax = plt.subplots(figsize=(7, 4))
    for m in metrics:
        ys = getattr(m, quantity)
        ax.plot(range(len(ys)), ys, color=ARM_COLOURS.get(m.arm, "#666"), alpha=0.6, lw=1.2,
                label=f"arm {m.arm}" if m.seed == min(x.seed for x in metrics if x.arm == m.arm) else None)
    ax.set_xlabel("generation")
    ax.set_ylabel(quantity.replace("_lineage", "") + " of accepted lineage")
    ax.set_title(title or quantity)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def auroc_bars(table: Dict[str, Dict[str, object]], out: Path) -> Path:
    plt = _mpl()
    if plt is None:
        (out.with_suffix(".txt")).write_text("matplotlib not installed; figure skipped\n")
        return out.with_suffix(".txt")
    names = [k for k, v in table.items() if v.get("auroc") is not None]
    vals = [table[k]["auroc"] for k in names]
    lo = [table[k]["auroc"] - (table[k]["ci_low"] or table[k]["auroc"]) for k in names]
    hi = [(table[k]["ci_high"] or table[k]["auroc"]) - table[k]["auroc"] for k in names]
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.bar(names, vals, yerr=[lo, hi], color="#1f6feb", capsize=3)
    ax.axhline(0.5, color="#999", lw=0.8, ls="--")
    ax.axhline(0.7, color="#1a7f37", lw=0.8, ls=":")
    ax.set_ylim(0, 1)
    ax.set_ylabel("AUROC (G falls ≥ δ within 3 generations)")
    ax.spines[["top", "right"]].set_visible(False)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out
