"""Generate a tailored cover letter from a resume and a job description.

Uses the official Anthropic SDK. Prompt construction is a separate, pure
function (`build_user_message`) so it can be unit-tested without a network
call — the actual Claude call happens only in `generate`.
"""

from __future__ import annotations

from .. import config


class LLMConfigError(RuntimeError):
    """Raised when the LLM is not configured (missing API key)."""


_SYSTEM = (
    "You are an expert career coach writing a cover letter for a software "
    "engineering job application. Write in the candidate's voice using ONLY "
    "the experience and skills present in their resume — never invent roles, "
    "employers, technologies, or achievements. Tailor the letter specifically "
    "to the job description: reference the company and role by name, and "
    "connect 2-3 concrete pieces of the candidate's real experience to what "
    "the role asks for. Keep it to 3-4 short paragraphs, professional but not "
    "stiff, no placeholder brackets, no headers or salutation boilerplate "
    "beyond a simple greeting and sign-off. Output plain text only."
)


def build_user_message(
    resume_text: str, job_title: str, company: str, job_description: str
) -> str:
    return (
        f"Job title: {job_title}\n"
        f"Company: {company}\n\n"
        f"Job description:\n{job_description}\n\n"
        f"Candidate resume:\n{resume_text}\n\n"
        "Write the cover letter now."
    )


def generate(
    resume_text: str, job_title: str, company: str, job_description: str
) -> str:
    api_key = config.anthropic_api_key()
    if not api_key:
        raise LLMConfigError(
            "ANTHROPIC_API_KEY is not set. Add it to your environment (.env)."
        )

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    user_msg = build_user_message(resume_text, job_title, company, job_description)

    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=2048,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()
