"""CSV import schemas. The file is parsed and column-mapped in the browser; the API receives
rows already keyed by field (see ``GET /imports/fields`` for each kind's field keys)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from app.domain.imports import MAX_ROWS_PER_REQUEST
from app.schemas.common import APIModel, StrictAPIModel

ImportKind = Literal["companies", "contacts", "leads"]


class ImportFieldInfo(APIModel):
    key: str
    label: str
    required: bool
    aliases: list[str] = Field(description="Lower-case column headers this field is auto-mapped from.")
    help: str = ""


class ImportCatalog(APIModel):
    kinds: dict[str, list[ImportFieldInfo]]
    max_rows_per_request: int


class ImportRow(StrictAPIModel):
    row_number: int = Field(ge=1, description="The row's line in the uploaded file, echoed back in results.")
    values: dict[str, str | None] = Field(description="Field key -> raw cell text.")

    @field_validator("values")
    @classmethod
    def _bounded(cls, values: dict[str, str | None]) -> dict[str, str | None]:
        if len(values) > 40:
            raise ValueError("at most 40 fields per row")
        for key, value in values.items():
            if len(key) > 64 or (value is not None and len(value) > 5000):
                raise ValueError("field key or value too long")
        return values


class ImportRequest(StrictAPIModel):
    rows: list[ImportRow] = Field(min_length=1, max_length=MAX_ROWS_PER_REQUEST)


class ImportRowResult(APIModel):
    row_number: int
    status: Literal["created", "existing", "skipped", "error"]
    record_id: str | None = None
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ImportResult(APIModel):
    kind: ImportKind
    created: int
    existing: int
    skipped: int
    failed: int
    rows: list[ImportRowResult]
