"""Typed view-models for state vars.

Reflex needs typed vars to render `rx.foreach` / `.length()` over nested data,
so we expose DB rows to the UI as these dataclasses rather than dicts.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class ApplicationVM:
    id: int = 0
    job_title: str = ""
    company: str = ""
    site: str = ""
    status: str = ""
    draft_count: int = 0
    created_at: str = ""


@dataclasses.dataclass
class DraftVM:
    id: int = 0
    label: str = ""
    content: str = ""
    saved: bool = False
    updated_at: str = ""


@dataclasses.dataclass
class ResumeVM:
    present: bool = False
    source_type: str = ""
    source_label: str = ""  # filename (upload) or URL
    preview: str = ""  # truncated extracted text
    updated_at: str = ""
