"""Optimistic concurrency control via ETag / If-Match.

Every mutable row carries a monotonic ``version`` maintained by a database trigger. The API
returns it as a weak-free entity tag and, when a client sends ``If-Match``, makes the update
conditional on it:

    GET   /api/v1/leads/{id}      -> 200, ETag: "7"
    PATCH /api/v1/leads/{id}      If-Match: "7"  -> 200, ETag: "8"
    PATCH /api/v1/leads/{id}      If-Match: "7"  -> 412 Precondition Failed

Without ``If-Match`` the write proceeds unconditionally, so existing clients keep working;
sending it is what buys protection from a lost update. ``If-Match: *`` means "any current
version", i.e. the row must merely exist.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import Depends, Header, Response

from app.core.errors import APIError, ConflictError, NotFoundError
from app.db.supabase import SupabaseClient

_ETAG_RE = re.compile(r'^(?:W/)?"?(\d+)"?$')

#: Sent by a client that wants the write to apply regardless of the current version.
ANY_VERSION = "*"


class PreconditionFailedError(APIError):
    """The row moved on since the client last read it."""

    status_code = 412
    code = "precondition_failed"
    title = "Precondition Failed"


def etag_for(version: Any) -> str:
    return f'"{version}"'


def set_etag(response: Response, row: dict[str, Any]) -> None:
    """Attach the row's version as an ETag, when the table carries one."""
    version = row.get("version")
    if version is not None:
        response.headers["ETag"] = etag_for(version)


def parse_if_match(
    if_match: Annotated[
        str | None,
        Header(
            alias="If-Match",
            description=(
                'Version the client last read, as returned in ETag (e.g. "7"). When present, '
                "the write is rejected with 412 if the row has changed since. Use * to require "
                "only that the row exists."
            ),
        ),
    ] = None,
) -> int | None | str:
    """Return the expected version, ``ANY_VERSION``, or None when the header is absent."""
    if if_match is None:
        return None
    candidate = if_match.strip()
    if candidate == ANY_VERSION:
        return ANY_VERSION

    # A client may legitimately send several tags; accept the write if any parses.
    for part in candidate.split(","):
        match = _ETAG_RE.match(part.strip())
        if match:
            return int(match.group(1))

    raise PreconditionFailedError(
        "If-Match must be an ETag returned by this API, or *",
    )


IfMatchDep = Annotated["int | None | str", Depends(parse_if_match)]


async def update_guarded(
    db: SupabaseClient,
    table: str,
    *,
    record_id: str,
    changes: dict[str, Any],
    if_match: int | None | str,
    what: str,
    id_column: str = "id",
) -> dict[str, Any]:
    """Apply an update, honouring If-Match when the caller supplied one.

    The conditional write and the version check are the same statement, so there is no window
    between checking and writing for another client to slip through.
    """
    params = {id_column: f"eq.{record_id}"}
    if isinstance(if_match, int):
        params["version"] = f"eq.{if_match}"

    result = await db.update(table, params, changes)
    row = result.first()
    if row is not None:
        return row

    # Zero rows updated. Distinguish "gone" from "someone else got there first" so the client
    # knows whether to refetch and retry or to stop.
    current = await db.select(table, params={"select": "*", id_column: f"eq.{record_id}"})
    existing = current.first()
    if existing is None:
        raise NotFoundError(f"{what} not found")

    if isinstance(if_match, int):
        raise PreconditionFailedError(
            f"{what} has been modified since you last read it "
            f"(expected version {if_match}, current version {existing.get('version')}). "
            "Refetch and reapply your changes.",
            extra={"current_version": existing.get("version")},
        )

    # The row exists and no precondition was set, so row-level security filtered the write.
    raise PreconditionFailedError(
        f"You do not have permission to modify this {what.lower()}",
        code="forbidden",
        title="Forbidden",
        status_code=403,
    )


async def soft_delete_guarded(
    db: SupabaseClient,
    table: str,
    *,
    record_id: str,
    if_match: int | None | str,
    what: str,
    deleted_at: str | None = None,
) -> None:
    """Mark a row deleted through the database function for that table.

    Not a PATCH. The SELECT policies hide soft-deleted rows, and PostgREST builds every write
    with a RETURNING clause -- even for ``return=minimal`` -- so row-level security evaluates
    the SELECT policy against the row the delete just produced and rejects it with 42501,
    whoever the caller is. The function does the ownership check explicitly and runs as its
    definer, which sidesteps the contradiction.
    """
    function = f"soft_delete_{table.rstrip('s')}"
    payload: dict[str, Any] = {"p_id": record_id}
    if isinstance(if_match, int):
        payload["p_expected_version"] = if_match

    result = await db.rpc(function, payload)
    outcome = result.data
    if isinstance(outcome, list) and outcome:
        outcome = outcome[0]
    if not isinstance(outcome, dict):
        outcome = {"status": "not_found"}

    status_value = outcome.get("status")
    if status_value == "deleted":
        return
    if status_value == "not_found":
        raise NotFoundError(f"{what} not found")
    if status_value == "referenced":
        raise ConflictError(
            f"{what} is the primary contact on a lead; reassign the lead first"
        )
    if status_value == "version_mismatch":
        raise PreconditionFailedError(
            f"{what} has been modified since you last read it "
            f"(current version {outcome.get('current_version')}).",
            extra={"current_version": outcome.get("current_version")},
        )
    raise PreconditionFailedError(
        f"You do not have permission to delete this {what.lower()}",
        code="forbidden",
        title="Forbidden",
        status_code=403,
    )
