"""Deterministic, bounded JSON and PDF exports of finalized postmortem content.

This module does not query the database or accept mutable review state. Callers must
verify the stored content checksum and authorize the incident before invoking it.
"""

import io
import os
import tempfile
from collections import Counter
from datetime import UTC
from html import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
)

from investigations.postmortem_content import canonical_bytes

EXPORT_SCHEMA_VERSION = "1.0"
PDF_RENDERER_VERSION = "1.0"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 6 * 1024 * 1024
MAX_PDF_PAGES = 80

NAVY = colors.HexColor("#19323D")
TEAL = colors.HexColor("#19747B")
MUTED = colors.HexColor("#596C74")
BORDER = colors.HexColor("#DCE5E7")


class PostmortemExportError(Exception):
    """Safe, typed export failure with no underlying user content in the message."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def export_envelope(*, version, verified_content: dict) -> dict:
    """Add fixed version metadata to the original, checksum-verified content."""
    if verified_content.get("incident", {}).get("id") != str(version.incident_id):
        raise PostmortemExportError("report_integrity", "The saved report is inconsistent.")
    return {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "postmortem_version": {
            "id": str(version.id),
            "incident_id": str(version.incident_id),
            "number": version.version,
            "created_at": version.created_at.isoformat(),
            "content_sha256": version.content_sha256,
        },
        "content": verified_content,
    }


def render_json(envelope: dict) -> bytes:
    """Re-downloads of the same frozen report produce identical JSON bytes."""
    try:
        data = canonical_bytes(envelope) + b"\n"
    except (TypeError, ValueError, OverflowError) as exc:
        raise PostmortemExportError("export_invalid", "This report cannot be exported.") from exc
    if len(data) > MAX_JSON_BYTES:
        raise PostmortemExportError("export_too_large", "This report exceeds the export limit.")
    return data


def _text(value: object) -> str:
    if value is None:
        return "Not recorded"
    return str(value)


def _markup(value: object) -> str:
    """Escape untrusted AI/human text before it reaches ReportLab's markup parser."""
    raw = _text(value)
    return escape(raw, quote=True).replace("\n", "<br/>")


def _time(value: object) -> str:
    if not value:
        return "Time unknown"
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return str(value) + " (timezone unrecorded)"
        return parsed.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, OverflowError, TypeError):
        return "Time unknown"


def _styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName="Helvetica", textColor=NAVY, spaceAfter=5)
    return {
        "title": ParagraphStyle(
            "IFTitle",
            fontSize=20,
            leading=24,
            fontName="Helvetica-Bold",
            spaceAfter=8,
            textColor=NAVY,
        ),
        "subtitle": ParagraphStyle(
            "IFSubtitle", fontSize=9, leading=13, textColor=MUTED, spaceAfter=14
        ),
        "h2": ParagraphStyle(
            "IFHeading",
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=NAVY,
            spaceBefore=13,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "IFSubheading",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=NAVY,
            spaceBefore=9,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "body": ParagraphStyle("IFBody", fontSize=9, leading=13, **base),
        "small": ParagraphStyle(
            "IFSmall", fontSize=7.6, leading=10.5, textColor=MUTED, spaceAfter=5
        ),
        "label": ParagraphStyle("IFLabel", fontSize=8, leading=11, textColor=TEAL, spaceAfter=4),
        "foot": ParagraphStyle("IFFooter", fontSize=8, leading=10, textAlign=TA_CENTER),
    }


def _service_chart(timeline: list[dict]) -> io.BytesIO | None:
    """A reproducible, source-bounded chart of selected evidence, not all incident events."""
    counts = Counter(item.get("service") or "Unspecified" for item in timeline)
    if not counts:
        return None
    # A backend-only Agg renderer; native interactive web charts remain separate.
    if not os.environ.get("MPLCONFIGDIR"):
        os.environ["MPLCONFIGDIR"] = tempfile.mkdtemp(prefix="incidentforge-matplotlib-")
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    top = sorted(counts.items(), key=lambda value: (-value[1], value[0]))[:7]
    names = [name[:38] for name, _ in reversed(top)]
    values = [count for _, count in reversed(top)]
    figure = Figure(figsize=(7.2, max(2.1, 0.46 * len(top) + 0.9)), dpi=110)
    FigureCanvasAgg(figure)
    axes = figure.add_axes((0.24, 0.31, 0.71, 0.62))
    axes.barh(names, values, color="#19747B", height=0.62)
    axes.set_xlabel("Selected events", fontsize=9, labelpad=6)
    axes.tick_params(axis="both", labelsize=8, length=0)
    axes.spines[["top", "right", "left"]].set_visible(False)
    axes.grid(axis="x", alpha=0.18)
    axes.set_axisbelow(True)
    axes.set_xlim(0, max(values) + 1)
    if max(values) <= 8:
        axes.set_xticks(range(max(values) + 2))
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=110, metadata={"Software": "IncidentForge AI"})
    figure.clear()
    buffer.seek(0)
    return buffer


def _safe_list(value: object) -> list:
    return value if isinstance(value, list) else []


def render_pdf(envelope: dict) -> bytes:
    """Render a printable PDF from immutable data with version-pinned metadata."""
    raw_json = render_json(envelope)
    if len(raw_json) > MAX_JSON_BYTES:
        raise PostmortemExportError("export_too_large", "This report exceeds the export limit.")
    content = envelope["content"]
    metadata = envelope["postmortem_version"]
    findings = content["ai"]["findings"]
    human = content["human"]
    timeline = _safe_list(content.get("timeline"))
    sources = _safe_list(content.get("evidence_manifest"))
    styles = _styles()
    elements = []

    def paragraph(value: object, style: str = "body") -> None:
        elements.append(Paragraph(_markup(value), styles[style]))

    def rich(label: str, value: object) -> None:
        elements.append(Paragraph(f"<b>{_markup(label)}:</b> {_markup(value)}", styles["body"]))

    def section(title: str, label: str | None = None) -> None:
        elements.append(Paragraph(_markup(title), styles["h2"]))
        if label:
            paragraph(label, "label")

    def references(ids: object) -> None:
        values = _safe_list(ids)
        if values:
            rich("Evidence IDs", ", ".join(_text(value) for value in values))

    paragraph("Incident postmortem", "title")
    paragraph(
        f"Version {metadata['number']}  |  Finalized {_time(metadata['created_at'])}  |  "
        f"Review revision {human['revision']}",
        "subtitle",
    )
    paragraph(content["incident"]["title"], "h2")
    elements.append(HRFlowable(width="100%", thickness=0.7, color=BORDER, spaceAfter=10))

    section("Incident summary", "AI-generated")
    paragraph(findings.get("incident_summary", "Not recorded"))

    section("Human assessment", "Human-authored")
    rich("Impact", human.get("impact_notes") or "Not recorded")
    rich("Remediation", human.get("remediation_notes") or "Not recorded")

    section("Evidence overview", "Selected, source-linked evidence")
    paragraph(
        f"{len(timeline)} selected evidence events. The chart below counts selected events "
        "only; it does not represent all incident logs or an error rate.",
        "small",
    )
    chart = _service_chart(timeline)
    if chart is not None:
        elements.append(
            Image(
                chart,
                width=166 * mm,
                height=min(
                    82,
                    48
                    + 7
                    * min(len(set(item.get("service") or "Unspecified" for item in timeline)), 7),
                )
                * mm,
                kind="proportional",
            )
        )
    section("Event timeline", "Recorded evidence")
    for index, item in enumerate(timeline, 1):
        rich(
            f"{index}. {_time(item.get('occurred_at'))}",
            f"{item.get('service') or 'Unknown service'}  |  {item.get('severity') or 'Unknown severity'}",
        )
        references([item.get("event_id")])

    section("Observed facts", "AI-generated; cited events are listed below each statement")
    facts = _safe_list(findings.get("observed_facts"))
    if not facts:
        paragraph("No facts recorded.")
    for index, fact in enumerate(facts, 1):
        rich(f"{index}", fact.get("statement", ""))
        references(fact.get("event_ids"))

    section("Hypotheses and human decisions", "AI-generated analysis with separate human review")
    decisions = {
        item.get("index"): item
        for item in _safe_list(human.get("hypotheses"))
        if isinstance(item, dict)
    }
    hypotheses = _safe_list(findings.get("hypotheses"))
    if not hypotheses:
        paragraph("No hypotheses recorded.")
    for index, hypothesis in enumerate(hypotheses):
        elements.append(
            Paragraph(f"{index + 1}. {_markup(hypothesis.get('title', 'Untitled'))}", styles["h3"])
        )
        rich("AI assessment", _text(hypothesis.get("status", "unknown")).replace("_", " "))
        decision = decisions.get(index, {})
        rich("Human decision", _text(decision.get("decision", "Not recorded")).replace("_", " "))
        if decision.get("note"):
            rich("Reviewer note", decision["note"])
        references(hypothesis.get("supporting_event_ids"))
        if hypothesis.get("contradicting_event_ids"):
            rich("Contradicting evidence", ", ".join(hypothesis["contradicting_event_ids"]))
        for alternative in _safe_list(hypothesis.get("alternative_explanations")):
            rich("Alternative", alternative)
        for check in _safe_list(hypothesis.get("further_checks")):
            rich("Further check", check)

    section("Suggested checks", "AI-generated; human verification required")
    actions = _safe_list(findings.get("suggested_actions"))
    if not actions:
        paragraph("None recorded.")
    for index, action in enumerate(actions, 1):
        rich(str(index), action.get("action", ""))
        references(action.get("rationale_event_ids"))

    section("Limitations", "AI-generated")
    limitations = _safe_list(findings.get("limitations"))
    if not limitations:
        paragraph("None recorded.")
    for item in limitations:
        paragraph(f"- {_text(item)}")

    section("Source provenance", "Frozen at finalization; source messages are not repeated")
    for item in sources:
        lines = item.get("source_lines") or []
        label = f"{item.get('source_name') or 'Unknown source'}"
        if len(lines) == 2:
            label += f"  |  lines {lines[0]}-{lines[1]}"
        rich(label, f"Event {item.get('event_id', '')}; Source {item.get('source_id', '')}")
        if item.get("source_sha256"):
            rich("Source SHA-256", item["source_sha256"])

    section("Version and AI provenance", "Immutable report metadata")
    rich("Report ID", metadata["id"])
    rich("Report version", metadata["number"])
    rich("PDF renderer version", PDF_RENDERER_VERSION)
    rich("Snapshot SHA-256", metadata["content_sha256"])
    rich("AI provider / model", f"{content['ai']['provider']} / {content['ai']['model_id']}")
    rich("Prompt", f"{content['ai']['prompt_profile']} / {content['ai']['prompt_version']}")
    rich("Response schema", content["ai"].get("response_schema_version", "Not recorded"))
    generation = content["ai"].get("generation") or {}
    rich(
        "Generation settings",
        f"Temperature {generation.get('temperature', 'N/A')}; output tokens cap {generation.get('max_output_tokens', 'N/A')}",
    )
    usage = content["ai"].get("usage") or {}
    rich(
        "Token usage",
        f"Input {usage.get('input_tokens', 'N/A')}; output {usage.get('output_tokens', 'N/A')}",
    )
    rich("Evidence snapshot", content["ai"]["evidence_snapshot"]["id"])
    rich("Evidence SHA-256", content["ai"]["evidence_snapshot"]["sha256"])
    rich("Consent recorded", _time(content["ai"].get("consent_accepted_at")))
    rich("Human review recorded", _time(human.get("reviewed_at")))
    rich("Reviewer ID", human.get("author_id") or "Not recorded")
    paragraph(
        "AI findings are advisory. Human decisions are recorded separately from model output.",
        "small",
    )

    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=21 * mm,
        rightMargin=21 * mm,
        topMargin=23 * mm,
        bottomMargin=22 * mm,
        title="IncidentForge - Incident Postmortem",
        author="IncidentForge AI",
        pageCompression=1,
        invariant=1,
    )

    def decorate(pdf_canvas, doc):
        if doc.page > MAX_PDF_PAGES:
            raise PostmortemExportError(
                "export_too_large", "This report exceeds the PDF page limit."
            )
        pdf_canvas.saveState()
        w, _ = A4
        pdf_canvas.setStrokeColor(BORDER)
        pdf_canvas.line(21 * mm, 17 * mm, w - 21 * mm, 17 * mm)
        pdf_canvas.setFont("Helvetica", 8)
        pdf_canvas.setFillColor(MUTED)
        pdf_canvas.drawString(21 * mm, 12 * mm, "IncidentForge  |  Finalized postmortem")
        pdf_canvas.drawRightString(w - 21 * mm, 12 * mm, f"Page {doc.page}")
        pdf_canvas.restoreState()

    try:
        pdf.build(
            elements,
            onFirstPage=decorate,
            onLaterPages=decorate,
            canvasmaker=canvas.Canvas,
        )
    except PostmortemExportError:
        raise
    except (ValueError, TypeError, OSError, AttributeError, KeyError) as exc:
        raise PostmortemExportError(
            "export_render_failed", "This PDF could not be generated."
        ) from exc
    data = buffer.getvalue()
    if not data.startswith(b"%PDF-"):
        raise PostmortemExportError("export_render_failed", "This PDF could not be generated.")
    if len(data) > MAX_PDF_BYTES:
        raise PostmortemExportError("export_too_large", "This report exceeds the PDF size limit.")
    return data
