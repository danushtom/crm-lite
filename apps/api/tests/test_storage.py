"""Private buckets: object paths on the row, signed links in the response.

Proposals carry pricing and contract terms; a voice agent's knowledge base carries pricing
sheets and internal scripts. Both used to be written to a public bucket, with the resulting
`/object/public/...` URL stored on the row -- so anyone who ever saw the link could read the
file forever, and links leak easily (out of the API to every org member, into browser history,
into `Referer` on the next click).
"""

from __future__ import annotations

import pytest

from app.services import storage


def test_an_object_path_is_namespaced_and_randomised():
    path = storage.object_path("opp-1", "terms.pdf", fallback="proposal")
    assert path.startswith("opp-1/")
    assert path.endswith("_terms.pdf")
    # The random segment is what stops one upload silently replacing another of the same name.
    assert storage.object_path("opp-1", "terms.pdf", fallback="proposal") != path


@pytest.mark.parametrize(
    "filename",
    ["../../etc/passwd", "..\\..\\secrets.env", "a/b/c.pdf", ".hidden"],
)
def test_a_crafted_filename_cannot_escape_its_prefix(filename):
    path = storage.object_path("opp-1", filename, fallback="proposal")
    segments = path.split("/")
    assert segments[0] == "opp-1"
    # The defence is that every separator becomes "_", leaving one flat segment under the
    # prefix. A literal ".." can survive inside that name and is inert without a separator
    # to traverse on, so this asserts the shape rather than banning the characters.
    assert len(segments) == 2
    assert "\\" not in segments[1]


def test_an_empty_filename_falls_back_rather_than_producing_a_bare_prefix():
    path = storage.object_path("opp-1", "", fallback="proposal")
    assert path.startswith("opp-1/")
    assert path.rsplit("_", 1)[-1] == "proposal"


@pytest.mark.anyio
async def test_signing_an_empty_path_returns_nothing():
    assert await storage.signed_url(bucket="proposals", path="") is None


@pytest.mark.anyio
async def test_a_legacy_absolute_url_is_passed_through(monkeypatch):
    """Rows written before the move to private buckets hold a full URL. Nothing in this project
    has one, but a deployment that did should keep working rather than being handed a link
    built by prefixing a URL onto the storage host."""
    legacy = "https://example.supabase.co/storage/v1/object/public/proposals/old.pdf"
    assert await storage.signed_url(bucket="proposals", path=legacy) == legacy


def test_the_signed_link_ttl_is_short():
    """A signed link pasted into a chat should stop working quickly; this is the whole reason
    the bucket is private rather than public-with-an-unguessable-name."""
    assert 0 < storage.SIGNED_URL_TTL_SECONDS <= 900
