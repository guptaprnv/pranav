"""Parser for monthly portfolio disclosure files (CSV and Excel).

AMCs publish these in a SEBI-prescribed shape, but the exact header wording
varies between houses and over time ("% to Net Assets" vs "% to NAV" vs
"% of Net Assets", and so on). So columns are identified by matching normalised
headers against an explicit alias list rather than by position.

Two rules hold this together, both from the brief's no-silent-fallbacks
principle:

1. If a required column cannot be identified, parsing **fails** with the
   headers it actually saw. It does not fall back to column order, because a
   mis-mapped column produces plausible-looking weights that are wrong, and
   every downstream finding would inherit that silently.
2. Rows that do not yield a usable holding are collected in `unmapped_rows`
   rather than skipped, so a format drift is visible in the output.

Adding a new AMC's wording is an edit to `_ALIASES` -- a data change with a
test, not new parsing logic.
"""
from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

from .models import DisclosureHolding, DisclosureParseError, SchemePortfolio

_NORMALISE_RE = re.compile(r"[^a-z0-9]+")

# Canonical field -> header wordings seen in the wild. Matching is on the
# normalised header (lowercased, punctuation collapsed), and a header matches
# if it *starts with* one of these, which absorbs the footnote markers AMCs
# commonly append ("Industry^", "% to Net Assets #").
_ALIASES: dict[str, tuple[str, ...]] = {
    "instrument_name": (
        "name of the instrument",
        "name of instrument",
        "instrument name",
        "security name",
        "name of the security",
    ),
    "isin": ("isin",),
    "industry": ("industry", "industry rating", "sector"),
    "quantity": ("quantity", "qty", "no of shares", "number of shares"),
    "market_value_lakhs": (
        "market value",
        "market fair value",
        "market value rs in lakhs",
        "fair value",
        "amount",
    ),
    "percent_to_nav": (
        "to net assets",
        "to nav",
        "percentage to net assets",
        "percent to nav",
        "of net assets",
        "to net asset",
    ),
}

_REQUIRED = ("instrument_name", "percent_to_nav")

# Subtotal rows carry both a name and a percentage, so they look exactly like
# holdings to a naive parser -- and including them double-counts every position
# in look-through, producing plausible but badly wrong exposure numbers.
#
# Detection deliberately requires TWO signals: the name matches a total-ish
# pattern AND the row has no ISIN. Name alone would misclassify a genuine
# holding in a company whose name contains "total" (TotalEnergies is a real
# listed company); ISIN alone would misclassify legitimately unlisted holdings,
# which have no ISIN but are real positions.
_STRUCTURAL_NAME_RE = re.compile(
    r"^\s*(sub\s*-?\s*total|total|grand\s+total|net\s+assets?|net\s+asset\s+value)\b",
    re.IGNORECASE,
)


def is_structural_row(name: str, isin: str | None) -> bool:
    """True for subtotal / total / net-asset summary rows.

    See `_STRUCTURAL_NAME_RE` for why both signals are required.
    """
    return not isin and bool(_STRUCTURAL_NAME_RE.match(name))


def _normalise_header(header: str) -> str:
    return _NORMALISE_RE.sub(" ", str(header).lower()).strip()


def map_columns(headers: Sequence[str]) -> dict[str, int]:
    """Map canonical field names to column indices.

    Raises `DisclosureParseError` if a required column is missing, listing the
    headers that were actually present so the failure is diagnosable without
    opening the file.
    """
    mapping: dict[str, int] = {}
    normalised = [_normalise_header(h) for h in headers]

    for field, aliases in _ALIASES.items():
        for index, header in enumerate(normalised):
            if not header:
                continue
            # "% to Net Assets" normalises to "to net assets" because the
            # percent sign is punctuation, so startswith handles both it and
            # trailing footnote markers.
            if any(header.startswith(alias) or alias in header for alias in aliases):
                mapping[field] = index
                break

    missing = [field for field in _REQUIRED if field not in mapping]
    if missing:
        raise DisclosureParseError(
            f"could not identify required column(s) {missing}. "
            f"headers seen: {[h for h in headers if str(h).strip()]}. "
            f"if this is a new AMC wording, add it to _ALIASES with a test."
        )
    return mapping


def _to_float(raw: object) -> float | None:
    if raw is None:
        return None
    token = str(raw).strip().replace(",", "").replace("%", "")
    if not token or token.lower() in {"-", "na", "n.a.", "nil", "none"}:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _row_to_holding(row: Sequence[object], mapping: dict[str, int]) -> DisclosureHolding | None:
    def cell(field: str) -> object | None:
        index = mapping.get(field)
        if index is None or index >= len(row):
            return None
        return row[index]

    name = cell("instrument_name")
    name_text = str(name).strip() if name is not None else ""
    percent = _to_float(cell("percent_to_nav"))

    # Disclosure files are full of section headers ("Equity & Equity related"),
    # subtotals, and blank spacer rows. A row with no name, or a name but no
    # percentage, is one of those rather than a holding.
    if not name_text or percent is None:
        return None

    isin_raw = cell("isin")
    isin = str(isin_raw).strip() if isin_raw is not None else ""

    if is_structural_row(name_text, isin or None):
        return None

    return DisclosureHolding(
        instrument_name=name_text,
        isin=isin or None,
        industry=(str(cell("industry")).strip() or None) if cell("industry") is not None else None,
        quantity=_to_float(cell("quantity")),
        market_value_lakhs=_to_float(cell("market_value_lakhs")),
        percent_to_nav=percent,
    )


def parse_rows(
    rows: Iterable[Sequence[object]],
    scheme_name: str,
    as_of: date,
    source_file: str,
    amfi_code: str | None = None,
) -> SchemePortfolio:
    """Parse already-loaded rows. Shared by the CSV and Excel entry points.

    The header row is found by scanning for the first row whose columns map
    successfully, because disclosure files routinely carry title and metadata
    rows above the actual table.
    """
    row_list = [list(row) for row in rows]
    mapping: dict[str, int] | None = None
    header_index = -1
    last_error: DisclosureParseError | None = None

    for index, row in enumerate(row_list):
        try:
            mapping = map_columns([str(cell) if cell is not None else "" for cell in row])
            header_index = index
            break
        except DisclosureParseError as exc:
            last_error = exc

    if mapping is None:
        raise last_error or DisclosureParseError(f"no header row found in {source_file}")

    holdings: list[DisclosureHolding] = []
    unmapped: list[str] = []

    for row in row_list[header_index + 1 :]:
        holding = _row_to_holding(row, mapping)
        if holding is None:
            text = " | ".join(str(cell) for cell in row if str(cell).strip())
            if text:
                unmapped.append(text)
            continue
        holdings.append(holding)

    return SchemePortfolio(
        scheme_name=scheme_name,
        as_of=as_of,
        holdings=holdings,
        source_file=source_file,
        amfi_code=amfi_code,
        unmapped_rows=unmapped,
    )


def parse_csv(
    path: str | Path,
    scheme_name: str,
    as_of: date,
    amfi_code: str | None = None,
) -> SchemePortfolio:
    file_path = Path(path)
    with file_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    return parse_rows(rows, scheme_name, as_of, str(file_path), amfi_code)


def parse_excel(
    path: str | Path,
    scheme_name: str,
    as_of: date,
    amfi_code: str | None = None,
    sheet: str | None = None,
) -> SchemePortfolio:
    from openpyxl import load_workbook

    file_path = Path(path)
    workbook = load_workbook(file_path, read_only=True, data_only=True)
    worksheet = workbook[sheet] if sheet else workbook.worksheets[0]
    rows = [list(row) for row in worksheet.iter_rows(values_only=True)]
    workbook.close()
    return parse_rows(rows, scheme_name, as_of, str(file_path), amfi_code)
