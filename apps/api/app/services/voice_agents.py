"""Voice agents: knowledge-base document upload, and compiling a script into a prompt."""

from __future__ import annotations

from typing import Any

from dracara_ai import voice_script

from app.core.config import settings
from app.services import storage


async def upload_document(
    *,
    voice_agent_id: str,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> str:
    """Store a knowledge-base document and return its object path.

    A path, not a URL: the bucket is private, so a readable link is signed per response and
    expires. These files hold pricing sheets and internal call scripts, which is exactly the
    material that should not sit behind a permanent public link.
    """
    path = storage.object_path(voice_agent_id, filename, fallback="document")
    return await storage.upload(
        bucket=settings.voice_kb_bucket, path=path, data=data, content_type=content_type
    )


# ---------------------------------------------------------------------------
# Script compilation. The one place an agent's `system_prompt` is produced.
# ---------------------------------------------------------------------------


def disclosure_for(persona_name: str, organization_name: str) -> str:
    """The fixed opening line, bound to the platform's own greeting field rather than the
    prompt (see voice_platform.create_assistant), so it plays on every call whatever the script
    says. Uses the persona name because that is the name the caller hears all call."""
    return (
        f"You're speaking with {persona_name}, an AI assistant from {organization_name}. "
        "This call may be recorded."
    )


def default_data_access() -> dict[str, Any]:
    return {
        "tools": {name: True for name in voice_script.DEFAULT_TOOLS},
        "lead_fields": list(voice_script.DEFAULT_LEAD_FIELDS),
    }


def resolve_persona(
    *, name: str, persona_name: str | None, role_title: str | None
) -> tuple[str, str]:
    """An agent always has a name to say and a role to claim on the phone. Falling back to the
    CRM label keeps a half-filled form from producing "You are , at Acme"."""
    return (
        (persona_name or "").strip() or name.strip(),
        (role_title or "").strip() or "assistant",
    )


def compile_system_prompt(
    *,
    script: dict[str, Any] | None,
    data_access: dict[str, Any] | None,
    name: str,
    persona_name: str | None,
    role_title: str | None,
    organization_name: str,
) -> str:
    resolved_name, resolved_role = resolve_persona(
        name=name, persona_name=persona_name, role_title=role_title
    )
    return voice_script.compile_prompt(
        script,
        persona_name=resolved_name,
        role_title=resolved_role,
        organization_name=organization_name,
        data_access=data_access,
    )


def build_preview(
    *,
    script: dict[str, Any] | None,
    data_access: dict[str, Any] | None,
    name: str,
    persona_name: str | None,
    role_title: str | None,
    organization_name: str,
) -> tuple[list[dict[str, str]], str, str]:
    """(walkthrough, compiled prompt, disclosure) for a script -- saved or still being edited.

    The builder screen shows all three from one call, so what an admin reads is produced by the
    same code that will brief the agent, not by a second description of it in the browser.
    """
    resolved_name, resolved_role = resolve_persona(
        name=name, persona_name=persona_name, role_title=role_title
    )
    disclosure = disclosure_for(resolved_name, organization_name)
    prompt = voice_script.compile_prompt(
        script,
        persona_name=resolved_name,
        role_title=resolved_role,
        organization_name=organization_name,
        data_access=data_access,
    )
    steps = voice_script.preview_steps(
        script,
        persona_name=resolved_name,
        organization_name=organization_name,
        disclosure_script=disclosure,
        data_access=data_access,
    )
    return steps, prompt, disclosure
