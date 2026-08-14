"""Tests for cover-letter prompt construction (no live Claude call)."""

import pytest

from coverletterer.services import cover_letter


def test_build_user_message_includes_all_inputs():
    msg = cover_letter.build_user_message(
        resume_text="Experienced Python developer.",
        job_title="Senior DevOps Engineer",
        company="PaperCut Software",
        job_description="Looking for someone with cloud experience.",
    )
    assert "Senior DevOps Engineer" in msg
    assert "PaperCut Software" in msg
    assert "Experienced Python developer." in msg
    assert "Looking for someone with cloud experience." in msg


def test_generate_requires_api_key(monkeypatch):
    monkeypatch.setattr(cover_letter.config, "anthropic_api_key", lambda: None)
    with pytest.raises(cover_letter.LLMConfigError):
        cover_letter.generate("resume", "title", "company", "description")
