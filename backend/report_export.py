"""
report_export.py — Render a workflow run as Markdown or PDF.

Proof-of-work export for Premium/Executive customers ("what did this
automation actually do"). Never raises for missing optional fields —
a run always has node_results/status/timestamps at minimum.
"""

import io
import json


def run_to_markdown(run: dict, workflow_name: str) -> str:
    lines = [
        f"# Run: {workflow_name}", "",
        f"Status: **{run.get('status')}**  ",
        f"Started: {run.get('started_at')}  ",
        f"Finished: {run.get('finished_at') or '-'}", "",
        "## Nodes",
    ]
    for node_id, r in (run.get("node_results") or {}).items():
        lines.append(f"### {node_id} — {r.get('status')}")
        if r.get("output") is not None:
            lines.append("```json\n" + json.dumps(r["output"], indent=2, default=str) + "\n```")
        if r.get("error"):
            lines.append(f"**Error:** {r['error']}")
        results = (r.get("output") or {}).get("results") if isinstance(r.get("output"), dict) else None
        if results:
            lines.append("**Sources:**")
            for src in results:
                lines.append(f"- [{src.get('title','')}]({src.get('link','')})")
    usage = run.get("usage") or {}
    if usage.get("total_tokens"):
        lines += ["", "## Usage", f"Tokens: {usage.get('total_tokens')}  ", f"LLM calls: {usage.get('llm_calls')}"]
    return "\n".join(lines)


def run_to_pdf(run: dict, workflow_name: str) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.7 * inch, bottomMargin=0.7 * inch)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"Run: {workflow_name}", styles["Title"]),
        Paragraph(f"Status: {run.get('status')}", styles["Normal"]),
        Paragraph(f"Started: {run.get('started_at')} — Finished: {run.get('finished_at') or '-'}", styles["Normal"]),
        Spacer(1, 12),
    ]
    for node_id, r in (run.get("node_results") or {}).items():
        story.append(Paragraph(f"{node_id} — {r.get('status')}", styles["Heading3"]))
        if r.get("output") is not None:
            text = json.dumps(r["output"], indent=2, default=str)[:4000]
            story.append(Preformatted(text, styles["Code"]))
        if r.get("error"):
            story.append(Paragraph(f"Error: {r['error']}", styles["Normal"]))
        story.append(Spacer(1, 8))
    usage = run.get("usage") or {}
    if usage.get("total_tokens"):
        story.append(Paragraph(f"Tokens used: {usage.get('total_tokens')} — LLM calls: {usage.get('llm_calls')}", styles["Normal"]))
    doc.build(story)
    return buf.getvalue()
