"""Turning raw UTM parameters into the channel a human recognises.

Ad platforms are not consistent about what they put in ``utm_source``: the same Meta click can
arrive as ``facebook``, ``fb``, ``ig`` or ``instagram`` depending on which placement and which
template the campaign was built from. Grouping on the raw value spreads one channel across four
cards, so both this module and its TypeScript mirror in ``apps/web/lib/attribution.ts``
normalise before grouping.

Nothing here rewrites what was stored. ``contacts.utm_*`` keeps exactly what the click carried,
because that is the only version that can be reconciled against the ad platform's own reporting
later; normalisation happens on the way out.
"""

from __future__ import annotations

from app.domain.enums import LeadSource

#: Raw utm_source -> the platform it means. Keys are lowercased before lookup.
_PLATFORM_ALIASES: dict[str, str] = {
    "facebook": "Meta",
    "fb": "Meta",
    "meta": "Meta",
    "instagram": "Meta",
    "ig": "Meta",
    "linkedin": "LinkedIn",
    "li": "LinkedIn",
    "google": "Google",
    "adwords": "Google",
    "googleads": "Google",
    "bing": "Microsoft",
    "microsoft": "Microsoft",
    "twitter": "X",
    "x": "X",
    "reddit": "Reddit",
    "youtube": "YouTube",
    "tiktok": "TikTok",
}

#: utm_medium values that mean somebody paid for the click.
_PAID_MEDIUMS = frozenset(
    {"cpc", "ppc", "paid", "paidsocial", "paid_social", "paid-social", "display", "cpm", "ads"}
)

#: utm_medium values that mean a person recommended it rather than an ad buying the click.
_REFERRAL_MEDIUMS = frozenset({"referral", "partner", "affiliate"})


def _clean(value: str | None) -> str:
    return (value or "").strip().lower()


def platform_label(utm_source: str | None) -> str | None:
    """"facebook" -> "Meta". Unknown sources are title-cased rather than dropped."""
    cleaned = _clean(utm_source)
    if not cleaned:
        return None
    return _PLATFORM_ALIASES.get(cleaned, cleaned.replace("_", " ").replace("-", " ").title())


def is_paid(utm_medium: str | None) -> bool:
    return _clean(utm_medium) in _PAID_MEDIUMS


def channel_label(utm_source: str | None, utm_medium: str | None, source: str | None = None) -> str:
    """The channel shown on a card: "Meta Ads", "LinkedIn", "Referral", "Direct".

    Falls back to the coarse ``contacts.source`` enum for contacts entered by hand, which have
    no UTM parameters at all, and finally to "Direct".
    """
    platform = platform_label(utm_source)
    if platform:
        return f"{platform} Ads" if is_paid(utm_medium) else platform

    medium = _clean(utm_medium)
    if medium in _REFERRAL_MEDIUMS:
        return "Referral"
    if medium == "email":
        return "Email"

    if source:
        return source.replace("_", " ").title()
    return "Direct"


def derive_lead_source(utm_source: str | None, utm_medium: str | None) -> LeadSource:
    """Map attribution onto the coarse ``lead_source`` enum.

    The enum predates this and has no ad-specific values, so a paid Meta click and an organic
    Facebook visit both land on ``website`` -- the UTM columns are what tell them apart. Adding
    enum values instead would have meant an ``ALTER TYPE`` on a type already referenced by two
    tables, for a distinction the UTM columns already carry more precisely.
    """
    platform = platform_label(utm_source)
    if platform == "LinkedIn":
        return LeadSource.LINKEDIN
    if _clean(utm_medium) in _REFERRAL_MEDIUMS:
        return LeadSource.REFERRAL
    if platform or _clean(utm_medium):
        return LeadSource.WEBSITE
    return LeadSource.OTHER
