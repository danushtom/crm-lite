import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock

from app.deps import TokenUser
from app.rbac import forbid_partner_intel_edit


@pytest.mark.asyncio
async def test_forbid_partner_intel_edit_blocks_partner():
    sb = AsyncMock()
    sb.request = AsyncMock(return_value=[{"role": "partner"}])
    user = TokenUser(sub="user-1", email="p@example.com")
    with pytest.raises(HTTPException) as ei:
        await forbid_partner_intel_edit(sb=sb, user=user)
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_forbid_partner_intel_edit_allows_agent():
    sb = AsyncMock()
    sb.request = AsyncMock(return_value=[{"role": "agent"}])
    user = TokenUser(sub="user-2", email="a@example.com")
    await forbid_partner_intel_edit(sb=sb, user=user)
