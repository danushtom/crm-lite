"""Web search via Exa, for company research and pre-call briefs.

Two rules, both about what crosses this module's boundary:

**Outbound: only public identifiers leave.** A query is built from a company's name and its web
domain -- things already public, and the only things a web search needs. CRM notes, deal values,
contact details and anything else a customer typed into this product never reach a third-party
search provider. Callers cannot pass free text through here by accident: :func:`company_queries`
builds the queries itself from those two fields, and nothing else in the product calls
:func:`search` directly.

**Inbound: everything that comes back is untrusted.** Result text is a stranger's web page. It is
handed to a model only as quoted data, inside a graph that has no tools and writes nothing, and
whatever it produces is shown to a person as a suggestion before it touches a record. See
``graphs/research.py``.
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from .config import ai_settings
from .errors import AiNotConfiguredError, AiUpstreamError
from .usage import UsageRecord

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None

#: Characters of page text kept per result. Enough for an About page or a news lede; small enough
#: that five results fit a prompt with room to spare.
DEFAULT_MAX_CHARS = 2_500


@dataclass(slots=True)
class WebResult:
    title: str
    url: str
    text: str
    published_date: str | None = None


def get_http_client() -> httpx.AsyncClient:
    """Module-level factory so tests can substitute a fake, matching ``client.py``."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(ai_settings.exa_timeout_seconds, connect=10.0))
    return _client


def reset_http_client() -> None:
    global _client
    _client = None


def is_configured() -> bool:
    return bool(ai_settings.is_configured and ai_settings.exa_api_key)


def normalise_domain(website: str | None) -> str | None:
    """Reduce a user-typed website to a bare public hostname, or None.

    The website field is free text. It is only ever used as an Exa domain filter -- this product
    never fetches it itself, so there is no SSRF surface -- but a filter of ``localhost`` or an IP
    address is meaningless at best, and rejecting it here keeps junk out of the query.
    """
    if not website:
        return None
    raw = website.strip()
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        host = (urlsplit(raw).hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host or len(host) > 253 or host.endswith((".local", ".internal", ".localhost")):
        return None
    try:
        ipaddress.ip_address(host)
        return None  # An IP address is not a company's domain.
    except ValueError:
        pass
    if not all(part and len(part) <= 63 for part in host.split(".")):
        return None
    return host


def company_queries(company_name: str, domain: str | None) -> list[dict[str, Any]]:
    """The only queries this product sends to a search provider, built from public identifiers.

    Deliberately takes two strings and nothing else, so there is no parameter through which a
    caller could pass CRM content along.
    """
    name = " ".join(company_name.split())[:120]
    queries: list[dict[str, Any]] = [
        {
            "query": f"{name} company overview: what they do, products, customers, team size, headquarters",
            "category": "company",
            "numResults": 4,
            **({"includeDomains": [domain]} if domain else {}),
        },
        {
            "query": f"{name} recent news, funding, launches, hiring, partnerships",
            "category": "news",
            "numResults": 4,
        },
    ]
    if domain:
        # Independent coverage too, not just the company's own marketing copy.
        queries.append({"query": f"{name} ({domain})", "numResults": 3})
    return queries


async def search(
    request: dict[str, Any],
    *,
    usage: UsageRecord | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[WebResult]:
    """Run one Exa search. ``request`` must come from :func:`company_queries`."""
    if not ai_settings.exa_api_key:
        raise AiNotConfiguredError("Web research requires EXA_API_KEY")

    body = {**request, "type": "auto", "contents": {"text": {"maxCharacters": max_chars}}}
    try:
        response = await get_http_client().post(
            f"{ai_settings.exa_api_base.rstrip('/')}/search",
            headers={"x-api-key": ai_settings.exa_api_key, "Content-Type": "application/json"},
            json=body,
        )
    except httpx.HTTPError as exc:
        raise AiUpstreamError("Could not reach the web search provider") from exc

    if response.status_code >= 400:
        # The body can echo the query back; log the status only.
        logger.error("exa_search_error status=%s", response.status_code)
        raise AiUpstreamError("The web search provider rejected the request")

    payload = response.json()
    if usage is not None:
        cost = (payload.get("costDollars") or {}).get("total")
        if isinstance(cost, (int, float)):
            usage.extra_cost_usd += float(cost)

    results = []
    for item in payload.get("results") or []:
        url = str(item.get("url") or "")
        if not url.startswith(("https://", "http://")):
            continue
        results.append(
            WebResult(
                title=str(item.get("title") or "")[:300],
                url=url[:1000],
                text=str(item.get("text") or "")[:max_chars],
                published_date=item.get("publishedDate"),
            )
        )
    return results
