"""Render docs/architecture.png (matplotlib) for the submission ZIP."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).resolve().parent / "architecture.png"

LAYERS = [
    ("Source layer", "PostgreSQL / MySQL  ·  7-table synthetic OLTP", "#1e3a5f"),
    ("Schema profiler", "SQLAlchemy reflection  ·  null rates, cardinality, FK graph, PII", "#134e4a"),
    ("LangGraph + LangChain", "profiler → mapper → HITL gate → rules → ETL → validator → docs", "#3b0764"),
    ("Human review gate", "confidence < 0.80  ·  approve / reject / override_note  ·  audit", "#7c2d12"),
    ("Validation", "Great Expectations ×3  ·  dbt tests  ·  reconciliation report", "#1e3a8a"),
    ("Observability", "LangFuse traces  ·  prompt_id  ·  immutable audit/migration_audit_log.json", "#365314"),
]


def main() -> None:
    fig, ax = plt.subplots(figsize=(12, 8), facecolor="#0a0e17")
    ax.set_facecolor("#0a0e17")
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 9)
    ax.axis("off")
    ax.set_title(
        "AI-Assisted Legacy Data Migration Platform",
        color="#e2e8f0",
        fontsize=16,
        pad=12,
        fontweight="bold",
    )
    ax.text(
        6,
        8.45,
        "FDE-CAPSTONE-DE-01  ·  LangGraph orchestration with human-in-the-loop confidence gating",
        ha="center",
        color="#94a3b8",
        fontsize=9,
    )
    y = 7.35
    for title, desc, color in LAYERS:
        box = FancyBboxPatch(
            (1.2, y - 0.55),
            9.6,
            1.05,
            boxstyle="round,pad=0.02,rounding_size=0.15",
            facecolor=color,
            edgecolor="#94a3b8",
            linewidth=0.8,
            alpha=0.92,
        )
        ax.add_patch(box)
        ax.text(6, y + 0.18, title, ha="center", va="center", color="white", fontsize=12, fontweight="bold")
        ax.text(6, y - 0.18, desc, ha="center", va="center", color="#e2e8f0", fontsize=8.5)
        if y > 1.5:
            ax.annotate(
                "",
                xy=(6, y - 0.62),
                xytext=(6, y - 0.92),
                arrowprops=dict(arrowstyle="->", color="#00d4aa", lw=1.4),
            )
        y -= 1.22
    ax.text(
        6,
        0.28,
        "Target: Snowflake / BigQuery  (local: Postgres or SQLite warehouse stand-in)",
        ha="center",
        color="#94a3b8",
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(OUT, dpi=140, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
