"""Deterministic extraction: what we can read off a resolution title and memo with rules.

Rules come first because they are free, instant, and auditable. Every rule
returns the exact span it matched, so each extracted field carries a verbatim
quote. The LLM stage (clock/llm.py) only runs on what rules leave blank.

Ann Arbor titles are unusually informative. A typical one:

    Resolution to Approve a Sole Source Professional Services Agreement with
    Covalence Consulting Inc., for UKG Pro Support ... ($279,400.00) (8 Votes Required)

gives us the procurement route, contract type, vendor, scope and amount.
The memo text adds what titles leave out: term length, end dates, renewals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .text import normalize, sentence_around


@dataclass
class Hit:
    """One extracted value plus the exact span of text that supports it."""

    field: str
    value: object
    start: int  # offsets into the normalized source text
    end: int
    rule: str
    quote_start: int = -1  # wider sentence-level span shown as the quote
    quote_end: int = -1

    def with_sentence(self, text: str) -> "Hit":
        self.quote_start, self.quote_end = sentence_around(text, self.start, self.end)
        return self


# ---------------------------------------------------------------------------
# Titles
# ---------------------------------------------------------------------------

MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?(?!\d)")

ROUTE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("sole_source", re.compile(r"\bsole[- ]source\b", re.I)),
    ("emergency", re.compile(r"\bemergency (?:purchase|procurement|repair|contract)", re.I)),
    (
        "cooperative",
        re.compile(
            r"\b(?:MiDEAL|MI ?DEAL|Sourcewell|NASPO|ValuePoint|OMNIA|HGAC ?Buy|H-GAC|BuyBoard|E&I|GSA Schedule|GSA contract|"
            r"cooperative(?: purchasing| contract| agreement)?|piggyback|"
            r"State of Michigan (?:contract|bid)|(?:Washtenaw County|Oakland County) (?:contract|bid))\b",
            re.I,
        ),
    ),
    (
        "competitive",
        re.compile(
            r"\b(?:ITB|RFP|RFQ|IFB|Bid|Request for Proposals?|Invitation to Bid)\s*(?:No\.?|Number|#)\s*[\w-]+|"
            r"\b(?:ITB|RFP|RFQ|IFB)[-:]\s*\d+|"
            r"\blowest responsible bidder\b|\bcompetitive(?:ly)? (?:bid|selected|solicitation|process)",
            re.I,
        ),
    ),
]

KIND_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("amendment", re.compile(r"\bAmendment(?: No\.?)? ?\d*\b|\bamend(?:ing)? the\b.*\bagreement\b", re.I)),
    ("change_order", re.compile(r"\bchange order\b", re.I)),
    ("renewal", re.compile(r"\b(?:renew|renewal|extend|extension)\b", re.I)),
    ("construction", re.compile(r"\bconstruction (?:contract|agreement)\b", re.I)),
    ("professional_services", re.compile(r"\bprofessional services agreement\b", re.I)),
    ("purchase_order", re.compile(r"\bpurchase order\b|\bpurchase of\b|\bblanket purchase\b", re.I)),
    ("services", re.compile(r"\b(?:general |maintenance )?services? (?:agreement|contract)\b", re.I)),
    ("agreement", re.compile(r"\b(?:agreement|contract)\b", re.I)),
]

# The city receiving money, or council moving money: a "Budget Approved" signal, not a vendor contract.
FUNDING = re.compile(
    r"\b(?:appropriat\w+|accept(?:ance)? (?:of )?(?:a |an |the )?(?:\w+ ){0,4}grant|"
    r"bonds?\b|millage|increase the FY ?\d{2,4}|budget amendment)",
    re.I,
)

# Titles that mention money but are not purchases from a vendor.
NOT_A_PURCHASE = re.compile(
    r"\b(?:easement|street closing|PILOT|payment in lieu|brownfield|tax abatement|"
    r"rezoning|special assessment|fee schedule|donation|settlement|claim of|legal action|"
    r"franchise|grant funds|accept (?:and appropriate )?(?:a |an |the )?[\w$,. -]{0,60}grant|grant application|"
    r"memorandum of understanding|collective bargaining|labor agreement|interlocal|development agreement|"
    r"sub-?recipient|grant agreement|between the City of Ann Arbor and|drain(?:age)? (?:board|district))\b",
    re.I,
)

# ---------------------------------------------------------------------------
# Vendor names
# ---------------------------------------------------------------------------
# A title names its vendor in one of a handful of shapes. Each pattern below captures a candidate
# name; candidates are tried in order and the first that passes the checks wins:
#   "...Agreement with Acme, Inc. for ..."                 with
#   "...Purchase Order to Acme, Inc. for ..."              to
#   "...Agreement between Acme, Inc. and the City ..."     between
#   "Change Order No. 2 to the Contract with Acme ..."     late_with
#   "Award Construction Contracts for X to Acme ..."       award
#   "Purchasing Agreement for asphalt from Acme ..."       from
#   "Purchase Order for asphalt to Acme ..."               for_to

# Where a vendor name stops: the start of scope ("for ..."), an amount, a bid number, a parenthesis,
# a second clause ("and to appropriate"), or the vendor's home town ("of Lake Orion, Michigan").
_STOP = (
    r"(?=,?\s+(?:for|in the amount|in an amount|and appropriate|and to|and approve|and authorize|and establish|"
    r"and ratify|and the City|through|via|under|utilizing|not to exceed|not-to-exceed|establish|by and through|"
    r"dated|effective|to|relative to|related to|regarding|pertaining to|in connection with|as part of|and related|"
    r"approve|authorize|appropriate|accept|amend)\b"
    r"|,?\s+of\s+[A-Z][\w .]+,\s+(?:Michigan|MI|Ohio|Indiana|Illinois|Wisconsin)\b"
    r"|\s+from\s+\$|,?\s+-?\s*(?:RFP|ITB|RFQ|IFB|Bid|MiDEAL|MI Deal|Sourcewell|NASPO|OMNIA)\b|\s*[(;:]|\s*$)"
)
_V = r"(?P<v>[A-Z0-9][^;:()$]*?)" + _STOP
_NUM = r"(?:\s+(?:No\.?|Number|#)\s*\d+|\s+\d+(?:-\d+)?)?"
_NOUN = (r"(?:agreements?|contracts?|PSA|amendments?" + _NUM + r"|renewal" + _NUM + r"|change orders?" + _NUM +
         r"|purchase orders?" + _NUM + r"|orders?|extensions?|authorization|services contract)")

# Tried in order; within one pattern, every match is tried until one passes the checks.
VENDOR_PATTERNS = [
    ("between", re.compile(r"\bbetween\s+(?:the\s+)?" + _V.replace(_STOP, r"(?=\s+and\s+(?:the\s+)?City\b)"), re.I)),
    ("with", re.compile(r"\b" + _NOUN + r"\s+with\s+(?:the\s+)?" + _V, re.I)),
    ("to", re.compile(r"\b(?:contracts?|purchase orders?" + _NUM + r"|orders?)\s+to\s+(?:the\s+)?" + _V, re.I)),
    ("late_with", re.compile(r"\b" + _NOUN + r"\b[^$;]*?\bwith\s+(?:the\s+)?" + _V, re.I)),
    ("award", re.compile(r"\baward\w*\b[^$;]*?\bto\s+(?:the\s+)?" + _V, re.I)),
    ("from", re.compile(r"\b(?:purchas\w*|procurement|acquisition|rental|orders?)\b[^$;]*?\bfrom\s+(?:the\s+)?" + _V, re.I)),
    ("for_to", re.compile(r"\b(?:purchase orders?|orders?|contracts?)" + _NUM + r"\s+for\s+[^$;]*?\bto\s+(?:the\s+)?" + _V, re.I)),
]

# Public bodies: agreements with them are intergovernmental, not a vendor a seller competes with.
PUBLIC_BODY = re.compile(
    r"^(?:the\s+)?(?:[A-Z][a-z]+ County\b|County of|City of|Village of|Charter Township|[A-Z][a-z]+ Township|"
    r"State of Michigan|Michigan Department|Department of|MDOT|EGLE|Regents of|University of Michigan|"
    r"Eastern Michigan University|Washtenaw Community College|Downtown Development|Courts and Law Enforcement|"
    r"Ann Arbor (?:Public Schools|Housing Commission|Housing Development|Downtown|Area Transportation|District Library|"
    r"Ypsilanti Regional|/Ypsilanti SmartZone)|Ann Arbor/Ypsilanti SmartZone|Huron-Clinton|Michigan Economic Development|[\w -]*Regional Planning Commission|"
    r"[\w ]*(?:Drain(?:age)? (?:Board|District|Commission)|Water Resources Commissioner|Sheriff))",
)
_NOT_A_NAME = re.compile(
    r"^(?:Exceed|City|Council|Current|Previous|Original|Additional|Resolution|Purchase|Provide|Approve|Accept|Amend|Appropriate|Agreements?$|Contracts?$|"
    r"(?:\d+|two|three|four|five|six|seven|eight|nine|ten|several|multiple)\s+(?:firms|vendors|contractors|consultants|companies))\b",
    re.I,
)
_LTD = re.compile(r"\b(?:Inc|Co|Corp|Ltd|L\.L\.C|LLC|P\.C|L\.P|P\.L\.L\.C|Jr|Sr)\.$")


def clean(v: str) -> str:
    v = v.strip(" ,;-")
    if v.endswith(".") and not _LTD.search(v):
        v = v[:-1]
    return v


def acceptable(v: str) -> str | None:
    """None if fine, else the reason it isn't a vendor name."""
    if not v or len(v) > 120 or len(v) < 2:
        return "length"
    if _NOT_A_NAME.search(v):
        return "not a name"
    if v[0].isdigit() and not re.match(r"^\d+(?:st|nd|rd|th)?\s+[A-Za-z]", v):
        return "a number"
    if PUBLIC_BODY.search(v):
        return "public body"
    return None


def extract_vendor(t: str):
    """(vendor, start, end, rule) or (None, ..., reason) for a normalized title."""
    saw_public = None
    for name, pat in VENDOR_PATTERNS:
        for m in pat.finditer(t):
            v = clean(m.group("v"))
            why = acceptable(v)
            if why is None:
                s = m.start("v") + (len(m.group("v")) - len(m.group("v").lstrip(" ,;-")))
                return v, s, s + len(v), f"title.vendor.{name}"
            if why == "public body":
                saw_public = v
    return None, None, None, ("public body: " + saw_public) if saw_public else "no vendor"


_SUFFIX = re.compile(
    r"[,\s]+(?:L\.?L\.?C\.?|Inc\.?|Incorporated|Corp\.?|Corporation|Co\.?|Company|Ltd\.?|L\.?P\.?|"
    r"P\.?C\.?|P\.?L\.?L\.?C\.?|LLP)\b\.?",
    re.I,
)


def vendor_key(name: str) -> str:
    """Normalize a vendor name for grouping: 'RACM, L.L.C., D/B/A Servpro' -> 'servpro'.

    If a d/b/a is present, the trade name is what buyers and competitors know.
    """
    n = normalize(name)
    m = re.search(r"\bd/?b/?a\b\.?\s*(.+)", n, re.I)
    if m:
        n = m.group(1)
    n = re.sub(r"\s*\bf/?k/?a\b.*$", "", n, flags=re.I)  # "formerly known as" names an old entity
    n = _SUFFIX.sub("", n)
    n = re.sub(r"^the\s+", "", n, flags=re.I)
    n = re.sub(r"[^a-z0-9& ]+", " ", n.lower()).replace("&", " and ")
    n = re.sub(r"\s+", " ", n).strip()
    # Trailing legal forms and a state qualifier don't change who the company is:
    # "Detroit Salt Company, L.C." / "Detroit Salt Company LC" / "Tetra Tech of Michigan" group together.
    for _ in range(3):
        n = re.sub(r"\s+(?:l ?c|l ?l ?c|inc|co|company|corp|corporation|ltd|l ?p|p ?c|p ?l ?l ?c|of michigan)$", "", n)
    return n


def parse_money(s: str) -> float:
    m = MONEY.search(s)
    if not m:
        raise ValueError(s)
    whole = m.group(1).replace(",", "")
    return float(whole) + (float("0." + m.group(2)) if m.group(2) else 0.0)


def parse_title(title: str) -> list[Hit]:
    """Extract kind, route, vendor and amount from a resolution title."""
    t = normalize(title)
    hits: list[Hit] = []

    for kind, pat in KIND_PATTERNS:
        if m := pat.search(t):
            hits.append(Hit("kind", kind, m.start(), m.end(), f"title.kind.{kind}"))
            break

    for route, pat in ROUTE_PATTERNS:
        if m := pat.search(t):
            hits.append(Hit("route", route, m.start(), m.end(), f"title.route.{route}"))
            break

    v, vs, ve, vrule = extract_vendor(t)
    if v:
        hits.append(Hit("vendor", v, vs, ve, vrule))

    amounts = list(MONEY.finditer(t))
    if amounts:
        # "Increase ... from $25,000 to $70,000": the new ceiling is the last figure.
        total = re.search(r"\btotal(?: of| contract| amount| not to exceed)?[:\s]+(?:of\s+)?\$", t, re.I)
        if total:
            pick = next(m for m in amounts if m.start() >= total.end() - 1)
        elif re.search(r"\bincreas\w*\b.*\bfrom\b", t, re.I) and len(amounts) > 1:
            pick = amounts[-1]  # "from $25,000 to $70,000": the new ceiling
        else:
            pick = amounts[0]  # later figures in a title are usually project budgets or contingencies
        hits.append(Hit("amount", parse_money(pick.group(0)), pick.start(), pick.end(), "title.amount"))
        # What kind of number it is, read from the words around it: an annual figure, a ceiling, a total,
        # or an increase. Sums on the site mix these, so the evidence popover always says which.
        near = t[max(0, pick.start() - 60):pick.end() + 40]
        basis = ("annual" if re.search(r"\bannual(?:ly)?\b|per year|each year|/year", near, re.I)
                 else "total" if total or re.search(r"\btotal\b", near, re.I)
                 else "ceiling" if re.search(r"not[- ]to[- ]exceed|\bNTE\b|up to", near, re.I)
                 else "increase" if re.search(r"\bincrease\b|\badditional\b", near, re.I)
                 else "stated")
        hits.append(Hit("amount_basis", basis, pick.start(), pick.end(), f"title.amount_basis.{basis}"))

    for h in hits:
        h.quote_start, h.quote_end = 0, len(t)  # the whole title is the quote
    return hits


def is_intergovernmental(title: str) -> bool:
    """An agreement whose only counterparty is a public body (the county, MDOT, the DDA, U-M)."""
    v, _, _, why = extract_vendor(normalize(title))
    return v is None and why.startswith("public body")


def is_purchase(title: str, hits: list[Hit]) -> bool:
    t = normalize(title)
    if NOT_A_PURCHASE.search(t):
        return False
    fields = {h.field for h in hits}
    return "vendor" in fields and ("kind" in fields or "amount" in fields)


# Money moving that is not new money for a program.
NOT_FUNDING = re.compile(r"\b(?:easement|street closing|PILOT|payment in lieu|tax abatement|rezoning|special assessment|"
                         r"fee schedule|settlement|legal action|franchise)\b", re.I)


def is_funding(title: str) -> bool:
    t = normalize(title)
    return bool(FUNDING.search(t)) and not NOT_FUNDING.search(t)


# ---------------------------------------------------------------------------
# Memo / resolution text: terms, dates, renewals, procurement method
# ---------------------------------------------------------------------------

_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "eighteen": 18, "twenty-four": 24,
    "thirty-six": 36, "a": 1, "an": 1,
}
_NUM = r"(?P<n>\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|eighteen|twenty-four|thirty-six)(?:\s*\(\d+\))?"
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE = rf"(?P<d>(?:{_MONTHS})\.? \d{{1,2}},? \d{{4}}|\d{{1,2}}/\d{{1,2}}/\d{{4}})"


def _num(s: str) -> int:
    s = s.lower()
    return int(s) if s.isdigit() else _NUM_WORDS[s]


def parse_date(s: str) -> date | None:
    s = s.replace(".", "").replace(",", "")
    m = re.fullmatch(rf"({_MONTHS}) (\d{{4}})", s)
    if m:  # month and year only: the last day of that month
        import calendar

        month = _MONTHS.split("|").index(m.group(1)) + 1
        year = int(m.group(2))
        return date(year, month, calendar.monthrange(year, month)[1])
    m = re.match(rf"({_MONTHS}) (\d{{1,2}}) (\d{{4}})", s)
    if m:
        month = _MONTHS.split("|").index(m.group(1)) + 1
        try:
            return date(int(m.group(3)), month, int(m.group(2)))
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    return None


# Order matters: more specific patterns first.
TERM_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("term_years", re.compile(rf"\b(?:term|period|duration) of {_NUM}[- ]years?\b", re.I)),
    ("term_months", re.compile(rf"\b(?:term|period|duration) of {_NUM}[- ]months?\b", re.I)),
    ("term_years", re.compile(rf"\b{_NUM}[- ]year (?:agreement|contract|term|period|service agreement|professional services agreement|lease)\b", re.I)),
    # "The term of the proposed contract with Acme, Inc. is for two-years and up to $170,000.00"
    ("term_years", re.compile(rf"\bterm of (?:the|this) (?:proposed )?(?:contract|agreement|purchase order)\b[^;]{{0,160}}?\b(?:is|shall be|will be)\s+(?:for\s+)?{_NUM}[- ](?:\(\d+\)\s*)?years?\b", re.I)),
    # "a Two (2) Year General Services Agreement", "a two-year general services contract"
    ("term_years", re.compile(rf"\b{_NUM}[- ](?:\(\d+\)\s*)?year(?:[\s-]+(?:general|professional|services?|purchas\w+|maintenance|support|best|source|sole|on-call|as-needed))+[\s-]+(?:agreement|contract|purchase order|PSA)\b", re.I)),
    ("term_years", re.compile(rf"\bover the (?:course of the )?next {_NUM} (?:\(\d+\) )?years\b", re.I)),
    ("term_months", re.compile(rf"\b{_NUM}[- ]month (?:agreement|contract|term|period)\b", re.I)),
    ("term_years_loose", re.compile(rf"\bfor (?:a period of )?{_NUM} (?:\(\d+\) )?years?\b", re.I)),
]

_MONTH_YEAR = rf"(?P<d>(?:{_MONTHS}),? \d{{4}})(?![\d,])"

END_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("end_date", re.compile(rf"\b(?:expir\w*|terminat\w*|ending|ends?|through|until|thru)\s+(?:on\s+)?{_DATE}", re.I)),
    # "ongoing support ... through July 2029": no day given, so the month's last day.
    ("end_month", re.compile(rf"\b(?:expir\w*|ending|ends?|through|until|thru)\s+(?:the end of\s+)?{_MONTH_YEAR}", re.I)),
    ("end_date", re.compile(rf"\b{_DATE}\s+(?:expiration|end) date\b", re.I)),
]

START_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("start_date", re.compile(rf"\b(?:effective|commenc\w*|beginning|begin\w*|starting|start\w*|from)\s+(?:on\s+)?{_DATE}", re.I)),
]

# "Prices are firm through May 10, 2023" is a pricing deadline, not a contract end.
_NOT_CONTRACT_END = re.compile(r"(?:pric\w*|firm|bids?|quotes?|warrant\w*|valid|good)\W+(?:\w+\W+){0,3}$", re.I)

RENEWAL = re.compile(
    rf"\b(?:option|options|ability|right)\s+(?:of |for |to )?(?:renew\w* )?(?:for )?(?:up to )?{_NUM}\s+"
    rf"(?:additional\s+)?(?P<len>one|two|three|1|2|3|\d+)?[- ]?(?:\(\d+\)\s*)?(?P<unit>year|month)s?\b",
    re.I,
)
# "authorized to renew the purchase order for up to three one-year periods"
RENEWAL_FOR = re.compile(
    rf"\b(?:renew|extend)\w*\b[^.;]{{0,80}}?\bfor (?:up to\s+)?{_NUM}\s+(?:\(\d+\)\s*)?(?:additional\s+)?(?P<len>one|two|three|1|2|3)?[- ]?(?:\(\d+\)\s*)?(?P<unit>year|month)\s+(?:periods?|terms?)\b",
    re.I,
)
RENEWAL_ALT = re.compile(
    rf"\b{_NUM},?\s+(?:\(\d+\)\s*)?(?:additional\s+|optional\s+|remaining\s+)?(?P<len>one|two|three|1|2|3)?[- ]?(?:\(\d+\)\s*)?(?P<unit>year|month)\s+(?:renewal|extension|option|term|period)s?\b",
    re.I,
)
_CONTRACT_SENTENCE = re.compile(r"\b(?:agreement|contract|purchase order|services|lease)\b", re.I)
_CIP = re.compile(r"Capital Improvements? (?:Plan|Program)|\bCIP\b", re.I)

# "N one-year terms" only means renewals when the sentence talks about extending or renewing.
_RENEW_CONTEXT = re.compile(r"renew|extend|extension|option", re.I)

FY_RANGE = re.compile(
    r"\b(?:FY ?|Fiscal Years? )(?P<a>20\d{2}|\d{2})\s*(?:-|–|through|to|thru|and(?: in)?)\s*(?:FY ?|Fiscal Year )?(?P<b>20\d{2}|\d{2})\b",
    re.I,
)

# "Design work for this project is expected to extend through 2027": a year, no day.
END_YEAR = re.compile(r"\b(?:expected|scheduled|anticipated|planned) to (?:extend|continue|run|last|be completed)\w* (?:through|until|by) (?:the end of )?(?P<y>20\d\d)\b", re.I)
# "The bid prices are firm through April 25, 2027": not the contract's end, but when the city needs new
# prices. Used only as a last resort for supply orders, and labeled as exactly that.
PRICES_UNTIL = re.compile(r"\b(?:bid )?pric(?:es|ing) (?:are|is|shall be|will be|remain)? ?firm (?:for a duration )?(?:through|until) (?P<d>(?:January|February|March|April|May|June|July|August|September|October|November|December)\.? \d{1,2},? \d{4})", re.I)

TEXT_ROUTE: list[tuple[str, re.Pattern]] = [
    ("sole_source", re.compile(r"\bsole[- ]source\b", re.I)),
    ("cooperative", ROUTE_PATTERNS[2][1]),
    (
        "competitive",
        re.compile(
            r"\b(?:Request for Proposals?|Invitation to Bid|Request for Qualifications|RFP|ITB|RFQ)\b\)?\s*(?:No\.?|#|Number|:|-)?\s*\d+|"
            r"\b(?:bids|proposals) (?:were|was) (?:received|opened|solicited)\b|\blowest responsible bidder\b|"
            # "Of the six proposals received", "issued a request for proposal", "sent an invitation to bid to ... and
            # other providers". Not "a new RFP can be advertised" or "explore an updated RFP", which are about the future.
            r"\b(?:\w+ )?(?:proposals|bids) received\b|"
            r"\b(?:issued|released|sent) (?:an? )?(?:Request for Proposals?|Invitation to Bid|Request for Qualifications|RFP|ITB|RFQ)\b|"
            r"\bcompetitive (?:bid|selection|process|solicitation)\b",
            re.I,
        ),
    ),
]


def parse_text(text_plain: str) -> list[Hit]:
    """Extract term, start, end, renewal options and procurement route from memo text.

    Returns at most one hit per field: the first match in document order, since
    the memo states the deal before it discusses alternatives or history.
    """
    t = normalize(text_plain)
    hits: list[Hit] = []

    def first(field: str, pats: list[tuple[str, re.Pattern]], conv) -> None:
        best: tuple[int, Hit] | None = None
        for name, pat in pats:
            for m in pat.finditer(t):
                try:
                    val = conv(name, m)
                except (KeyError, ValueError):
                    continue
                if val is None:
                    continue  # this match was vetoed; keep looking further down the document
                if best is None or m.start() < best[0]:
                    best = (m.start(), Hit(field, val, m.start(), m.end(), f"text.{name}"))
                break
        if best:
            hits.append(best[1].with_sentence(t))

    def term(name: str, m: re.Match):
        if name == "term_years_loose":
            # "for two years" counts only in a sentence about this agreement, not "for over three years, staff..."
            lo, hi = sentence_around(t, m.start(), m.end())
            if not _CONTRACT_SENTENCE.search(t[lo:hi]) or re.search(r"\b(?:over|past|last|prior)\s*$", t[max(0, m.start() - 12):m.start()], re.I):
                return None
        n = _num(m.group("n"))
        months = n * 12 if name.startswith("term_years") else n
        return months if 1 <= months <= 120 else None

    first("term_months", TERM_PATTERNS, term)

    def dated(name: str, m: re.Match):
        if name == "end_date" and _NOT_CONTRACT_END.search(t[max(0, m.start() - 40):m.start()]):
            return None
        d = parse_date(m.group("d"))
        return d.isoformat() if d and 2000 <= d.year <= 2045 else None

    first("end_date", END_PATTERNS, dated)
    first("start_date", START_PATTERNS, dated)
    if not any(h.field == "end_date" for h in hits) and (m := END_YEAR.search(t)):
        y = int(m.group("y"))
        if 2000 <= y <= 2045:
            hits.append(Hit("end_date", f"{y}-12-31", m.start(), m.end(), "text.end_year").with_sentence(t))
    if m := PRICES_UNTIL.search(t):
        d = parse_date(m.group("d"))
        if d:
            hits.append(Hit("prices_until", d.isoformat(), m.start(), m.end(), "text.prices_until").with_sentence(t))

    for pat in (RENEWAL, RENEWAL_FOR, RENEWAL_ALT):
        for m in pat.finditer(t):
            if pat is RENEWAL_ALT:
                lo, hi = sentence_around(t, m.start(), m.end())
                if not _RENEW_CONTEXT.search(t[lo:hi]):
                    continue
            try:
                count = _num(m.group("n"))
                length = _num(m.group("len")) if m.group("len") else 1
                unit = m.group("unit").lower()
                # "a two (2)-year extension" / "one two-year renewal": with no separate length and a
                # singular noun, the number is the length of ONE renewal, not a count of them.
                tail = t[m.end("unit"):m.end()].lower()
                if not m.group("len") and re.search(r"(?:renewal|extension|option|term|period)\b$", tail) \
                        and re.fullmatch(r"\s*(?:\(\d+\)\s*)?-?\s*", t[m.end("n"):m.start("unit")] or ""):
                    count, length = 1, count
                months = length * (12 if unit == "year" else 1)
                if 1 <= count <= 10:
                    hits.append(Hit("renewals", {"count": count, "months_each": months}, m.start(), m.end(), "text.renewals").with_sentence(t))
                    break
            except (KeyError, ValueError):
                continue
        if any(h.field == "renewals" for h in hits):
            break

    for route, pat in TEXT_ROUTE:
        if m := pat.search(t):
            hits.append(Hit("route", route, m.start(), m.end(), f"text.route.{route}").with_sentence(t))
            break

    for m in FY_RANGE.finditer(t):
        lo, hi = sentence_around(t, m.start(), m.end())
        # A CIP lists a project across a planning horizon; that is not the contract's term.
        if _CIP.search(t[lo:hi]) or not re.search(r"agreement|contract|services|purchase|budget", t[lo:hi], re.I):
            continue
        # "any approved extension for FY28 and FY29" names the renewal years, not the contract's own.
        if re.search(r"\b(?:extension|renew\w*|option)\b", t[max(lo, m.start() - 60):m.start()], re.I):
            continue
        a, b = (int(x) if len(x) == 4 else 2000 + int(x) for x in (m.group("a"), m.group("b")))
        if 2000 < a <= b <= a + 10:
            # Fiscal years in Ann Arbor run July 1 - June 30; FY2027 ends June 30, 2027.
            hits.append(Hit("fy_range", {"from": a, "to": b}, m.start(), m.end(), "text.fy_range").with_sentence(t))
            break

    return hits


# ---------------------------------------------------------------------------
# Categories (what a seller would call the market)
# ---------------------------------------------------------------------------

CATEGORIES: dict[str, dict] = {
    "it_software": {
        "label": "IT & software",
        "kw": r"software|\bSaaS\b|subscription|licens|\bIT\b|information technology|technology|network|cyber|server|"
        r"\bERP\b|database|\bGIS\b|cloud|computer|laptop|\bUKG\b|Tyler|Munis|workforce management|platform|"
        r"permitting system|website|telecom|phone system|fiber|data center|\bAI\b|records management|digital",
        "dept": r"information technology",
    },
    "public_safety": {
        "label": "Public safety tech & equipment",
        "kw": r"police|fire\b|firefight|ambulance|\bEMS\b|\b911\b|dispatch|body[- ]worn|camera|taser|siren|"
        r"emergency management|radio|SCBA|turnout gear|crime|license plate|public safety|rescue",
        "dept": r"police|fire|emergency|safety",
    },
    "water_utilities": {
        "label": "Water, sewer & utilities",
        "kw": r"water(?! damage)|watermain|sewer|sanitary|storm ?water|wastewater|hydrant|\bmain\b|treatment plant|utilit|"
        r"chlorine|lime|biosolids|meter|dam\b|energy utility|electric",
        "dept": r"water|utilities|sustainable energy",
    },
    "streets_transport": {
        "label": "Streets & transportation",
        "kw": r"street|road|paving|resurfac|sidewalk|traffic|signal|bridge|transportation|bikeway|bike lane|"
        r"crosswalk|parking|pavement|asphalt|concrete|curb|transit\b|salt\b|snow",
        "dept": r"transportation|engineering|systems planning",
    },
    "facilities_construction": {
        "label": "Facilities & construction",
        "kw": r"construction|building|roof|HVAC|renovat|facility|facilities|demolition|remediation|elevator|"
        r"boiler|janitorial|custodial|painting|flooring|window|restoration|architect",
        "dept": r"facilities|fleet and facility|project management",
    },
    "fleet_equipment": {
        "label": "Fleet, vehicles & equipment",
        "kw": r"vehicle|truck|fleet|equipment|mower|loader|tractor|container|cart|tires|fuel|"
        r"sweeper|excavator|trailer|\bpick-?up\b|SUV|van\b",
        "dept": r"fleet",
    },
    "parks_environment": {
        "label": "Parks, forestry & environment",
        "kw": r"parks?\b|recreation|golf|pool|trail|tree|forestry|natural area|canoe|playground|landscap|"
        r"solid waste|recycl|compost|climate|sustainab|solar|heat pump|electrification|deer",
        "dept": r"parks|sustainability|natural area|solid waste",
    },
    "professional_services": {
        "label": "Consulting & professional services",
        "kw": r"consult|engineering services|design services|professional services|study|assessment|audit|"
        r"legal|appraisal|survey|planning services|master plan|training|staffing|actuar|benefits|insurance",
        "dept": r"attorney|human resources|finance|administrator|planning",
    },
    "housing_community": {
        "label": "Housing & human services",
        "kw": r"housing|affordable|homeless|shelter|community development|human services|senior|youth|"
        r"food|eviction|tenant|counseling|treatment court|sobriety|recovery|mental health|social work|case management",
        "dept": r"housing|community|district court",
    },
}

# Keywords match at a word start ("tree" must not fire on "Street"); stems like "renovat" still work.
_CAT_RE = {k: (re.compile(r"\b(?:" + v["kw"] + ")", re.I), re.compile(v["dept"], re.I)) for k, v in CATEGORIES.items()}


def categorize(title: str, requester: str | None) -> list[str]:
    """Multi-label categories. A water-main engineering contract is both water and professional services."""
    t = normalize(title)
    req = normalize(requester or "")
    scores: dict[str, int] = {}
    for key, (kw, dept) in _CAT_RE.items():
        s = 2 * len(kw.findall(t)) + (1 if req and dept.search(req) else 0)
        if s:
            scores[key] = s
    ranked = sorted(scores, key=lambda k: -scores[k])
    return ranked[:3]


# ---------------------------------------------------------------------------
# Who wrote the memo (the people a seller would talk to)
# ---------------------------------------------------------------------------

# Nearly every Ann Arbor memo ends its header with
#   "Prepared by: Missy Stults, Sustainability and Innovations Director Reviewed by: Marti Praschan, ..."
# The preparer is usually the staff lead who scoped the purchase; the reviewer is their area administrator.
_STAFF = re.compile(
    r"\b(?P<role>Prepared|Reviewed) [Bb]y:?\s+(?P<who>.+?)(?=\s+(?:Prepared|Reviewed|Approved) [Bb]y\b|\s*\.\.|$)"
)
_SUFFIX_PART = re.compile(r"^(?:Jr|Sr|II|III|IV|PE|P\.E|PhD|AICP|CPA)\.?$", re.I)
# A header often lists several reviewers in a row: "Tom Shewchuk, Director, ITSU Kim Hoenerhoff,
# Financial Analyst". The next person starts where a two-word name is followed by a comma. Words that
# occur in job titles can't start a name, so "Systems Planning, Public Services" isn't read as a person.
_TITLE_WORD = (
    r"(?:Acting|Interim|Senior|Assistant|Associate|Deputy|Chief|Executive|Area|City|Public|Systems?|Services?|"
    r"Planning|Financial|Finance|Information|Technology|Community|Economic|Development|Housing|Water|Resource|"
    r"Treatment|Plant|Fleet|Facilities|Field|Operations|Parks|Recreation|Engineering|Project|Capital|Budget|"
    r"Human|Office|Unit|Police|Fire|Safety|Court|District|Transportation|Sustainability|Innovations?|Energy|"
    r"Solid|Waste|Utilities|Accounting|Procurement|Purchasing|Risk|Building|Rental|Natural|Areas?|Asset|"
    r"Management|Manager|Director|Administrator|Analyst|Coordinator|Supervisor|Specialist|Officer|Engineer|"
    r"Attorney|Treasurer|Clerk|Superintendent|Administrative|Customer|Service|Wastewater|Stormwater|Forestry)"
)
_NEXT_PERSON = re.compile(r"\s+(?:and\s+)?(?!" + _TITLE_WORD + r"\b)[A-Z][a-z]+(?:\s[A-Z]\.)?\s[A-Z][A-Za-z'\u2019-]+[,.]\s|\s+Reviewed\s+b\w*:?")


def _split_person(who: str) -> tuple[str, str] | None:
    parts = [p.strip() for p in who.split(",")]
    if len(parts) < 2:
        return None
    name = re.sub(r"^(?:Dr|Mr|Mrs|Ms|Mx)\.?\s+", "", parts[0])
    i = 1
    while i < len(parts) - 1 and _SUFFIX_PART.match(parts[i]):
        name += ", " + parts[i]
        i += 1
    title = ", ".join(parts[i:]).strip()
    nxt = _NEXT_PERSON.search(title)
    if nxt:
        title = title[: nxt.start()]
    title = title.strip(" ,;")
    if not (1 <= len(name.split()) <= 5) or not title or len(title) > 120:
        return None
    return name, title


def parse_staff(text_plain: str) -> list[Hit]:
    """The memo's "Prepared by" and "Reviewed by" people, each with the exact header text as evidence."""
    t = normalize(text_plain)
    hits: list[Hit] = []
    seen = set()
    for m in _STAFF.finditer(t[:4000]):  # the header block sits near the top
        role = "prepared_by" if m.group("role") == "Prepared" else "reviewed_by"
        if role in seen:
            continue
        person = _split_person(m.group("who"))
        if not person:
            continue
        seen.add(role)
        # Quote only this person: the header text up to the end of their title.
        end = t.find(person[1], m.start("who")) + len(person[1])
        h = Hit(role, {"name": person[0], "title": person[1]}, m.start("who"), end, f"text.{role}")
        h.quote_start, h.quote_end = m.start(), end
        hits.append(h)
    return hits


# ---------------------------------------------------------------------------
# What kind of clock a contract has
# ---------------------------------------------------------------------------

# Only some contracts have a renewal clock. Buying two trucks or building a bridge is done when it's
# done; the next chance to compete is the next purchase, not a renewal date. Counting those as
# "missing an end date" would make the coverage number meaningless, so each contract gets a class.
_GOODS = re.compile(
    r"\b(?:purchase of|vehicles?|trucks?|tractors?|mowers?|loaders?|excavators?|trailers?|sweepers?|"
    r"equipment|units?\b|tires|salt|containers|carts|materials|supplies|chemicals|lime|chlorine|"
    r"furniture|uniforms|radios|cameras|computers|laptops|hardware)\b",
    re.I,
)
_SERVICE = re.compile(
    r"\b(?:services?|maintenance|support|subscription|licens\w*|software|hosting|lease|on-call|as-needed|"
    r"annual|consulting|management|monitoring|inspection|janitorial|cleaning|operation)\b",
    re.I,
)


def contract_class(title: str, kind: str | None) -> str:
    """'term' (services that run for a period and come up for renewal), 'one_time' (goods or a
    construction project), or 'change' (an amendment or change order to a contract we may already have)."""
    t = normalize(title)
    if kind in ("amendment", "change_order"):
        return "change"
    if kind == "construction" or re.search(r"\bconstruction (?:contract|project)\b", t, re.I):
        return "one_time"
    if _GOODS.search(t) and not _SERVICE.search(t):
        return "one_time"
    return "term"


# "Annual Software Maintenance and Support for FY 2027": a one-fiscal-year contract in the title.
_TITLE_FY = re.compile(r"\b(?:for|in|during)\s+(?:the\s+)?FY\s?(?P<y>20\d{2}|\d{2})\b(?!\s*(?:-|–|through|to|thru)\s*(?:FY\s?)?\d)", re.I)


def title_fiscal_year(title: str) -> Hit | None:
    t = normalize(title)
    m = _TITLE_FY.search(t)
    if not m:
        return None
    y = int(m.group("y"))
    y = y if y > 2000 else 2000 + y
    if not 2015 <= y <= 2045:
        return None
    h = Hit("fy_range", {"from": y, "to": y}, m.start(), m.end(), "title.fiscal_year")
    h.quote_start, h.quote_end = 0, len(t)
    return h


# ---------------------------------------------------------------------------
# How long the incumbent has had the work, when the memo says so
# ---------------------------------------------------------------------------

# "The current maintenance agreement with Cogsdale Corporation has been in place since 2018",
# "Carlisle/Wortman has been providing reliable services to the City ... since 2014". Council records
# here start in 2022, so this is the only way to see an incumbency that began earlier.
_SINCE = re.compile(
    r"\b(?:has been in place|have been in place|in place|under contract|ha(?:s|ve) (?:been )?provid(?:ed|ing)|"
    r"ha(?:s|ve) (?:served|supported|maintained|been (?:the|our|a))|ha(?:s|ve) worked with|ha(?:s|ve) used)"
    r"[^.;]{0,90}?\bsince\s+(?:(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+)?"
    r"(?P<y>(?:19|20)\d\d)\b",
    re.I,
)


def parse_incumbent_since(text_plain: str, vendor: str | None) -> Hit | None:
    """The year a vendor's relationship with the city began, if the memo states it near the vendor's name."""
    if not vendor:
        return None
    t = normalize(text_plain)
    key = vendor_key(vendor).split()
    if not key:
        return None
    first = key[0]
    for m in _SINCE.finditer(t):
        y = int(m.group("y"))
        if not 1970 <= y <= date.today().year:
            continue
        s0, s1 = sentence_around(t, m.start(), m.end())
        if first in t[s0:s1].lower():
            h = Hit("since_year", y, m.start(), m.end(), "text.incumbent_since")
            h.quote_start, h.quote_end = s0, s1
            return h
    return None


# "automatically renews annually", "up to 5 automatic renewals", "Automatic renewal for an additional three-year
# term unless notice is provided": an evergreen contract has no natural rebid date unless someone acts.
_AUTO_RENEW = re.compile(r"\bautomatic(?:ally)?\s+renew\w*|\bauto-?renew\w*", re.I)


def parse_auto_renew(text_plain: str) -> Hit | None:
    t = normalize(text_plain)
    m = _AUTO_RENEW.search(t)
    if not m:
        return None
    return Hit("auto_renews", True, m.start(), m.end(), "text.auto_renews").with_sentence(t)
