"""Text normalization, sentence windows, and quote verification.

Every fact the app shows is backed by a quote. A quote is only accepted if it
appears, after light normalization, as an exact substring of the source text.
This module is the single place that decides what "appears in the source" means.
"""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_TRANSLATE = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'", "‛": "'",
        "“": '"', "”": '"', "„": '"',
        "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
        " ": " ", " ": " ", " ": " ",
    }
)


def normalize(s: str) -> str:
    """Unicode-normalize, unify quotes/dashes, collapse whitespace.

    Applied identically to source text and candidate quotes, so a quote that
    differs from the source only by line breaks or curly quotes still verifies,
    while any change to the words themselves does not.
    """
    s = unicodedata.normalize("NFKC", s or "").translate(_TRANSLATE)
    return _WS.sub(" ", s).strip()


def verify(quote: str, source: str) -> tuple[bool, int, int]:
    """Is `quote` an exact substring of `source` after normalization?

    Returns (ok, start, end) with offsets into normalize(source), so the UI can
    highlight the exact span. Case-sensitive on purpose: a quote is a quote.
    """
    q, src = normalize(quote), normalize(source)
    if not q:
        return False, -1, -1
    i = src.find(q)
    return (i >= 0, i, i + len(q) if i >= 0 else -1)


# Abbreviations that end in a period but do not end a sentence.
_ABBREV = re.compile(
    r"(?:\b(?:Inc|Co|Corp|Ltd|LLC|L\.L\.C|L\.P|Mr|Mrs|Ms|Dr|St|No|Nos|Jr|Sr|vs|approx|Dept|U\.S|i\.e|e\.g|etc|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)|\b[A-Z])\.$"
)


# After "Inc." etc., a capitalized sentence-starter means the sentence really did end.
_STARTER = re.compile(r" (?:The|This|These|That|It|Its|Staff|Funding|Funds|Approval|Under|In|On|If|All|A|An|Council|City|We|They|Work|Services|Payment|Pricing|Prices|Per|Pursuant|Additionally|Further|Bids|Proposals)\b")


def _boundary(text: str, i: int) -> bool:
    """Is text[i] ('.' or ';') the end of a sentence?"""
    if text[i] not in ".;":
        return False
    if i + 1 < len(text) and text[i + 1] != " ":
        return False
    if text[i] == ";":
        return True
    if _ABBREV.search(text[max(0, i - 7):i + 1]):
        return bool(_STARTER.match(text, i + 1))
    return True


def sentence_around(text: str, start: int, end: int, max_len: int = 360) -> tuple[int, int]:
    """Expand [start, end) in `text` to the enclosing sentence, capped at max_len.

    Works on already-normalized text. Sentence boundaries are '. ', '; ' or
    ': ' runs that are not abbreviations, plus 'RESOLVED' / 'WHEREAS' clause starts,
    which is how council resolutions are actually structured.
    """
    lo = start
    while lo > 0:
        if _boundary(text, lo - 1):
            break
        # Legistar marks sections with "..Title", "..Memorandum", "..Body": treat as a break.
        if text[lo - 2:lo] == ".." and lo < start:
            break
        if text.startswith(("RESOLVED", "WHEREAS", "Whereas", "Resolved"), lo) and lo < start:
            break
        lo -= 1
    hi = end
    while hi < len(text):
        if text.startswith(" ..", hi) or (text.startswith("..", hi) and hi > end and text[hi - 1] != "."):
            break
        if _boundary(text, hi):
            hi += 1
            break
        hi += 1
    lo = len(text[:lo]) - len(text[:lo].lstrip()) if lo == 0 else lo
    while lo < start and text[lo] == " ":
        lo += 1
    # Cap length, keeping the matched span visible.
    if hi - lo > max_len:
        pad = max(0, (max_len - (end - start)) // 2)
        lo = max(lo, start - pad)
        hi = min(hi, end + pad)
        # Don't cut words in half.
        while lo > 0 and lo < start and text[lo - 1] != " ":
            lo += 1
        while hi < len(text) and hi > end and text[hi] != " ":
            hi -= 1
    return lo, hi


def context(text: str, start: int, end: int, pad: int = 280) -> dict:
    """A display window around a span: before / quote / after, for the evidence drawer."""
    lo, hi = max(0, start - pad), min(len(text), end + pad)
    while lo > 0 and text[lo - 1] != " ":
        lo -= 1
    while hi < len(text) and text[hi] != " ":
        hi += 1
    return {
        "before": ("… " if lo > 0 else "") + text[lo:start],
        "quote": text[start:end],
        "after": text[end:hi] + (" …" if hi < len(text) else ""),
    }
