"""
Build a compressed pickle index from the Book of Business company list.

By default reads the same BOB list already loaded in the app database
(bob_companies / cohort_2_bob_companies). You can override with --src for a
CSV/XLSX export.

Run from project root:
    python scripts/build_company_index.py
    python scripts/build_company_index.py --cohort 2
    python scripts/build_company_index.py --src data/bob_companies.xlsx
"""
import argparse
import gzip
import os
import pickle
import sys
from collections import defaultdict

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from server.utils.company_map import normalize_company_key, _tokenize  # noqa: E402

DEFAULT_SRC_CANDIDATES = [
    os.path.join(_ROOT, "data", "bob_companies.xlsx"),
    os.path.join(_ROOT, "data", "bob_companies.csv"),
]
DEFAULT_INDEX = os.path.join(_ROOT, "data", "company_index.pkl.gz")
DEFAULT_DUPES = os.path.join(_ROOT, "data", "company_index_duplicates.csv")
DEFAULT_COHORT = int(os.environ.get("BOB_DEFAULT_COHORT", "2"))

_COMPANY_HEADERS = (
    "company_name", "company name", "company", "organization", "organization_name",
    "org", "org name", "book of business", "bob company", "bob",
)


def _norm_header(name: str) -> str:
    return " ".join(str(name or "").strip().lower().replace("_", " ").split())


def _pick_company_column(columns) -> str | None:
    norm_map = {_norm_header(c): c for c in columns}
    for alias in _COMPANY_HEADERS:
        key = _norm_header(alias)
        if key in norm_map:
            return norm_map[key]
    if len(columns) == 1:
        return columns[0]
    for col in columns:
        norm = _norm_header(col)
        if "company" in norm or "organization" in norm or norm == "bob":
            return col
    return None


def _load_dataframe(src: str) -> pd.DataFrame:
    ext = os.path.splitext(src)[1].lower()
    if ext in (".xlsx", ".xls", ".xlsm"):
        return pd.read_excel(src)
    return pd.read_csv(src, encoding="utf-8", on_bad_lines="skip")


def _load_from_database(cohort_id: int) -> tuple[list[str], str]:
    from dotenv import load_dotenv
    from server.app import create_app
    from server.utils.bob_match import cohort_id_to_prefix, get_bob_company_names_with_prefix

    load_dotenv(os.path.join(_ROOT, ".env"))
    prefix = cohort_id_to_prefix(cohort_id)
    table = f"{prefix}bob_companies" if prefix else "bob_companies"

    app = create_app()
    with app.app_context():
        names = get_bob_company_names_with_prefix(prefix)

    if not names:
        raise RuntimeError(
            f"No companies found in {table}. Import the BOB list via the app first "
            "(Import → Book of Business companies)."
        )
    return names, table


def _load_company_names(src: str | None, cohort_id: int) -> tuple[list[str], str, str | None]:
    if src:
        if not os.path.isfile(src):
            sys.exit(f"Source not found: {src}")
        df = _load_dataframe(src)
        company_col = _pick_company_column(list(df.columns))
        if not company_col:
            sys.exit(
                "Could not detect a company-name column.\n"
                f"  found columns: {list(df.columns)}\n"
                f"  expected one of: {_COMPANY_HEADERS}, or a single-column file"
            )
        names = [
            str(v).strip()
            for v in df[company_col].astype("string").tolist()
            if v and str(v).strip() and str(v).lower() != "nan"
        ]
        return names, src, company_col

    names, table = _load_from_database(cohort_id)
    return names, table, None


def build_index(src: str | None, index_path: str, dupes_path: str, cohort_id: int) -> dict:
    company_names, source_label, company_col = _load_company_names(src, cohort_id)

    work = pd.DataFrame({"raw": company_names})
    work["norm"] = work["raw"].map(normalize_company_key)
    before = len(work)
    work = work[(work["norm"] != "") & work["raw"].notna() & (work["raw"] != "")]
    skipped = before - len(work)

    dupes = (
        work.groupby("norm", observed=True)["raw"]
        .nunique()
        .reset_index(name="variant_count")
    )
    dupes = dupes[dupes["variant_count"] > 1]

    exact: dict[str, str] = {}
    choices: list[str] = []
    display_names: list[str] = []
    for _, row in work.drop_duplicates("norm", keep="first").iterrows():
        norm = row["norm"]
        display = str(row["raw"]).strip()
        exact[norm] = display
        choices.append(norm)
        display_names.append(display)

    token_index: dict[str, list[int]] = defaultdict(list)
    for idx, choice in enumerate(choices):
        for token in _tokenize(choice):
            token_index[token].append(idx)

    index = {
        "exact": exact,
        "choices": choices,
        "display_names": display_names,
        "token_index": dict(token_index),
    }

    os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
    with gzip.open(index_path, "wb") as out:
        pickle.dump(index, out, protocol=pickle.HIGHEST_PROTOCOL)

    if len(dupes):
        merged = dupes.merge(
            work.groupby("norm", observed=True)["raw"]
            .apply(lambda s: " | ".join(sorted(set(s))[:5]))
            .reset_index(name="sample_variants"),
            on="norm",
            how="left",
        )
        merged.to_csv(dupes_path, index=False, encoding="utf-8")

    return {
        "source": source_label,
        "company_col": company_col or "(database company_name)",
        "input_rows": before,
        "exact_entries": len(exact),
        "choices": len(choices),
        "duplicate_norm_keys": len(dupes),
        "skipped_rows": skipped,
        "index_path": index_path,
        "dupes_path": dupes_path if len(dupes) else None,
        "cohort_id": None if src else cohort_id,
    }


def main():
    parser = argparse.ArgumentParser(description="Build BOB company fuzzy-match index")
    parser.add_argument(
        "--src",
        help="Optional BOB list file (.xlsx/.csv). Default: load from database.",
    )
    parser.add_argument(
        "--cohort",
        type=int,
        default=DEFAULT_COHORT,
        help=f"Cohort whose bob_companies table to read when using DB (default: {DEFAULT_COHORT})",
    )
    parser.add_argument("--out", default=DEFAULT_INDEX, help="Output pickle.gz path")
    parser.add_argument("--dupes", default=DEFAULT_DUPES, help="Duplicate keys CSV path")
    args = parser.parse_args()

    if args.src:
        print(f"Reading {args.src} ...")
    else:
        print(f"Reading BOB companies from database (cohort {args.cohort}) ...")

    stats = build_index(args.src, args.out, args.dupes, args.cohort)
    print(f"[OK] source: {stats['source']}")
    if stats["cohort_id"] is not None:
        print(f"[OK] cohort: {stats['cohort_id']}")
    print(f"[OK] company column: '{stats['company_col']}'")
    print(f"[OK] input rows: {stats['input_rows']:,}")
    print(f"[OK] exact entries: {stats['exact_entries']:,}")
    print(f"[OK] skipped rows: {stats['skipped_rows']:,}")
    print(f"[OK] duplicate normalized keys: {stats['duplicate_norm_keys']:,}")
    print(f"[OK] index written -> {stats['index_path']}")
    if stats["dupes_path"]:
        print(f"[OK] duplicates logged -> {stats['dupes_path']}")


if __name__ == "__main__":
    main()
