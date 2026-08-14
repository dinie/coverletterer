"""Tests for cover-letter PDF export."""

from coverletterer.services import pdf_export


def test_render_cover_letter_pdf_returns_valid_pdf_bytes():
    pdf_bytes = pdf_export.render_cover_letter_pdf(
        "Dear Hiring Manager,\n\nI would love to join your team.\n\nBest,\nJane",
        job_title="Senior DevOps Engineer",
        company="PaperCut Software",
    )
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 500


def test_render_cover_letter_pdf_handles_empty_content():
    pdf_bytes = pdf_export.render_cover_letter_pdf("")
    assert pdf_bytes.startswith(b"%PDF-")


def test_render_cover_letter_pdf_handles_long_content():
    long_content = "\n\n".join(f"Paragraph {i} " * 40 for i in range(30))
    pdf_bytes = pdf_export.render_cover_letter_pdf(long_content)
    assert pdf_bytes.startswith(b"%PDF-")
