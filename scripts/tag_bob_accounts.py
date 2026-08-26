#!/usr/bin/env python3
"""
Tag registration rows with their Book of Business (BOB) account match.

Reads a registrations CSV or Excel file, resolves each row's company name
against the BOB company index (server/utils/company_map.py) and writes the same
rows back to CSV with two extra columns:

    BOB Account   - "Yes" when the company resolves to a BOB company, else "No"
    BOB Company   - the canonical BOB company name when matched

Usage:
    python scripts/tag_bob_accounts.py coco_cli_gen_ai.csv
    python scripts/tag_bob_accounts.py registrations.xlsx --sheet "Sheet1"
    python scripts/tag_bob_accounts.py coco_cli_gen_ai.csv -o out.csv --company-col "..."
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from server.utils.company_map import get_bob_company, normalize_company_key  # noqa: E402

MATCH_COL = "BOB Account"
COMPANY_COL = "BOB Company"

DEFAULT_COMPANY_HEADER = "College/School/Company/Startup Name"

# Hand-verified overrides for names the fuzzy matcher cannot reach: acronyms
# (OCBC, UOB) and Singapore "Pte Ltd" entries, whose index keys keep a trailing
# "pte" and so score below the fuzzy threshold. Keys are normalize_company_key()
# output; values are the exact company_name as it appears in the BOB list.
ALIASES = {
    "ocbc": "OCBC Bank Ltd",
    "uob": "United Overseas Bank Limited (UOB)",
    "mediacorp": "Mediacorp Pte. Ltd.",
    "propertyguru": "PropertyGuru Pte. Ltd.",
    "shopback": "Ecommerce Enablers Pte. Ltd. (Shopback)",
    "singapore airlines": "SINGAPORE AIRLINES GROUP",
    "certis": "CERTIS TECHNOLOGY (SINGAPORE) PTE. LTD.",
    "kulicke and soffa": "KULICKE AND SOFFA GLOBAL HOLDING CORPORATION",
}


def _alias_lookup(raw_company: str) -> str | None:
    """Resolve a company via the hand-verified alias table, ignoring 'Pte'."""
    key = normalize_company_key(raw_company)
    if not key:
        return None
    if key.endswith(" pte"):
        key = key[:-4].strip()
    return ALIASES.get(key)


def resolve_bob_company(raw_company: str) -> str | None:
    """Alias table first (hand-verified), then the fuzzy BOB index."""
    return _alias_lookup(raw_company) or get_bob_company(raw_company)


def _detect_company_column(fieldnames: list[str]) -> str | None:
    if DEFAULT_COMPANY_HEADER in fieldnames:
        return DEFAULT_COMPANY_HEADER
    for name in fieldnames:
        low = name.lower()
        if "company" in low or "organization" in low:
            return name
    return None


EXCEL_SUFFIXES = (".xlsx", ".xls", ".xlsm")


def _read_rows(path: Path, sheet: str | None = None) -> tuple[list[str], list[dict]]:
    if path.suffix.lower() in EXCEL_SUFFIXES:
        import pandas as pd

        df = pd.read_excel(path, sheet_name=sheet or 0, dtype=str).fillna("")
        return list(df.columns), df.to_dict("records")

    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("Input file has no header row.")
        return list(reader.fieldnames), list(reader)


def tag_file(
    input_path: Path,
    output_path: Path,
    company_col: str | None = None,
    sheet: str | None = None,
) -> dict:
    fieldnames, rows = _read_rows(input_path, sheet)

    company_col = company_col or _detect_company_column(fieldnames)
    if not company_col:
        raise ValueError(f"Could not find a company column. Available: {fieldnames}")

    out_fields = fieldnames + [c for c in (MATCH_COL, COMPANY_COL) if c not in fieldnames]

    matched = 0
    via_alias = 0
    for row in rows:
        raw = row.get(company_col, "")
        alias = _alias_lookup(raw)
        bob = alias or get_bob_company(raw)
        row[MATCH_COL] = "Yes" if bob else "No"
        row[COMPANY_COL] = bob or ""
        if bob:
            matched += 1
        if alias:
            via_alias += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return {
        "total": len(rows),
        "matched": matched,
        "via_alias": via_alias,
        "company_col": company_col,
        "output": output_path,
    }


def check_aliases() -> list[str]:
    """Return alias targets that are not present in the BOB index."""
    from server.utils.company_map import _load_index

    exact = _load_index()["exact"]
    return [
        f"{key} -> {value}"
        for key, value in ALIASES.items()
        if normalize_company_key(value) not in exact
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Tag rows that belong to BOB accounts")
    parser.add_argument("input", help="Input registrations CSV or Excel file")
    parser.add_argument("-o", "--output", help="Output CSV path")
    parser.add_argument("--company-col", help="Company column name in the input file")
    parser.add_argument("--sheet", help="Sheet name to read (Excel input only)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        sys.exit(f"Input file not found: {input_path}")

    output_path = Path(args.output) if args.output else input_path.with_name(
        f"{input_path.stem}_bob_tagged.csv"
    )

    for stale in check_aliases():
        print(f"[WARN] alias target not found in BOB list: {stale}")

    stats = tag_file(input_path, output_path, args.company_col, args.sheet)
    print(f"[OK] company column: '{stats['company_col']}'")
    print(f"[OK] rows: {stats['total']:,}")
    print(f"[OK] BOB accounts: {stats['matched']:,} "
          f"({stats['via_alias']:,} via alias table)")
    print(f"[OK] saved -> {stats['output']}")


if __name__ == "__main__":
    main()
