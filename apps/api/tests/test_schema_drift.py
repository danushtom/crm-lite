"""Every PostgREST filter in the API and worker names a column that exists.

The test fakes key responses on ``"{METHOD} {table}"`` and ignore query params, so a filter on a
column a migration dropped or moved passes every unit test and fails only against the real
database -- with a 400 that takes the whole request (or scheduled job) down. That has happened
twice: ``users.role`` (dropped by the dynamic-roles migration, still filtered on by the worker's
overdue escalation, which then failed every run) and ``leads.stage`` (moved to opportunities,
still filtered on by agent performance).

This rebuilds each table's columns from ``supabase/migrations`` and checks the filter keys in
every ``select/update/delete/count("table", ...)`` and ``request("GET", "/table", ...)`` call.
It is deliberately a heuristic -- literal table names and literal filter dicts only -- but those
are nearly every query in this codebase.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "supabase" / "migrations"
SOURCES = [ROOT / "apps" / "api" / "app", ROOT / "apps" / "worker"]

_CREATE = re.compile(r'CREATE TABLE (?:IF NOT EXISTS )?"?public"?\."?(\w+)"?\s*\((.*?)\n\);', re.S)
_ALTER = re.compile(r'ALTER TABLE (?:ONLY )?(?:"?public"?\.)?"?(\w+)"?(.*?);', re.S)
_NOT_COLUMNS = {"constraint", "primary", "unique", "check", "foreign", "exclude"}
_CALL = re.compile(
    r'(?:\.select|\.select_one|\.update|\.update_counting|\.delete|\bcount|\b_scan)\(\s*(?:sb,\s*)?"/?(\w+)"'
    r'|\.request\(\s*"\w+",\s*"/(\w+)"'
)
_FILTER = re.compile(
    r'"([a-z_]+)":\s*f?"(?:eq|neq|gt|gte|lt|lte|in|is|not|like|ilike|cs|cd|ov|fts)\.'
)
#: PostgREST's own query parameters, which look like filters but are not columns.
_RESERVED = {"select", "order", "limit", "offset", "and", "or", "on_conflict", "columns", "not"}


def _schema() -> dict[str, set[str]]:
    columns: dict[str, set[str]] = {}
    for migration in sorted(MIGRATIONS.glob("*.sql")):
        sql = migration.read_text(encoding="utf-8")
        for table, body in _CREATE.findall(sql):
            columns.setdefault(table, set()).update(
                c for c in re.findall(r'^\s+"?([a-z_]+)"?\s', body, re.M) if c not in _NOT_COLUMNS
            )
        for table, body in _ALTER.findall(sql):
            if table not in columns:
                continue
            columns[table].update(re.findall(r'ADD COLUMN (?:IF NOT EXISTS )?"?(\w+)', body))
            for dropped in re.findall(r'DROP COLUMN (?:IF EXISTS )?"?(\w+)', body):
                columns[table].discard(dropped)
    return columns


def _call_arguments(text: str, start: int) -> str:
    """The text of one call's arguments, up to its balancing close paren."""
    depth, i = 1, start
    while i < len(text) and depth:
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
    return text[start:i]


def test_the_migrations_parse_into_a_schema():
    schema = _schema()
    # Guards the guard: if the parser silently stopped understanding the migrations, every
    # lookup below would be skipped and the real test would pass vacuously.
    assert {"leads", "opportunities", "users", "calls", "organization_subscriptions"} <= schema.keys()
    assert "role" not in schema["users"] and "role_id" in schema["users"]
    assert "stage" in schema["opportunities"] and "stage" not in schema["leads"]


def test_every_filter_names_an_existing_column():
    schema = _schema()
    problems = []
    for source in SOURCES:
        for path in source.rglob("*.py"):
            if {".venv", "tests", "__pycache__"} & set(path.parts):
                continue
            text = path.read_text(encoding="utf-8")
            for call in _CALL.finditer(text):
                table = call.group(1) or call.group(2)
                if table not in schema:
                    continue
                for key in _FILTER.findall(_call_arguments(text, call.end())):
                    if key not in _RESERVED and key not in schema[table]:
                        line = text.count("\n", 0, call.start()) + 1
                        problems.append(f"{path.relative_to(ROOT)}:{line} filters {table}.{key}")
    assert problems == [], "filters on columns that do not exist:\n" + "\n".join(problems)
