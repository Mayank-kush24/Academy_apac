#!/usr/bin/env python3
"""
Job Title Mapper (CLI) — map raw job titles to the authoritative client list.

Every title is matched against the reference index built from the
"Complete List of Dev Titles" workbook (exact lookup first, then a fast,
length-aware fuzzy match). Titles with no confident match are left blank
(Unclassified) rather than force-fitted.

Build the index once:
    python scripts/build_title_index.py --src "Copy of  Complete List of Dev Titles.xlsx"

Map a file (CSV or Excel; columns auto-detected):
    python scripts/title_mapper.py input.csv
    python scripts/title_mapper.py input.xlsx -o mapped.csv
    python scripts/title_mapper.py input.csv --title-col Designation --email-col Email

Output columns: email, raw title, sub_category, broad_category
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

from server.utils.title_map import _index_path, get_title_categories  # noqa: E402

EMAIL_ALIASES = frozenset({
    "email", "e-mail", "e mail", "mail", "email address", "emailaddress",
})
TITLE_ALIASES = frozenset({
    "title", "job title", "raw title", "raw job title", "designation",
    "job_title", "jobtitle", "role", "position", "raw designation",
})


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _detect(fieldnames, aliases, contains):
    for name in fieldnames:
        if _norm(name) in aliases:
            return name
    for name in fieldnames:
        if any(c in _norm(name) for c in contains):
            return name
    return None


def _read_rows(path: Path):
    """Return (fieldnames, list-of-dict rows) for a CSV or Excel file."""
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


def map_file(input_path: Path, output_path: Path,
             email_col: str | None, title_col: str | None) -> dict:
    fieldnames, rows = _read_rows(input_path)
    if not fieldnames:
        raise ValueError("Could not read any columns from the input file.")

    title_col = title_col or _detect(fieldnames, TITLE_ALIASES,
                                     ("title", "designation", "role", "position"))
    email_col = email_col or _detect(fieldnames, EMAIL_ALIASES, ("email", "mail"))
    if not title_col:
        raise ValueError(
            "Could not find a job-title column. Use --title-col to name it. "
            f"Available columns: {fieldnames}"
        )

    total = len(rows)
    matched = 0
    out_rows = []
    for row in rows:
        raw_title = str(row.get(title_col, "") or "").strip()
        email = str(row.get(email_col, "") or "").strip() if email_col else ""
        sub, broad = get_title_categories(raw_title)
        if sub and broad:
            matched += 1
        out_rows.append({
            "email": email,
            "raw title": raw_title,
            "sub_category": sub or "",
            "broad_category": broad or "",
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["email", "raw title", "sub_category", "broad_category"]
        )
        writer.writeheader()
        writer.writerows(out_rows)

    return {
        "total": total,
        "matched": matched,
        "unmatched": total - matched,
        "title_col": title_col,
        "email_col": email_col or "(none)",
        "output": output_path,
    }


def main():
    parser = argparse.ArgumentParser(description="Map raw job titles to the client title list")
    parser.add_argument("input", help="Input CSV or Excel file")
    parser.add_argument("-o", "--output", help="Output CSV path (default: <input>_mapped_<ts>.csv)")
    parser.add_argument("--title-col", help="Name of the raw job-title column")
    parser.add_argument("--email-col", help="Name of the email column")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        sys.exit(f"Input file not found: {input_path}")

    if not os.path.isfile(_index_path()):
        sys.exit(
            "Title index not found.\n"
            "Build it first:\n"
            '  python scripts/build_title_index.py --src "Copy of  Complete List of Dev Titles.xlsx"'
        )

    output_path = Path(args.output) if args.output else _default_output(input_path)
    print(f"Mapping {input_path} ...")
    stats = map_file(input_path, output_path, args.email_col, args.title_col)
    print(f"[OK] columns: title='{stats['title_col']}' email='{stats['email_col']}'")
    print(f"[OK] rows: {stats['total']:,}")
    print(f"[OK] matched: {stats['matched']:,}")
    print(f"[OK] unmatched / excluded: {stats['unmatched']:,}")
    print(f"[OK] saved -> {stats['output']}")


if __name__ == "__main__":
    main()
