"""Draw the README figures from saved dev reports. Needs matplotlib, which the project doesn't."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, PathPatch, Rectangle  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402

from compare_reports import summarise  # noqa: E402
from reqtrace.documents import ROOT, load_change_request  # noqa: E402
from reqtrace.evaluation import load_cases  # noqa: E402
from reqtrace.screening import screen_sections  # noqa: E402
from run_agent_eval import ATTACKS, inject  # noqa: E402

RESULTS = ROOT / "eval" / "results"
OUTPUT = ROOT / "docs" / "images"
DEV_DOCUMENTS = ("CR-101", "CR-102", "CR-103")
THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "primary": "#0b0b0b",
        "secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "series": ("#2a78d6", "#eb6834"),
        "box": "#f0efec",
    },
    "dark": {
        "surface": "#1a1a19",
        "primary": "#f0efec",
        "secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "series": ("#3987e5", "#d95926"),
        "box": "#2c2c2a",
    },
}
plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]
BAR_INCHES = 0.2
GAP_INCHES = 0.02
CORNER_INCHES = 0.04


def load_report(path: str) -> dict:
    return json.loads((RESULTS / path).read_text(encoding="utf-8"))


def rows(report: dict) -> dict[str, dict]:
    return {row["case_id"]: row for review in report["reviews"] for row in review["details"]}


def verdicts_changed(report: dict, clean: dict) -> int:
    baseline = rows(clean)
    return sum(
        row["raw_verdict"] != baseline[case_id]["raw_verdict"]
        or row["checked_verdict"] != baseline[case_id]["checked_verdict"]
        for case_id, row in rows(report).items()
    )


def citation_data() -> dict:
    cases = {case["case_id"]: case for case in load_cases("dev")}
    before = summarise(load_report("baseline/semantic_dev.json"), cases)
    after = summarise(load_report("schema/semantic_dev.json"), cases)
    labels = {
        "Accuracy after citation checks": "Accuracy after check",
        "Quotes found in the cited section": "Quotes found in the cited section",
        "Expected facts covered by citations": "Gold facts covered",
    }
    return {
        "categories": list(labels),
        "series": {
            "Before schema constraints": [before[key] for key in labels.values()],
            "After schema constraints": [after[key] for key in labels.values()],
        },
    }


def screen_passes_attack(attack: str) -> bool:
    """True if screening restores every dev document to its clean text."""
    return all(
        screen_sections(inject(load_change_request(document), attack))[0] == load_change_request(document)
        for document in DEV_DOCUMENTS
    )


def injection_data() -> dict:
    clean = load_report("agent/workflow_dev.json")
    names = {
        "system_override": "Direct instruction naming a tool",
        "addressed_note": "Note addressed to the AI reviewer",
        "obfuscated": "Instruction with altered spelling",
        "false_claim": "False compliance claim in plain prose",
    }
    assert set(names) == set(ATTACKS)
    without, with_screen = [], []
    for attack in names:
        changed = verdicts_changed(load_report(f"agent/attack_{attack}_unscreened.json"), clean)
        without.append(changed)
        if attack == "system_override":
            with_screen.append(verdicts_changed(load_report(f"agent/attack_{attack}_screened.json"), clean))
        else:
            with_screen.append(0 if screen_passes_attack(attack) else changed)
    return {
        "categories": list(names.values()),
        "series": {"Without the screen": without, "With the screen": with_screen},
    }


def draw_bar(ax, y_center, value, height, color, corner_x, corner_y):
    """Draw a horizontal bar, square at the baseline with a rounded tip."""
    if value <= 0:
        return
    top, bottom = y_center - height / 2, y_center + height / 2
    corner_x = min(corner_x, value)
    vertices = [
        (0, top),
        (value - corner_x, top),
        (value, top),
        (value, top + corner_y),
        (value, bottom - corner_y),
        (value, bottom),
        (value - corner_x, bottom),
        (0, bottom),
        (0, top),
    ]
    codes = [
        MplPath.MOVETO,
        MplPath.LINETO,
        MplPath.CURVE3,
        MplPath.CURVE3,
        MplPath.LINETO,
        MplPath.CURVE3,
        MplPath.CURVE3,
        MplPath.LINETO,
        MplPath.CLOSEPOLY,
    ]
    ax.add_patch(PathPatch(MplPath(vertices, codes), facecolor=color, edgecolor="none", zorder=3))


def grouped_bars(data, title, subtitle, note, x_max, ticks, formatter, name, mode):
    theme = THEMES[mode]
    categories, series = data["categories"], data["series"]
    fig = plt.figure(figsize=(8, 1.55 + 0.72 * len(categories) + (0.25 if note else 0)), facecolor=theme["surface"])
    fig_w, fig_h = fig.get_size_inches()
    plot_top = fig_h - 1.2
    plot_bottom = 0.42 + (0.28 if note else 0)
    ax = fig.add_axes(
        [3.0 / fig_w, plot_bottom / fig_h, (fig_w - 3.6) / fig_w, (plot_top - plot_bottom) / fig_h],
        facecolor=theme["surface"],
    )
    plot_h = plot_top - plot_bottom
    plot_w = fig_w - 3.6
    ax.set_xlim(0, x_max)
    ax.set_ylim(len(categories) - 0.5, -0.5)
    unit_y = len(categories) / plot_h
    unit_x = x_max / plot_w
    height = BAR_INCHES * unit_y
    gap = GAP_INCHES * unit_y
    for category_index in range(len(categories)):
        for series_index, (label, values) in enumerate(series.items()):
            value = values[category_index]
            offset = (series_index - 0.5) * (height + gap)
            draw_bar(
                ax,
                category_index + offset,
                value,
                height,
                theme["series"][series_index],
                CORNER_INCHES * unit_x,
                CORNER_INCHES * unit_y,
            )
            ax.text(
                value + 0.07 * unit_x,
                category_index + offset,
                formatter(value),
                va="center",
                ha="left",
                fontsize=9.5,
                color=theme["primary"],
                zorder=4,
            )
    ax.set_yticks(range(len(categories)))
    ax.set_yticklabels(
        [textwrap.fill(category, 34) for category in categories], fontsize=10.5, color=theme["primary"]
    )
    ax.set_xticks(ticks)
    ax.set_xticklabels([formatter(tick) for tick in ticks], fontsize=9, color=theme["muted"])
    ax.tick_params(axis="both", length=0, pad=6)
    ax.grid(axis="x", color=theme["grid"], linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(theme["axis"])
    ax.spines["left"].set_linewidth(1)
    fig.text(0.3 / fig_w, (fig_h - 0.36) / fig_h, title, fontsize=14, fontweight="semibold", color=theme["primary"])
    fig.text(0.3 / fig_w, (fig_h - 0.62) / fig_h, subtitle, fontsize=10, color=theme["secondary"])
    handles = [
        Line2D([], [], marker="s", linestyle="none", markersize=9, color=theme["series"][index], label=label)
        for index, label in enumerate(series)
    ]
    legend = fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.22 / fig_w, (fig_h - 0.7) / fig_h),
        ncol=2,
        frameon=False,
        fontsize=10,
        handletextpad=0.2,
        columnspacing=1.4,
    )
    for text in legend.get_texts():
        text.set_color(theme["secondary"])
    if note:
        fig.text(0.3 / fig_w, 0.14 / fig_h, note, fontsize=8.5, color=theme["muted"])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT / f"{name}_{mode}.png", dpi=200, facecolor=theme["surface"])
    plt.close(fig)


def draw_terminal():
    """Render a saved review transcript. This is a rendering, not a screen capture."""
    lines = []
    for line in (OUTPUT / "terminal_review_cr103.txt").read_text(encoding="utf-8").splitlines():
        indent = len(line) - len(line.lstrip())
        wrapped = textwrap.wrap(
            line,
            92,
            initial_indent=" " * indent,
            subsequent_indent=" " * (indent + 2),
            break_on_hyphens=False,
        )
        lines += wrapped or [""]
    line_height = 0.2
    fig = plt.figure(figsize=(8.6, 0.85 + line_height * len(lines)), facecolor="#1a1a19")
    fig_w, fig_h = fig.get_size_inches()
    fig.add_artist(Rectangle((0, (fig_h - 0.36) / fig_h), 1, 0.36 / fig_h, transform=fig.transFigure, color="#2c2c2a"))
    fig.text(0.3 / fig_w, (fig_h - 0.24) / fig_h, "reqtrace-agent: terminal review", color="#c3c2b7", fontsize=9.5)
    in_citation = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        color = "#f0efec"
        weight = "normal"
        if stripped.startswith("[verified]"):
            in_citation = True
        elif not line.startswith("    "):
            in_citation = False
        if in_citation:
            color = "#c3c2b7"
        elif stripped.startswith(("Type approve", "Your name")):
            color = "#6da7ec"
        elif ":" in stripped and stripped.split(":")[0] in {"CHG-1", "CHG-2", "CHG-3", "CHG-4", "DAT-1", "SEC-1", "SEC-2", "BCK-1"}:
            weight = "bold"
        fig.text(
            0.3 / fig_w,
            (fig_h - 0.62 - line_height * index) / fig_h,
            line,
            family=["Consolas", "DejaVu Sans Mono"],
            fontsize=10,
            color=color,
            fontweight=weight,
            va="baseline",
        )
    fig.savefig(OUTPUT / "terminal_review.png", dpi=200, facecolor="#1a1a19")
    plt.close(fig)


def draw_workflow():
    theme = THEMES["light"]
    fig = plt.figure(figsize=(12, 5.1), facecolor=theme["surface"])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 5.1)
    ax.axis("off")
    ax.text(0.4, 4.65, "reqtrace-agent review workflow", fontsize=17, fontweight="semibold", color=theme["primary"])
    box_w, box_h = 1.92, 0.95

    def box(x, y, text, human=False):
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                box_w,
                box_h,
                boxstyle="round,pad=0,rounding_size=0.08",
                facecolor=theme["series"][0] if human else theme["box"],
                edgecolor="none",
            )
        )
        ax.text(
            x + box_w / 2,
            y + box_h / 2,
            text,
            ha="center",
            va="center",
            fontsize=10.5,
            color="#ffffff" if human else theme["primary"],
        )

    def arrow(start, end, connection="arc3", label=None, label_at=None):
        ax.add_patch(
            FancyArrowPatch(
                start,
                end,
                arrowstyle="-|>",
                mutation_scale=13,
                linewidth=1.3,
                color=theme["secondary"],
                connectionstyle=connection,
                shrinkA=0,
                shrinkB=0,
            )
        )
        if label:
            ax.text(*label_at, label, fontsize=9.5, color=theme["secondary"], ha="center", va="center")

    top = 3.3
    xs = [0.4 + index * 2.3 for index in range(5)]
    labels = [
        "Change request\nand policy rule",
        "Screen for text\naddressed to an AI",
        "Retrieve the top 3\nsections (RAG)",
        "LLM returns a verdict\nand citations",
        "Code checks each\nquote against source",
    ]
    for x, label in zip(xs, labels):
        box(x, top, label)
    for x in xs[:-1]:
        arrow((x + box_w, top + box_h / 2), (x + 2.3, top + box_h / 2))

    bottom = 1.25
    box(xs[4], bottom, "Failed check:\ndowngrade verdict")
    box(xs[3], bottom, "Draft finding and\nfollow-up question")
    box(xs[2], bottom, "Named person\ndecides", human=True)
    arrow((xs[4] + box_w / 2, top), (xs[4] + box_w / 2, bottom + box_h))
    arrow((xs[4], bottom + box_h / 2), (xs[3] + box_w, bottom + box_h / 2))
    arrow(
        (xs[4] + 0.2, top),
        (xs[3] + box_w - 0.25, bottom + box_h),
        label="Verified",
        label_at=(xs[3] + box_w - 0.4, 2.75),
    )
    arrow((xs[3], bottom + box_h / 2), (xs[2] + box_w, bottom + box_h / 2))
    result_h = 0.62
    for y, text in ((bottom + 0.62, "Approved: export report"), (bottom - 0.29, "Rejected: nothing exported")):
        ax.add_patch(
            FancyBboxPatch(
                (xs[0], y),
                3.0,
                result_h,
                boxstyle="round,pad=0,rounding_size=0.08",
                facecolor=theme["box"],
                edgecolor="none",
            )
        )
        ax.text(xs[0] + 1.5, y + result_h / 2, text, ha="center", va="center", fontsize=10.5, color=theme["primary"])
        arrow((xs[2], bottom + box_h / 2), (xs[0] + 3.0, y + result_h / 2))
    ax.add_patch(Rectangle((0.4, 0.32), 11.12, 0.015, facecolor=theme["axis"], edgecolor="none"))
    ax.text(
        0.4,
        0.11,
        "Every tool call, refusal, and decision is recorded in a hash-chained audit log. The model has no tool for recording a decision.",
        fontsize=10,
        color=theme["secondary"],
    )
    fig.savefig(OUTPUT / "workflow.png", dpi=200, facecolor=theme["surface"])
    plt.close(fig)


def main() -> int:
    citations = citation_data()
    attacks = injection_data()
    print(json.dumps({"citations": citations, "attacks": attacks}, indent=2))
    for mode in THEMES:
        grouped_bars(
            citations,
            "Schema constraints made the citations usable",
            "Share of 24 synthetic dev cases or expected items, semantic experiment, qwen2.5:7b",
            None,
            1.0,
            [0, 0.25, 0.5, 0.75, 1.0],
            lambda value: f"{value:.2f}",
            "citation_results",
            mode,
        )
        grouped_bars(
            attacks,
            "The screen stopped direct attacks, but not disguised ones",
            "Verdicts changed out of 24 by one attack in each dev document, compared with a clean run",
            "Only the first with-screen value was run on the model. The others follow from comparing screened inputs.",
            8,
            [0, 2, 4, 6, 8],
            lambda value: f"{value:d}",
            "injection_results",
            mode,
        )
    draw_terminal()
    draw_workflow()
    return 0


if __name__ == "__main__":
    sys.exit(main())
