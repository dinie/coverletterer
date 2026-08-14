"""Render a cover-letter draft's text content into a simple one-page PDF.

`reportlab` is pure Python (no native/system dependencies like `weasyprint`
needs), which keeps local setup and future deployment simple. Generated on
demand from the draft's current text — nothing is persisted.
"""

from __future__ import annotations

import datetime
import io


def render_cover_letter_pdf(content: str, job_title: str = "", company: str = "") -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "CoverLetterBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=16,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "CoverLetterHeading",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor="#555555",
        spaceAfter=18,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        leftMargin=1 * inch,
        rightMargin=1 * inch,
    )

    story = []
    header_bits = [datetime.date.today().strftime("%d %B %Y")]
    if job_title:
        header_bits.append(job_title)
    if company:
        header_bits.append(company)
    story.append(Paragraph(" — ".join(header_bits), heading_style))
    story.append(Spacer(1, 6))

    for para in content.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        # Paragraph() treats bare text as HTML-ish markup; escape the basics.
        safe = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe = safe.replace("\n", "<br/>")
        story.append(Paragraph(safe, body_style))

    doc.build(story)
    return buffer.getvalue()
