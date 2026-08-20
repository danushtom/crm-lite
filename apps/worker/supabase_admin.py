"""Sync Supabase REST client using service role (worker only)."""

from __future__ import annotations

import json
from typing import Any

import httpx


class SupabaseAdmin:
    def __init__(self, base_url: str, service_role_key: str):
        self._base = base_url.rstrip("/") + "/rest/v1"
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: Any = None,
        prefer: str | None = None,
    ) -> Any:
        headers = {**self._headers}
        if prefer:
            headers["Prefer"] = prefer
        with httpx.Client(timeout=120.0) as client:
            r = client.request(
                method,
                f"{self._base}{path}",
                params=params,
                content=json.dumps(json_body) if json_body is not None else None,
                headers=headers,
            )
        if r.status_code == 409:
            return None
        if r.status_code >= 400:
            raise RuntimeError(f"Supabase {r.status_code}: {r.text}")
        if r.status_code == 204 or not r.content:
            return None
        ct = r.headers.get("content-type", "")
        if "application/json" in ct:
            return r.json()
        return r.text


def insert_notification(
    sb: SupabaseAdmin,
    *,
    user_id: str,
    notif_type: str,
    title: str,
    body: str | None,
    dedupe_key: str | None = None,
    metadata: dict[str, Any] | None = None,
    source_task_id: str | None = None,
    meeting_id: str | None = None,
) -> dict[str, Any] | None:
    payload = {
        "user_id": user_id,
        "type": notif_type,
        "title": title,
        "body": body,
        "metadata": metadata or {},
        "dedupe_key": dedupe_key,
        "source_task_id": source_task_id,
        "meeting_id": meeting_id,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    rows = sb.request("POST", "/notifications", json_body=payload, prefer="return=representation")
    if rows is None:
        return None
    if isinstance(rows, list) and rows:
        return rows[0]
    return rows if isinstance(rows, dict) else None
