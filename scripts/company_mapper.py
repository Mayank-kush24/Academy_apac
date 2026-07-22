#!/usr/bin/env python3
"""
Company Name Mapper (CLI) — map raw company names to Book of Business names.

Every company is matched against the BOB reference index (exact lookup first,
then fuzzy match). Names with no confident match are left unchanged.

Build the index once:
    python scripts/build_company_index.py --src data/bob_companies.xlsx

Map a file (CSV or Excel; columns auto-detected):
    python scripts/company_mapper.py input.csv
    python scripts/company_mapper.py input.xlsx -o mapped.csv
    python scripts/company_mapper.py input.csv --company-col organization_name

Output columns: email, raw company, mapped company
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from server.utils.company_map import _index_path, get_bob_company, map_company  # noqa: E402

EMAIL_ALIASES = frozenset({
    "email", "e-mail", "e mail", "mail", "email address", "emailaddress",
})
COMPANY_ALIASES = frozenset({
    "company", "company name", "raw company", "organization", "organization_name",
    "org", "org name", "college/school/company/startup name",
    "collegeschoolcompanystartupname",
})


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _detect(fieldnames, aliases, contains):
    for name in fieldnames:
        if _norm(name) in aliases:
            return name
    for name in fieldnames:
        norm = _norm(name)
        if any(c in norm for c in contains):
            return name
    return None


def _read_rows(path: Path):
    if path.suffix.lower() in (".xlsx", ".xls", ".xlsm"):
        import pandas as pd

        df = pd.read_excel(path, dtype=str).fillna("")
        return list(df.columns), df.to_dict("records")
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("Input file has no header row.")
        return list(reader.fieldnames), list(reader)


def _default_output(input_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return input_path.with_name(f"{input_path.stem}_companies_mapped_{stamp}.csv")


def map_file(input_path: Path, output_path: Path,
             email_col: str | None, company_col: str | None) -> dict:
    fieldnames, rows = _read_rows(input_path)
    if not fieldnames:
        raise ValueError("Could not read any columns from the input file.")

    company_col = company_col or _detect(
        fieldnames, COMPANY_ALIASES, ("company", "organization", "org")
    )
    email_col = email_col or _detect(fieldnames, EMAIL_ALIASES, ("email", "mail"))
    if not company_col:
        raise ValueError(
            "Could not find a company column. Use --company-col to name it. "
            f"Available columns: {fieldnames}"
        )

    total = len(rows)
    matched = 0
    out_rows = []
    for row in rows:
        raw_company = str(row.get(company_col, "") or "").strip()
        email = str(row.get(email_col, "") or "").strip() if email_col else ""
        mapped = map_company(raw_company)
        if raw_company and get_bob_company(raw_company):
            matched += 1
        out_rows.append({
            "email": email,
            "raw company": raw_company,
            "mapped company": mapped,
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["email", "raw company", "mapped company"]
        )
        writer.writeheader()
        writer.writerows(out_rows)

    return {
        "total": total,
        "matched": matched,
        "unchanged": total - matched,
        "company_col": company_col,
        "email_col": email_col or "(none)",
        "output": output_path,
    }


def main():
    parser = argparse.ArgumentParser(description="Map raw company names to BOB company list")
    parser.add_argument("input", help="Input CSV or Excel file")
    parser.add_argument("-o", "--output", help="Output CSV path")
    parser.add_argument("--company-col", help="Name of the raw company column")
    parser.add_argument("--email-col", help="Name of the email column")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        sys.exit(f"Input file not found: {input_path}")

    if not os.path.isfile(_index_path()):
        sys.exit(
            "Company index not found.\n"
            "Build it first:\n"
            "  python scripts/build_company_index.py"
        )

    output_path = Path(args.output) if args.output else _default_output(input_path)
    print(f"Mapping {input_path} ...")
    stats = map_file(input_path, output_path, args.email_col, args.company_col)
    print(f"[OK] columns: company='{stats['company_col']}' email='{stats['email_col']}'")
    print(f"[OK] rows: {stats['total']:,}")
    print(f"[OK] matched to BOB: {stats['matched']:,}")
    print(f"[OK] left unchanged: {stats['unchanged']:,}")
    print(f"[OK] saved -> {stats['output']}")


if __name__ == "__main__":
    main()
