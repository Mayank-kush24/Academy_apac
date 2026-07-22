#!/usr/bin/env python3
"""
External company mapper — pass email + company name, get mapped BOB company.

Input: CSV or Excel with email and company columns (headers auto-detected).
Output CSV columns: email, company name, mapped company name

If no BOB match is found, mapped company name equals the original company name.

One-time setup (uses the BOB list already in your database):
    python scripts/build_company_index.py

Batch file:
    python scripts/external_company_mapper.py input.csv
    python scripts/external_company_mapper.py input.csv -o output.csv

Single row:
    python scripts/external_company_mapper.py --email user@example.com --company "TCS"
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

from server.utils.company_map import _index_path, map_company  # noqa: E402

OUTPUT_FIELDS = ["email", "company name", "mapped company name"]

EMAIL_ALIASES = frozenset({
    "email", "e-mail", "e mail", "mail", "email address", "emailaddress",
})
COMPANY_ALIASES = frozenset({
    "company", "company name", "organization", "organization_name",
    "org", "org name", "college/school/company/startup name",
})


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _detect_column(fieldnames: list[str], aliases: frozenset[str], contains: tuple[str, ...]) -> str | None:
    for name in fieldnames:
        if _norm(name) in aliases:
            return name
    for name in fieldnames:
        norm = _norm(name)
        if any(part in norm for part in contains):
            return name
    return None


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
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
    return input_path.with_name(f"{input_path.stem}_mapped_{stamp}.csv")


def _map_row(email: str, company: str) -> dict[str, str]:
    company = (company or "").strip()
    return {
        "email": (email or "").strip(),
        "company name": company,
        "mapped company name": map_company(company),
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def map_file(
    input_path: Path,
    output_path: Path,
    email_col: str | None = None,
    company_col: str | None = None,
) -> dict:
    fieldnames, rows = _read_rows(input_path)
    email_col = email_col or _detect_column(fieldnames, EMAIL_ALIASES, ("email", "mail"))
    company_col = company_col or _detect_column(fieldnames, COMPANY_ALIASES, ("company", "organization", "org"))

    if not email_col:
        raise ValueError(
            "Could not find an email column. Use --email-col. "
            f"Available columns: {fieldnames}"
        )
    if not company_col:
        raise ValueError(
            "Could not find a company column. Use --company-col. "
            f"Available columns: {fieldnames}"
        )

    out_rows = [
        _map_row(str(row.get(email_col, "")), str(row.get(company_col, "")))
        for row in rows
    ]
    _write_csv(output_path, out_rows)

    matched = sum(
        1 for row in out_rows
        if row["company name"] and row["mapped company name"] != row["company name"]
    )
    return {
        "total": len(out_rows),
        "matched": matched,
        "unchanged": len(out_rows) - matched,
        "email_col": email_col,
        "company_col": company_col,
        "output": output_path,
    }


def _ensure_index() -> None:
    if not os.path.isfile(_index_path()):
        sys.exit(
            "Company index not found.\n"
            "Run once:\n"
            "  python scripts/build_company_index.py"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Map email + company name to BOB company (external tool)"
    )
    parser.add_argument("input", nargs="?", help="Input CSV or Excel file")
    parser.add_argument("-o", "--output", help="Output CSV path")
    parser.add_argument("--email-col", help="Email column name in input file")
    parser.add_argument("--company-col", help="Company column name in input file")
    parser.add_argument("--email", help="Single-row mode: email address")
    parser.add_argument("--company", help="Single-row mode: company name")
    args = parser.parse_args()

    _ensure_index()

    if args.email is not None or args.company is not None:
        if not args.email or not args.company:
            sys.exit("Single-row mode requires both --email and --company.")
        row = _map_row(args.email, args.company)
        print(",".join(OUTPUT_FIELDS))
        print(",".join(f'"{row[k]}"' if "," in row[k] else row[k] for k in OUTPUT_FIELDS))
        return

    if not args.input:
        parser.print_help()
        sys.exit(1)

    input_path = Path(args.input)
    if not input_path.is_file():
        sys.exit(f"Input file not found: {input_path}")

    output_path = Path(args.output) if args.output else _default_output(input_path)
    print(f"Mapping {input_path} ...")
    stats = map_file(input_path, output_path, args.email_col, args.company_col)
    print(f"[OK] email column: '{stats['email_col']}'")
    print(f"[OK] company column: '{stats['company_col']}'")
    print(f"[OK] rows: {stats['total']:,}")
    print(f"[OK] mapped to BOB: {stats['matched']:,}")
    print(f"[OK] unchanged: {stats['unchanged']:,}")
    print(f"[OK] saved -> {stats['output']}")


if __name__ == "__main__":
    main()
