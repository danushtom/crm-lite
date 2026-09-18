"""Web research: what leaves the product, and what is allowed back in.

Outbound, only a company's name and public domain may reach the search provider. Inbound, web
text is untrusted: a claim survives only if it cites a source the model was actually given, and
enumerations and URLs are validated in code rather than trusted to the prompt.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from dracara_ai import search as web
from dracara_ai.config import ai_settings
from dracara_ai.graphs import research
from dracara_ai.usage import UsageRecord


# --- Outbound: domain normalisation ---------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://www.acme.io/about?x=1", "acme.io"),
        ("acme.io", "acme.io"),
        ("  HTTP://Sub.Acme.co.in/  ", "sub.acme.co.in"),
        ("localhost", None),
        ("http://127.0.0.1:8000", None),
        ("http://[::1]/", None),
        ("intranet.local", None),
        ("not a website", None),
        ("", None),
        (None, None),
    ],
)
def test_a_website_becomes_a_bare_public_domain_or_nothing(raw, expected):
    assert web.normalise_domain(raw) == expected


# --- Outbound: nothing but public identifiers ------------------------------------


def test_queries_are_built_from_the_name_and_domain_alone():
    """The query builder takes two strings. There is no parameter through which CRM content --
    notes, deal values, contact details -- could be passed to the search provider."""
    import inspect

    assert list(inspect.signature(web.company_queries).parameters) == ["company_name", "domain"]


def test_every_query_mentions_only_the_company():
    queries = web.company_queries("Acme Robotics", "acme.io")
    allowed_keys = {"query", "category", "numResults", "includeDomains"}
    for q in queries:
        assert set(q) <= allowed_keys
        assert "Acme Robotics" in q["query"]


@pytest.mark.asyncio
async def test_the_request_sent_to_exa_carries_only_the_query_and_search_options(monkeypatch):
    sent: dict = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "results": [
                    {"title": "Acme", "url": "https://acme.io/about", "text": "Acme builds robots."},
                    {"title": "bad", "url": "javascript:alert(1)", "text": "x"},
                ],
                "costDollars": {"total": 0.005},
            }

    class FakeClient:
        async def post(self, url, *, headers, json):
            sent.update(url=url, headers=headers, body=json)
            return FakeResponse()

    monkeypatch.setattr(ai_settings, "exa_api_key", "exa-test")
    monkeypatch.setattr(web, "get_http_client", lambda: FakeClient())

    usage = UsageRecord(feature="t", model="gpt-4o-mini")
    results = await web.search(web.company_queries("Acme", "acme.io")[0], usage=usage)

    assert sent["url"].endswith("/search")
    assert sent["headers"]["x-api-key"] == "exa-test"
    assert set(sent["body"]) <= {"query", "category", "numResults", "includeDomains", "type", "contents"}
    # Non-http(s) URLs from the provider are dropped, never shown as a clickable source.
    assert [r.url for r in results] == ["https://acme.io/about"]
    # Search is billed in dollars, and that cost is attributed rather than lost.
    assert usage.extra_cost_usd == pytest.approx(0.005)


@pytest.mark.asyncio
async def test_search_refuses_to_run_without_a_key(monkeypatch):
    from dracara_ai.errors import AiNotConfiguredError

    monkeypatch.setattr(ai_settings, "exa_api_key", "")
    with pytest.raises(AiNotConfiguredError):
        await web.search({"query": "Acme"})


# --- Inbound: citations are verified, not trusted ---------------------------------


def _results(n: int = 2) -> list[web.WebResult]:
    return [web.WebResult(title=f"S{i}", url=f"https://s{i}.example/page", text="...") for i in range(1, n + 1)]


def test_a_claim_citing_a_source_that_was_never_retrieved_is_dropped():
    raw = research._Profile(
        industry=research._CitedText(value="Robotics", source=1),
        location=research._CitedText(value="Pune, India", source=7),  # there is no source 7
    )
    profile = research.verify_citations(raw, _results(2))

    assert profile.industry.value == "Robotics"
    assert profile.industry.source_url == "https://s1.example/page"
    assert profile.location is None


def test_enumerations_are_enforced_in_code():
    raw = research._Profile(
        size=research._CitedText(value="about 40 people", source=1),
        segment=research._CitedText(value="Enterprise", source=1),
    )
    profile = research.verify_citations(raw, _results(1))

    assert profile.size is None  # not one of the allowed bands
    assert profile.segment.value == "enterprise"


def test_only_a_real_linkedin_url_can_become_a_suggested_link():
    """A page that talks the model into 'the LinkedIn is https://evil.example' must not get that
    link planted on a record."""
    bad = research.verify_citations(
        research._Profile(linkedin_url=research._CitedText(value="https://evil.example/in/acme", source=1)),
        _results(1),
    )
    good = research.verify_citations(
        research._Profile(linkedin_url=research._CitedText(value="https://www.linkedin.com/company/acme", source=1)),
        _results(1),
    )
    assert bad.linkedin_url is None
    assert good.linkedin_url.value == "https://www.linkedin.com/company/acme"


def test_news_and_signals_are_capped_and_verified():
    raw = research._Profile(
        recent_news=[research._CitedText(value=f"item {i}", source=1) for i in range(9)]
        + [research._CitedText(value="invented", source=99)],
    )
    profile = research.verify_citations(raw, _results(1))
    assert len(profile.recent_news) == 5
    assert all(n.source_url == "https://s1.example/page" for n in profile.recent_news)


def test_a_suspicious_source_is_surfaced_not_hidden():
    profile = research.verify_citations(research._Profile(suspicious_content=True), _results(1))
    assert profile.suspicious_content is True


# --- The cost gate ----------------------------------------------------------------


def test_no_search_results_means_no_model_call(monkeypatch):
    """No OpenAI key is configured in this run, so a model call would raise. Getting a profile
    back proves the graph ended at the gate."""

    async def empty(_request, **_kwargs):
        return []

    monkeypatch.setattr(web, "search", empty)
    profile, usage = asyncio.run(research.research_company(company_name="Nobody Ltd", website=None))

    assert profile.note
    assert profile.sources == []
    assert usage.total_tokens == 0


def test_one_failed_query_does_not_sink_the_others(monkeypatch):
    calls = {"n": 0}

    async def flaky(request, **_kwargs):
        calls["n"] += 1
        if request.get("category") == "news":
            raise RuntimeError("provider hiccup")
        return []

    monkeypatch.setattr(web, "search", flaky)
    profile, _ = asyncio.run(research.research_company(company_name="Acme", website="acme.io"))

    assert calls["n"] == 3
    assert profile.note  # nothing found, but no exception escaped


def test_research_requires_a_company_name():
    with pytest.raises(ValueError):
        asyncio.run(research.research_company(company_name="  ", website=None))


# --- The brief separates trusted and untrusted input ------------------------------


def test_the_brief_prompt_labels_crm_facts_and_fences_web_research():
    data = research.BriefInput(
        company_name="Acme",
        stage="negotiation",
        research=research.CompanyProfile(
            industry=research.CitedFact(value="Robotics", source_url="https://s1.example/page"),
            sources=[research.Source(index=1, title="S1", url="https://s1.example/page")],
        ),
    )
    rendered = research._render_brief_input(data)

    assert "CRM FACTS (trusted)" in rendered
    assert "<<<RESEARCH" in rendered and "RESEARCH>>>" in rendered
    # Web-derived text sits inside the fence, after the trusted block.
    assert rendered.index("Robotics") > rendered.index("<<<RESEARCH")


def test_the_research_graph_compiles():
    assert research.build_graph() is not None


def test_profiles_round_trip_through_json_storage():
    """Profiles are stored as JSONB and re-validated on read; a shape change that broke that
    would make every stored profile unreadable."""
    profile = research.verify_citations(
        research._Profile(industry=research._CitedText(value="Robotics", source=1)), _results(1)
    )
    restored = research.CompanyProfile.model_validate(json.loads(profile.model_dump_json()))
    assert restored == profile
