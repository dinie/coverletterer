"""Tests for resume ingestion: PDF/HTML text extraction and resume resolution."""

import io

import pytest

from coverletterer.services import resume_ingest


def _make_pdf_bytes(text: str) -> bytes:
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(72, 720, text)
    c.save()
    return buffer.getvalue()


def test_extract_pdf_text_returns_page_text():
    pdf_bytes = _make_pdf_bytes("Jane Doe - Software Engineer")
    text = resume_ingest.extract_pdf_text(pdf_bytes)
    assert "Jane Doe" in text
    assert "Software Engineer" in text


def test_extract_pdf_text_raises_on_garbage():
    with pytest.raises(resume_ingest.ResumeIngestError):
        resume_ingest.extract_pdf_text(b"not a pdf")


def test_get_effective_resume_prefers_override(monkeypatch):
    store = {(1, 5): "override-resume", (1, None): "default-resume"}
    monkeypatch.setattr(
        resume_ingest, "_existing", lambda uid, aid: store.get((uid, aid))
    )
    assert resume_ingest.get_effective_resume(1, 5) == "override-resume"


def test_get_effective_resume_falls_back_to_default(monkeypatch):
    store = {(1, None): "default-resume"}
    monkeypatch.setattr(
        resume_ingest, "_existing", lambda uid, aid: store.get((uid, aid))
    )
    assert resume_ingest.get_effective_resume(1, 5) == "default-resume"


def test_get_effective_resume_none_when_neither_exists(monkeypatch):
    monkeypatch.setattr(resume_ingest, "_existing", lambda uid, aid: None)
    assert resume_ingest.get_effective_resume(1, 5) is None


def test_get_effective_resume_default_only_lookup(monkeypatch):
    store = {(1, None): "default-resume"}
    monkeypatch.setattr(
        resume_ingest, "_existing", lambda uid, aid: store.get((uid, aid))
    )
    assert resume_ingest.get_effective_resume(1, None) == "default-resume"
