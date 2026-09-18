"""CSV import. The browser parses the file and maps its columns; this validates, de-duplicates
and writes the rows, as the caller, in batches (see app/services/imports.py)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.api.deps import CurrentUserDep, DbDep, ProfileDep, is_full_access
from app.core.rate_limit import limiter
from app.domain.imports import FIELDS, MAX_ROWS_PER_REQUEST
from app.schemas.common import AUTH_RESPONSES, ERROR_RESPONSES
from app.schemas.imports import (
    ImportCatalog,
    ImportFieldInfo,
    ImportKind,
    ImportRequest,
    ImportResult,
    ImportRowResult,
)
from app.services.imports import run_import

router = APIRouter(prefix="/imports", tags=["Imports"])


@router.get(
    "/fields",
    response_model=ImportCatalog,
    summary="List importable fields per record type",
    description="Each field's aliases are the column headers the web app auto-maps to it.",
    responses=AUTH_RESPONSES,
)
async def import_fields(_user: CurrentUserDep) -> ImportCatalog:
    return ImportCatalog(
        kinds={
            kind: [
                ImportFieldInfo(
                    key=f.key, label=f.label, required=f.required, aliases=list(f.aliases), help=f.help
                )
                for f in fields
            ]
            for kind, fields in FIELDS.items()
        },
        max_rows_per_request=MAX_ROWS_PER_REQUEST,
    )


@router.post(
    "/{kind}",
    response_model=ImportResult,
    summary="Import a batch of rows",
    description=(
        f"Up to {MAX_ROWS_PER_REQUEST} rows per request. Runs as the caller, under row-level "
        "security. Existing companies (by domain or name), contacts (by email) and leads (by "
        "company and contact) are matched rather than duplicated, so a batch is safe to retry. "
        "Every row gets a result; one bad row never fails the others."
    ),
    responses=ERROR_RESPONSES,
)
@limiter.limit("120/minute")
async def import_rows(
    request: Request,
    response: Response,
    kind: ImportKind,
    body: ImportRequest,
    db: DbDep,
    user: CurrentUserDep,
    profile: ProfileDep,
) -> ImportResult:
    results = await run_import(
        db,
        kind,
        [(row.row_number, row.values) for row in body.rows],
        user_id=user.sub,
        full_access=is_full_access(profile),
    )
    rows = [
        ImportRowResult(
            row_number=r.row_number,
            status=r.status,  # type: ignore[arg-type]
            record_id=r.record_id,
            message=r.message,
            warnings=r.warnings,
        )
        for r in results
    ]
    count = lambda status: sum(1 for r in rows if r.status == status)  # noqa: E731
    return ImportResult(
        kind=kind,
        created=count("created"),
        existing=count("existing"),
        skipped=count("skipped"),
        failed=count("error"),
        rows=rows,
    )
