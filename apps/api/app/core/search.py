"""Building PostgREST filter values out of user-supplied search text.

Three endpoints grew their own version of this and drifted apart: leads stripped ``*%(),``,
contacts stripped ``*%,`` and companies stripped only ``*%``. All three were safe in practice
-- PostgREST parses a filter as ``column.operator.value`` and treats what follows as literal,
so an injected clause lands inside the LIKE pattern and simply matches nothing -- but three
implementations of one rule is three chances for the next one to be wrong, and the weakest of
them was the one feeding an ``or=(...)`` group, where commas and parentheses really are
structural.

This is the single version. It strips rather than escapes: these are search boxes, PostgREST's
quoting rules differ between a bare filter and an ``or=`` group, and a dropped bracket in a
name search is a better outcome than a subtly wrong escape.
"""

from __future__ import annotations

#: Characters that mean something to PostgREST's filter grammar, so they never reach it:
#:   * and %   LIKE wildcards -- a bare "%" would otherwise match every row
#:   ( ) ,     group and separator syntax inside or=(...) / in.(...)
#:   " \\       value quoting and its escape
#:   :         used by PostgREST for casts (e.g. ::text)
_STRUCTURAL = set('*%(),"\\:')

#: Long enough for any real name, short enough that the pattern cannot be used to push an
#: expensive scan or a very large query string.
_MAX_TERM = 200


def sanitize_term(term: str | None) -> str:
    """Strip the characters that would change how PostgREST parses a filter."""
    if not term:
        return ""
    return "".join(c for c in term.strip() if c not in _STRUCTURAL)[:_MAX_TERM]


def contains_pattern(term: str | None) -> str:
    """``"acme"`` -> ``"*acme*"``, for use as the value of an ``ilike`` filter.

    Returns an empty string when nothing usable survives sanitising, which callers should treat
    as "no search was given" rather than as "match everything" -- a search of ``%`` must not
    silently turn into an unfiltered list.
    """
    cleaned = sanitize_term(term)
    return f"*{cleaned}*" if cleaned else ""
