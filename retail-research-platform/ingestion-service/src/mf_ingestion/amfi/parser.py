"""Parser for AMFI's NAVAll feed -- the free, public scheme master + daily NAV.

Format (semicolon-delimited, with interleaved section headers):

    Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date

    Open Ended Schemes(Equity Scheme - Large Cap Fund)
    Some Asset Management Company Limited
    100001;INF000A01AA1;INF000A01AB9;Some Large Cap Fund - Direct Plan - Growth;123.4567;06-Aug-2026

Category and AMC names appear as bare lines with no delimiter, and apply to
every data row beneath them until the next such line. That makes this a
stateful line-oriented parse, not a CSV read.

Per the brief's no-silent-fallbacks rule, any line this parser cannot classify
is collected into `unparsed_lines` rather than skipped, so a format change at
AMFI surfaces as visible output instead of quietly shrinking the scheme master.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from ..models import Option, Plan, Scheme, SchemeMaster

FIELD_COUNT = 6
HEADER_PREFIX = "Scheme Code"

# Category lines look like "Open Ended Schemes(Equity Scheme - Large Cap Fund)"
# or "Close Ended Schemes(...)". AMC lines are bare company names. Both lack
# semicolons, so the parenthesised "Schemes(" shape is what separates them.
_CATEGORY_RE = re.compile(r"Schemes?\s*\(", re.IGNORECASE)

# AMFI writes "N.A." for schemes with no NAV published on a given day.
_NULL_TOKENS = {"", "-", "n.a.", "na", "null", "nav not available"}


def _parse_nav(raw: str) -> float | None:
    if raw.strip().lower() in _NULL_TOKENS:
        return None
    try:
        return float(raw.strip())
    except ValueError:
        return None


def _parse_date(raw: str) -> date | None:
    token = raw.strip()
    if token.lower() in _NULL_TOKENS:
        return None
    try:
        return datetime.strptime(token, "%d-%b-%Y").date()
    except ValueError:
        return None


def _parse_isin(raw: str) -> str | None:
    token = raw.strip()
    return None if token.lower() in _NULL_TOKENS else token


def detect_plan(scheme_name: str) -> Plan:
    """Extract Direct/Regular from a scheme name.

    Deliberately conservative. AMFI names are not perfectly consistent, and per
    the brief the plan variant determines the largest single leak -- so an
    unrecognised name yields UNKNOWN and forces a question downstream rather
    than defaulting. Historically many schemes predate the direct-plan regime
    and carry no marker at all; those are genuinely unknown from the name.
    """
    haystack = scheme_name.lower()
    has_direct = re.search(r"\bdirect\b", haystack) is not None
    has_regular = re.search(r"\bregular\b", haystack) is not None
    if has_direct and not has_regular:
        return Plan.DIRECT
    if has_regular and not has_direct:
        return Plan.REGULAR
    return Plan.UNKNOWN


def detect_option(scheme_name: str) -> Option:
    """Extract Growth/IDCW from a scheme name. Same conservatism as detect_plan.

    IDCW is the current name for what older scheme names call dividend, payout,
    or reinvestment; all of those map to IDCW.
    """
    haystack = scheme_name.lower()
    has_growth = re.search(r"\bgrowth\b", haystack) is not None
    has_idcw = (
        re.search(r"\bidcw\b", haystack) is not None
        or re.search(r"\bdividend\b", haystack) is not None
        or re.search(r"\bpayout\b", haystack) is not None
        or re.search(r"\breinvest", haystack) is not None
    )
    if has_growth and not has_idcw:
        return Option.GROWTH
    if has_idcw and not has_growth:
        return Option.IDCW
    return Option.UNKNOWN


def parse_navall(text: str, source_url: str, fetched_at: date) -> SchemeMaster:
    schemes: list[Scheme] = []
    unparsed: list[str] = []
    current_category = ""
    current_amc = ""

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            continue
        if line.startswith(HEADER_PREFIX):
            continue

        if ";" not in line:
            if _CATEGORY_RE.search(line):
                current_category = line
            else:
                current_amc = line
            continue

        fields = line.split(";")
        if len(fields) != FIELD_COUNT:
            unparsed.append(raw_line)
            continue

        code, isin_growth, isin_reinvest, name, nav, nav_date = (f.strip() for f in fields)
        if not code or not name:
            unparsed.append(raw_line)
            continue

        schemes.append(
            Scheme(
                amfi_code=code,
                name=name,
                amc=current_amc,
                category=current_category,
                plan=detect_plan(name),
                option=detect_option(name),
                isin_growth=_parse_isin(isin_growth),
                isin_reinvestment=_parse_isin(isin_reinvest),
                nav=_parse_nav(nav),
                nav_date=_parse_date(nav_date),
            )
        )

    return SchemeMaster(
        schemes=schemes,
        source_url=source_url,
        fetched_at=fetched_at,
        unparsed_lines=unparsed,
    )
