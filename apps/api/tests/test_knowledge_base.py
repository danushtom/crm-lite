"""The knowledge base's tenant boundary.

Qdrant has no row-level security. Unlike every other store in this product, a forgotten filter
here does not fail closed -- it returns another organization's pricing sheets. These tests assert
the three properties that stand in for RLS:

  1. A search cannot be issued without an organization.
  2. Every read and delete carries the organization as a `must` condition.
  3. A payload that comes back with the wrong tenant is dropped rather than served.

If a future change makes `organization_id` optional or defaulted anywhere in `vector_store`, one
of these fails.
"""

from __future__ import annotations

import pytest
from dracara_ai import vector_store
from dracara_ai.config import ai_settings

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"


def _matched(filter_obj) -> dict[str, str]:
    """Flatten a Qdrant filter's `must` conditions into {field: value}."""
    return {c.key: c.match.value for c in filter_obj.must}


# --- 1. An organization is always required ---------------------------------------


def test_a_filter_cannot_be_built_without_an_organization():
    with pytest.raises(ValueError, match="tenant boundary"):
        vector_store._tenant_filter(organization_id="")


def test_search_requires_its_scoping_arguments_by_keyword():
    """Keyword-only and required, so no caller can pass them positionally by accident or omit
    them and inherit a default."""
    with pytest.raises(TypeError):
        vector_store.search(ORG_A, "va-1", [0.1])  # type: ignore[call-arg,misc]


# --- 2. Scoping is applied as a `must` condition ----------------------------------


def test_the_filter_scopes_by_organization_and_agent():
    matched = _matched(
        vector_store._tenant_filter(organization_id=ORG_A, voice_agent_id="va-1")
    )
    assert matched == {"organization_id": ORG_A, "voice_agent_id": "va-1"}


def test_the_delete_filter_is_scoped_by_organization_too():
    """A stale or crafted document id must not be able to delete another tenant's points."""
    matched = _matched(
        vector_store._tenant_filter(organization_id=ORG_A, document_id="doc-1")
    )
    assert matched["organization_id"] == ORG_A
    assert matched["document_id"] == "doc-1"


@pytest.mark.asyncio
async def test_search_sends_the_organization_filter_to_qdrant(monkeypatch):
    captured: dict = {}

    class FakePoint:
        def __init__(self, payload):
            self.payload = payload
            self.score = 0.9
            self.id = "p1"

    class FakeResponse:
        points = [
            FakePoint(
                {
                    "organization_id": ORG_A,
                    "text": "Our MVP package starts at 5,00,000 INR.",
                    "document_id": "doc-1",
                    "filename": "pricing.pdf",
                    "chunk_index": 0,
                }
            )
        ]

    class FakeClient:
        async def query_points(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    monkeypatch.setattr(vector_store, "get_qdrant_client", lambda: FakeClient())
    monkeypatch.setattr(vector_store, "ensure_collection", _noop)

    results = await vector_store.search(
        organization_id=ORG_A, voice_agent_id="va-1", query_vector=[0.1, 0.2]
    )

    assert _matched(captured["query_filter"])["organization_id"] == ORG_A
    assert results[0].text.startswith("Our MVP package")


async def _noop(*_args, **_kwargs):
    return None


# --- 3. A wrong-tenant payload is never served ------------------------------------


@pytest.mark.asyncio
async def test_a_result_from_another_organization_is_dropped(monkeypatch):
    """If the filter ever silently fails, the defence in depth in `search` must catch it.

    This is the scenario that has no equivalent elsewhere in the codebase: Postgres would simply
    not have returned the row.
    """

    class FakePoint:
        def __init__(self, org):
            self.payload = {
                "organization_id": org,
                "text": f"secret pricing for {org}",
                "document_id": "doc-x",
                "filename": "pricing.pdf",
                "chunk_index": 0,
            }
            self.score = 0.99
            self.id = f"p-{org}"

    class FakeResponse:
        points = [FakePoint(ORG_B), FakePoint(ORG_A)]

    class FakeClient:
        async def query_points(self, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(vector_store, "get_qdrant_client", lambda: FakeClient())
    monkeypatch.setattr(vector_store, "ensure_collection", _noop)

    results = await vector_store.search(
        organization_id=ORG_A, voice_agent_id="va-1", query_vector=[0.1]
    )

    assert len(results) == 1
    assert ORG_B not in results[0].text


# --- Point ids -------------------------------------------------------------------


def test_reindexing_a_document_overwrites_its_own_points():
    """Deterministic ids are what make indexing idempotent -- a retry must not double a
    document's chunks in the index."""
    assert vector_store.point_id("doc-1", 0) == vector_store.point_id("doc-1", 0)
    assert vector_store.point_id("doc-1", 0) != vector_store.point_id("doc-1", 1)
    assert vector_store.point_id("doc-1", 0) != vector_store.point_id("doc-2", 0)


# --- Chunking and extraction ------------------------------------------------------


def test_chunking_overlaps_so_a_sentence_on_a_boundary_stays_findable():
    from dracara_ai.chunking import chunk_text

    text = "\n\n".join(f"Paragraph {i} about pricing and delivery." for i in range(60))
    chunks = chunk_text(text, size=400, overlap=80)

    assert len(chunks) > 1
    assert all(len(c) <= 400 + 80 for c in chunks)
    # Every chunk carries content; an empty chunk would waste an embedding call.
    assert all(c.strip() for c in chunks)


def test_short_documents_are_a_single_chunk():
    from dracara_ai.chunking import chunk_text

    assert chunk_text("Our MVP package starts at 5,00,000 INR.") == [
        "Our MVP package starts at 5,00,000 INR."
    ]


def test_an_unsupported_file_type_is_rejected_by_name_not_by_content_type():
    """`content_type` comes from the uploading client and is not trustworthy -- `storage.py`
    makes the same point about why signed links force a download."""
    from dracara_ai.extract import extract_text, is_supported
    from dracara_ai.extract import UnsupportedDocumentError

    assert not is_supported("malware.exe")
    with pytest.raises(UnsupportedDocumentError):
        extract_text(b"MZ\x90\x00", "malware.exe")


def test_plain_text_and_markdown_extract_directly():
    from dracara_ai.extract import extract_text

    assert "pricing" in extract_text(b"# Rates\n\nOur pricing is fixed.", "rates.md")


def test_the_embedding_dimension_matches_the_collection(monkeypatch):
    """Changing the embedding model without changing the dimension (or re-indexing) makes every
    existing point unsearchable, silently."""
    assert ai_settings.openai_embedding_dimensions == 1536
    assert ai_settings.openai_embedding_model == "text-embedding-3-small"


# --- The SQL side of the tenant boundary ------------------------------------------
#
# Read as text rather than executed: there is no database in this test run. These assert the
# properties of the migration that, if they regressed, would fail silently in production rather
# than loudly here.

import pathlib
import re

MIGRATION = pathlib.Path("../../supabase/migrations/20260918000000_ai_features.sql")


def _migration() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _has_permission_body() -> str:
    """The text between the has_permission header and the end of its dollar-quoted body."""
    after_header = _migration().split("CREATE OR REPLACE FUNCTION public.has_permission", 1)[1]
    return after_header.split("$$;", 1)[0]


def test_has_permission_requires_the_user_to_still_be_active():
    """20260909020000 made deactivation actually revoke access by adding `is_active` to
    current_org_id(), is_admin() and can_access_lead(). A fourth chokepoint that omitted it
    would be a standing grant for a revoked user."""
    assert "u.is_active" in _has_permission_body()


def test_has_permission_is_security_definer_and_stable():
    body = _migration().split("CREATE OR REPLACE FUNCTION public.has_permission")[1][:600]
    assert "SECURITY DEFINER" in body
    assert "SET search_path = public" in body
    assert "STABLE" in body


def test_has_permission_is_executable_by_authenticated():
    """A policy expression runs as the querying role, so `authenticated` needs EXECUTE — the
    initial schema grants is_admin() and current_org_id() the same way."""
    sql = _migration()
    assert "GRANT ALL ON FUNCTION public.has_permission(UUID, TEXT, TEXT) TO authenticated;" in sql


def test_every_repointed_policy_keeps_its_organization_clause():
    """Swapping is_admin() for has_permission() must not drop the org comparison alongside it —
    that clause is what scopes the policy to one tenant."""
    sql = _migration()
    for block in re.findall(r"CREATE POLICY \w+ ON public\.\w+ FOR (?:INSERT|UPDATE|DELETE).*?;", sql, re.S):
        if "has_permission" in block:
            assert "current_org_id(auth.uid())" in block, block[:160]


def test_the_new_tables_accept_no_writes_from_authenticated_users():
    """ai_usage and deal_health_snapshots are written only by service-role callers. A user who
    could forge a usage row could exhaust another tenant's budget; one who could forge a health
    snapshot could plant text that lands in a colleague's daily brief."""
    sql = _migration()
    for table in ("ai_usage", "deal_health_snapshots"):
        for verb in ("INSERT", "UPDATE", "DELETE"):
            assert not re.search(rf"CREATE POLICY \w+ ON public\.{table} FOR {verb}", sql)
        assert re.search(rf"CREATE POLICY \w+ ON public\.{table} FOR SELECT", sql)


def test_ai_usage_is_readable_only_with_the_manage_permission():
    sql = _migration()
    policy = re.search(r"CREATE POLICY ai_usage_select.*?;", sql, re.S).group(0)
    assert "current_org_id(auth.uid())" in policy
    assert "'ai', 'manage'" in policy


def test_deal_health_visibility_follows_the_opportunity():
    """Reusing can_access_lead() through the opportunity keeps this in step with opp_select
    instead of restating its ownership rule and drifting from it."""
    sql = _migration()
    policy = re.search(r"CREATE POLICY deal_health_snapshots_select.*?;\n", sql, re.S).group(0)
    assert "current_org_id(auth.uid())" in policy
    assert "can_access_lead(auth.uid(), o.lead_id)" in policy


def test_every_new_table_derives_or_guards_its_organization():
    """A tenant-owned table must never take organization_id on trust from a user session.
    deal_health_snapshots derives it from its opportunity; ai_usage has no owning FK, so it
    guards instead -- a real user session has its own organization forced in."""
    sql = _migration()
    assert "EXECUTE FUNCTION public.set_parent_organization('opportunities', 'opportunity_id')" in sql
    assert "EXECUTE FUNCTION public.set_ai_usage_organization()" in sql

    guard = sql.split("FUNCTION public.set_ai_usage_organization", 1)[1].split("$$;", 1)[0]
    assert "auth.uid() IS NOT NULL" in guard
    assert "current_org_id(auth.uid())" in guard
    # And it fails closed rather than writing a NULL-org row.
    assert "RAISE EXCEPTION" in guard
