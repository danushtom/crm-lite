"""Company endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUserDep, DbDep
from app.core.pagination import Page, PageParamsDep
from app.schemas.common import AUTH_RESPONSES, ERROR_RESPONSES
from app.schemas.companies import Company, CompanyCreate, CompanyUpdate

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.get(
    "",
    response_model=Page[Company],
    summary="List companies",
    description="Companies visible to the caller under row-level security, newest first.",
    responses=AUTH_RESPONSES,
)
async def list_companies(
    db: DbDep,
    page: PageParamsDep,
    search: Annotated[
        str | None, Query(max_length=200, description="Case-insensitive match on company name.")
    ] = None,
) -> Page[Company]:
    params: dict[str, str] = {
        "select": "*",
        "order": "created_at.desc,id.desc",
        "limit": str(page.limit),
        "offset": str(page.offset),
    }
    if search and search.strip():
        cleaned = search.strip().replace("*", "").replace("%", "")[:200]
        if cleaned:
            params["name"] = f"ilike.*{cleaned}*"

    result = await db.select("companies", params=params, count=True)
    return Page.build([Company.model_validate(r) for r in result.rows], page, result.count)


@router.post(
    "",
    response_model=Company,
    status_code=status.HTTP_201_CREATED,
    summary="Create a company",
    responses=ERROR_RESPONSES,
)
async def create_company(
    body: CompanyCreate,
    db: DbDep,
    user: CurrentUserDep,
    response: Response,
) -> Company:
    payload = body.model_dump(exclude_none=True)
    payload["created_by"] = user.sub
    result = await db.insert("companies", payload)
    company = Company.model_validate(result.one("Company"))
    response.headers["Location"] = f"{router.prefix}/{company.id}"
    return company


@router.get(
    "/{company_id}",
    response_model=Company,
    summary="Get a company",
    responses=ERROR_RESPONSES,
)
async def get_company(company_id: str, db: DbDep) -> Company:
    result = await db.select("companies", params={"select": "*", "id": f"eq.{company_id}"})
    return Company.model_validate(result.one("Company"))


@router.patch(
    "/{company_id}",
    response_model=Company,
    summary="Update a company",
    description="Partial update. Only the fields present in the request body are modified.",
    responses=ERROR_RESPONSES,
)
async def update_company(company_id: str, body: CompanyUpdate, db: DbDep) -> Company:
    changes = body.changes()
    if not changes:
        return await get_company(company_id, db)
    result = await db.update("companies", {"id": f"eq.{company_id}"}, changes)
    return Company.model_validate(result.one("Company"))
