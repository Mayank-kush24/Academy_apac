#!/usr/bin/env python3
"""Clean c2_company_names.csv — strip quotes, mojibake, and junk values."""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from server.utils.company_name_clean import clean_company_name  # noqa: E402

DEFAULT_INPUT = _ROOT / "c2_company_names.csv"
DEFAULT_OUTPUT = _ROOT / "c2_company_names_cleaned.csv"


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("Input file has no header row.")
        return list(reader.fieldnames), list(reader)


def _detect_column(fieldnames: list[str], aliases: frozenset[str]) -> str | None:
    norm_map = {" ".join(name.strip().lower().replace("_", " ").split()) for name in fieldnames}
    for name in fieldnames:
        norm = " ".join(name.strip().lower().replace("_", " ").split())
        if norm in aliases:
            return name
    return None


def clean_file(input_path: Path, output_path: Path) -> dict[str, int]:
    fieldnames, rows = _read_rows(input_path)
    email_col = _detect_column(fieldnames, frozenset({"email", "e-mail", "mail"}))
    company_col = _detect_column(fieldnames, frozenset({"company name", "company", "organization"}))
    if not email_col or not company_col:
        raise ValueError(f"Could not detect email/company columns in {fieldnames}")

    stats: Counter[str] = Counter()
    out_rows: list[dict[str, str]] = []
    for row in rows:
        raw = row.get(company_col, "") or ""
        cleaned = clean_company_name(raw)
        if raw.strip() and not cleaned:
            stats["emptied_junk"] += 1
        elif raw.strip() != cleaned:
            stats["cleaned"] += 1
        else:
            stats["unchanged"] += 1
        out_rows.append({email_col: row.get(email_col, ""), company_col: cleaned})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[email_col, company_col])
        writer.writeheader()
        writer.writerows(out_rows)

    stats["total"] = len(rows)
    stats["non_empty_after"] = sum(1 for r in out_rows if (r.get(company_col) or "").strip())
    return dict(stats)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    stats = clean_file(args.input, args.output)
    print(f"Wrote {args.output}")
    print(
        f"Rows: {stats['total']} | cleaned: {stats['cleaned']} | "
        f"junk->empty: {stats['emptied_junk']} | unchanged: {stats['unchanged']} | "
        f"non-empty after: {stats['non_empty_after']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
