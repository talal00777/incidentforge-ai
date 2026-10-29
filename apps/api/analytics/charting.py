"""Bounded, deterministic rendering of incident-level aggregate charts."""

from collections import Counter
from io import BytesIO
from math import ceil
from textwrap import fill

import seaborn as sns
from matplotlib import rc_context
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from analytics.engine import EventFact

CHART_TYPES = ("volume", "severity", "fingerprints", "service-errors")
MAX_CHART_POINTS = 96
MAX_LABELS = 10
ERROR_LEVELS = frozenset({"ERROR", "FATAL", "CRITICAL"})


def chart_series(kind: str, analysis: dict, events: list[EventFact]) -> dict:
    """Build an ordered, tabular dataset from the canonical analysis snapshot."""
    if kind not in CHART_TYPES:
        raise ValueError("Unsupported chart")

    if kind == "volume":
        timeline = analysis["timeline"]
        stride = max(1, ceil(len(timeline) / MAX_CHART_POINTS))
        rows = []
        for start in range(0, len(timeline), stride):
            window = timeline[start : start + stride]
            rows.append(
                {
                    "label": window[0]["start"],
                    "end": window[-1]["start"],
                    "total": sum(item["total"] for item in window),
                    "errors": sum(item["errors"] for item in window),
                }
            )
        note = (
            f"Up to {stride} populated {analysis['bucket_minutes']}-minute buckets per bar; "
            "unpopulated intervals are not shown."
            if stride > 1
            else (
                f"Populated {analysis['bucket_minutes']}-minute UTC buckets only; "
                "gaps are not filled."
            )
        )
        return {"rows": rows, "note": note}

    if kind == "severity":
        ranking = sorted(
            analysis["severity_counts"],
            key=lambda item: (-item["count"], item["severity"]),
        )
        rows = [
            {"label": item["severity"], "total": item["count"]} for item in ranking[:MAX_LABELS]
        ]
        if len(ranking) > MAX_LABELS:
            rows.append(
                {"label": "Other", "total": sum(item["count"] for item in ranking[MAX_LABELS:])}
            )
        return {
            "rows": rows,
            "note": "Counts are log events, not request failure rates; remaining levels are Other.",
        }

    if kind == "fingerprints":
        return {
            "rows": [
                {"label": item["fingerprint"][:12], "total": item["count"]}
                for item in analysis["fingerprint_groups"][:MAX_LABELS]
            ],
            "note": "Top normalized fingerprint hashes; labels are truncated for display.",
        }

    failures = Counter(
        (event.service or "unknown") for event in events if event.severity.upper() in ERROR_LEVELS
    )
    ranked = sorted(failures.items(), key=lambda item: (-item[1], item[0]))[:MAX_LABELS]
    return {
        "rows": [{"label": service, "total": count} for service, count in ranked],
        "note": "Error-level log event counts by service; no request denominator is available.",
    }


def chart_caption(kind: str, analysis: dict, series: dict) -> str:
    """Describe chart coverage, known missingness and any rendering reduction."""
    timeline = analysis["timeline"]
    if timeline:
        span = f"{timeline[0]['start']} to {timeline[-1]['start']} UTC"
    else:
        span = "no timestamped events"
    return (
        f"{kind}; window: {span}; {analysis['missing_event_time']} events lack "
        f"occurrence times; {series['note']}"
    )


def render_png(kind: str, analysis: dict, events: list[EventFact]) -> bytes:
    """Render a private PNG response without writing evidence or images to disk."""
    series = chart_series(kind, analysis, events)
    rows = series["rows"]
    palette = sns.color_palette("deep", 2)
    with rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "figure.dpi": 100,
            "savefig.dpi": 100,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    ):
        fig = Figure(figsize=(9.6, 5.6), dpi=100)
        FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)
        fig.subplots_adjust(
            left=0.16, right=0.98, top=0.88, bottom=0.35 if kind == "volume" else 0.19
        )
        try:
            if rows:
                positions = list(range(len(rows)))
                if kind == "volume":
                    ax.bar(
                        positions,
                        [row["total"] for row in rows],
                        color=palette[0],
                        label="All events",
                    )
                    ax.bar(
                        positions,
                        [row["errors"] for row in rows],
                        color=palette[1],
                        label="Error-level",
                    )
                    ax.legend(loc="upper right")
                else:
                    ax.barh(positions, [row["total"] for row in rows], color=palette[0])
                    ax.invert_yaxis()
                if kind == "volume":
                    width = len(rows)
                    chosen = sorted({0, width - 1, *range(0, width, max(1, ceil(width / 8)))})
                    ax.set_xticks(
                        chosen,
                        [rows[index]["label"][5:16] for index in chosen],
                        rotation=30,
                        ha="right",
                    )
                else:
                    ax.set_yticks(positions, [str(row["label"])[:48] for row in rows])
            else:
                ax.text(
                    0.5,
                    0.5,
                    "No matching events",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                )
                ax.set_xticks([])
                ax.set_yticks([])
            ax.set_title(
                {
                    "volume": "Event volume by UTC time bucket",
                    "severity": "Log events by severity",
                    "fingerprints": "Top normalized fingerprint clusters",
                    "service-errors": "Error-level events by service",
                }[kind]
            )
            ax.set_ylabel("Events" if kind == "volume" else "")
            ax.set_xlabel("Time (UTC)" if kind == "volume" else "Log events")
            fig.text(
                0.05,
                0.035,
                fill(chart_caption(kind, analysis, series), 105),
                ha="left",
                va="bottom",
                fontsize=7,
            )
            output = BytesIO()
            fig.savefig(output, format="png", metadata={"Software": "IncidentForge"}, dpi=100)
            return output.getvalue()
        finally:
            fig.clear()
