"""One sanitiser for every search filter.

Three endpoints previously each had their own version and had drifted: leads stripped
``*%(),``, contacts stripped ``*%,`` and companies stripped only ``*%``. None was exploitable
-- PostgREST reads what follows ``column.operator.`` as a literal value, so an injected clause
ends up inside the LIKE pattern and matches nothing -- but the weakest of them fed an
``or=(...)`` group, where commas and parentheses genuinely are structural.
"""

from __future__ import annotations

import pytest

from app.core.config import API_V1_PREFIX as V1
from app.core.search import contains_pattern, sanitize_term
from tests.conftest import FakeResult

ROLE = {"id": "role-1", "name": "Admin", "grants_full_access": True, "role_permissions": []}


def as_user(fake_db, test_user):
    fake_db.responses["GET users"] = FakeResult(
        [{"id": test_user.sub, "role_id": ROLE["id"], "is_active": True, "roles": ROLE, "organization_id": "org-1"}]
    )


@pytest.mark.parametrize("char", ["*", "%", "(", ")", ",", '"', "\\", ":"])
def test_every_structural_character_is_removed(char):
    assert char not in sanitize_term(f"ac{char}me")


def test_a_bare_wildcard_does_not_become_match_everything():
    """"%" alone must not turn a search into an unfiltered list -- it sanitises to nothing, and
    callers treat empty as "no search given"."""
    assert contains_pattern("%") == ""
    assert contains_pattern("***") == ""
    assert contains_pattern("   ") == ""


def test_an_ordinary_term_is_wrapped_for_contains_matching():
    assert contains_pattern("Acme") == "*Acme*"
    assert contains_pattern("  Acme  ") == "*Acme*"


def test_characters_that_appear_in_real_names_survive():
    """Over-stripping is its own bug: these are the characters a search box actually sees."""
    assert contains_pattern("O'Brien & Sons-Ltd. #2") == "*O'Brien & Sons-Ltd. #2*"
    assert contains_pattern("priya@northwind.example") == "*priya@northwind.example*"


def test_the_term_is_length_capped():
    assert len(sanitize_term("a" * 5000)) == 200


@pytest.mark.parametrize(
    "resource,table",
    [("contacts", "contacts"), ("companies", "companies"), ("leads", "leads")],
)
def test_no_endpoint_passes_raw_search_text_into_a_filter(
    authed_client, fake_db, test_user, resource, table
):
    as_user(fake_db, test_user)
    fake_db.responses[f"GET {table}"] = FakeResult([], count=0)

    payload = 'x*%(),"\\:'
    response = authed_client.get(f"{V1}/{resource}", params={"search": payload})

    assert response.status_code == 200
    params = [c for c in fake_db.calls if c[0] == "GET" and c[1] == table][0][2]["params"]
    filters = " ".join(v for k, v in params.items() if k not in {"select", "order", "limit", "offset"})

    # An endpoint may use parentheses and commas of its own -- contacts builds an or= group --
    # so the property under test is about the *value*: the sanitised pattern is what got
    # embedded, and nothing resembling the raw payload survived.
    assert contains_pattern(payload) in filters
    assert payload not in filters
    assert "ilike.*x*" in filters


def test_the_contacts_or_group_stays_well_formed(authed_client, fake_db, test_user):
    """This is the case that mattered: an unbalanced parenthesis or a stray comma here changes
    which columns are searched, not just what is matched."""
    as_user(fake_db, test_user)
    fake_db.responses["GET contacts"] = FakeResult([], count=0)

    authed_client.get(f"{V1}/contacts", params={"search": "a),email.ilike.*b"})

    params = [c for c in fake_db.calls if c[0] == "GET" and c[1] == "contacts"][0][2]["params"]
    assert params["or"] == "(full_name.ilike.*aemail.ilike.b*,email.ilike.*aemail.ilike.b*)"
    assert params["or"].count("(") == 1 and params["or"].count(")") == 1
