"""Splitting a document into retrievable chunks.

Deliberately simple: paragraph-aware, character-budgeted, with an overlap so a sentence spanning a
boundary is still findable from either side. The documents this handles are pricing sheets, FAQs
and call scripts -- short, structured, and already written in chunks by a human. A token-exact
splitter would add a tokenizer dependency to both the API and the worker to buy very little here.
"""

from __future__ import annotations

#: Roughly 200 tokens of English. Small enough that a retrieved chunk can be read aloud mid-call
#: without the agent losing the thread, large enough to keep a price table intact.
DEFAULT_CHUNK_CHARS = 800
DEFAULT_OVERLAP_CHARS = 120


def chunk_text(
    text: str,
    *,
    size: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_OVERLAP_CHARS,
) -> list[str]:
    """Split ``text`` into overlapping chunks, preferring paragraph then sentence boundaries."""
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")

    normalised = "\n".join(line.rstrip() for line in text.splitlines())
    normalised = normalised.strip()
    if not normalised:
        return []
    if len(normalised) <= size:
        return [normalised]

    chunks: list[str] = []
    start = 0
    length = len(normalised)

    while start < length:
        end = min(start + size, length)
        if end < length:
            # Prefer to break on a paragraph, then a sentence, then a space -- but only if the
            # boundary is in the last third of the window, so a document with no paragraph breaks
            # still advances instead of emitting tiny chunks.
            floor = start + (size * 2 // 3)
            for marker in ("\n\n", ". ", "\n", " "):
                found = normalised.rfind(marker, floor, end)
                if found != -1:
                    end = found + len(marker)
                    break

        chunk = normalised[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= length:
            break
        start = max(end - overlap, start + 1)

    return chunks
