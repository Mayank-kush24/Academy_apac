"""
Build a compressed pickle index from the authoritative client title reference.

The reference is the "Complete List of Dev Titles" workbook (or any CSV/Excel)
holding one row per observed job title with its buyer segment:

    title                -> the raw job-title string (the lookup key + display)
    buyer_segment        -> the broad category (one of 7)  e.g. "Technology End User"
    buyer_segment_rollup -> optional rollup (Decision Maker / Practitioner)
    num_title            -> optional frequency (used to resolve conflicts)

Legacy CSVs with "Sub category" / "Broad category" headers are still supported.

When the same normalized title maps to several broad categories, the category
with the highest total `num_title` wins (most frequent usage), which is far more
robust than first-seen-wins on a 1M+ row corpus.

Run from project root:
    python scripts/build_title_index.py --src "Copy of  Complete List of Dev Titles.xlsx"
    python scripts/build_title_index.py            # uses default reference
"""
import argparse
import gzip
import os
import pickle
import re
import sys
from collections import defaultdict

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from server.utils.title_map import _clean_text, _tokenize  # noqa: E402

DEFAULT_SRC_CANDIDATES = [
    os.path.join(_ROOT, "Copy of  Complete List of Dev Titles.xlsx"),
    os.path.join(_ROOT, "data", "client_title_reference.csv"),
]
DEFAULT_INDEX = os.path.join(_ROOT, "data", "title_index.pkl.gz")
DEFAULT_CONFLICTS = os.path.join(_ROOT, "data", "title_index_conflicts.csv")

# Header aliases (normalized: lowercased, underscores/spaces collapsed).
_TITLE_HEADERS = ("title", "sub category", "sub_category", "raw title", "designation")
_BROAD_HEADERS = ("buyer_segment", "buyer segment", "broad category", "broad_category")
_COUNT_HEADERS = ("num_title", "count", "frequency", "freq", "n")
_ROLLUP_HEADERS = ("buyer_segment_rollup", "buyer segment rollup", "rollup")

# Strip zero-width / bidi control characters that pollute scraped titles.
_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")


def _default_src() -> str:
    for cand in DEFAULT_SRC_CANDIDATES:
        if os.path.isfile(cand):
            return cand
    return DEFAULT_SRC_CANDIDATES[0]


def _norm_header(name: str) -> str:
    return " ".join(str(name or "").strip().lower().replace("_", " ").split())


def _pick_column(columns, aliases):
    norm_map = {_norm_header(c): c for c in columns}
    for alias in aliases:
        key = _norm_header(alias)
        if key in norm_map:
            return norm_map[key]
    return None


def _display_sub(raw: str) -> str:
    """Clean a raw title for display: drop invisibles/form-noise, title-case."""
    s = _INVISIBLE_RE.sub("", str(raw or ""))
    s = re.sub(r"\(\s*[\d.]+\s*\)", "", s)  # strip form artifacts like "( 5 )"
    s = re.sub(r"\s+", " ", s).strip(" \t-,./|")
    if not s:
        return s
    return s.title()


def _load_dataframe(src: str) -> pd.DataFrame:
    ext = os.path.splitext(src)[1].lower()
    if ext in (".xlsx", ".xls", ".xlsm"):
        return pd.read_excel(src)
    return pd.read_csv(src, encoding="utf-8", on_bad_lines="skip")


def build_index(src: str, index_path: str, conflicts_path: str) -> dict:
    if not os.path.isfile(src):
        sys.exit(f"Source not found: {src}")

    df = _load_dataframe(src)
    title_col = _pick_column(df.columns, _TITLE_HEADERS)
    broad_col = _pick_column(df.columns, _BROAD_HEADERS)
    count_col = _pick_column(df.columns, _COUNT_HEADERS)
    if not title_col or not broad_col:
        sys.exit(
            "Could not detect required columns.\n"
            f"  found columns: {list(df.columns)}\n"
            f"  need a title column ({_TITLE_HEADERS}) and "
            f"a broad column ({_BROAD_HEADERS})"
        )

    work = pd.DataFrame({
        "raw": df[title_col].astype("string"),
        "broad": df[broad_col].astype("string").str.strip(),
    })
    work["count"] = (
        pd.to_numeric(df[count_col], errors="coerce").fillna(1).clip(lower=1)
        if count_col else 1
    )
    work["norm"] = work["raw"].map(_clean_text)

    before = len(work)
    work = work[(work["norm"] != "") & work["broad"].notna() & (work["broad"] != "")]
    skipped = before - len(work)

    # Winning broad category per normalized title = highest total frequency.
    broad_weight = (
        work.groupby(["norm", "broad"], observed=True)["count"]
        .sum()
        .reset_index()
        .sort_values(["norm", "count"], ascending=[True, False])
    )
    distinct_broads = broad_weight.groupby("norm", observed=True)["broad"].nunique()
    conflict_norms = set(distinct_broads[distinct_broads > 1].index)
    winners = broad_weight.drop_duplicates("norm", keep="first")
    norm_to_broad = dict(zip(winners["norm"], winners["broad"]))

    # Representative display string per normalized title = most frequent variant.
    work["display"] = work["raw"].map(_display_sub)
    work = work[work["display"] != ""]
    disp_weight = (
        work.groupby(["norm", "display"], observed=True)["count"]
        .sum()
        .reset_index()
        .sort_values(["norm", "count"], ascending=[True, False])
        .drop_duplicates("norm", keep="first")
    )
    norm_to_display = dict(zip(disp_weight["norm"], disp_weight["display"]))

    exact: dict[str, tuple[str, str]] = {}
    choices: list[str] = []
    choice_meta: list[tuple[str, str]] = []
    for norm, broad in norm_to_broad.items():
        display = norm_to_display.get(norm) or norm.title()
        exact[norm] = (display, broad)
        choices.append(norm)
        choice_meta.append((display, broad))

    token_index: dict[str, list[int]] = defaultdict(list)
    for idx, choice in enumerate(choices):
        for token in _tokenize(choice):
            token_index[token].append(idx)

    index = {
        "exact": exact,
        "choices": choices,
        "choice_meta": choice_meta,
        "token_index": dict(token_index),
    }

    os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
    with gzip.open(index_path, "wb") as out:
        pickle.dump(index, out, protocol=pickle.HIGHEST_PROTOCOL)

    if conflict_norms:
        conflict_rows = broad_weight[broad_weight["norm"].isin(conflict_norms)]
        conflict_rows.to_csv(conflicts_path, index=False, encoding="utf-8")

    return {
        "source": src,
        "title_col": title_col,
        "broad_col": broad_col,
        "count_col": count_col or "(none, assumed 1)",
        "input_rows": before,
        "exact_entries": len(exact),
        "choices": len(choices),
        "conflicts": len(conflict_norms),
        "skipped_rows": skipped,
        "index_path": index_path,
        "conflicts_path": conflicts_path if conflict_norms else None,
    }


def main():
    parser = argparse.ArgumentParser(description="Build client title fuzzy-match index")
    parser.add_argument("--src", default=_default_src(),
                        help="Input reference (.xlsx/.xls/.csv)")
    parser.add_argument("--out", default=DEFAULT_INDEX, help="Output pickle.gz path")
    parser.add_argument("--conflicts", default=DEFAULT_CONFLICTS, help="Conflicts CSV path")
    args = parser.parse_args()

    print(f"Reading {args.src} ...")
    stats = build_index(args.src, args.out, args.conflicts)
    print(f"[OK] source columns: title='{stats['title_col']}' "
          f"broad='{stats['broad_col']}' count='{stats['count_col']}'")
    print(f"[OK] input rows: {stats['input_rows']:,}")
    print(f"[OK] exact entries: {stats['exact_entries']:,}")
    print(f"[OK] fuzzy choices: {stats['choices']:,}")
    print(f"[OK] skipped rows: {stats['skipped_rows']:,}")
    print(f"[OK] conflicts (highest-frequency wins): {stats['conflicts']:,}")
    print(f"[OK] index written -> {stats['index_path']}")
    if stats["conflicts_path"]:
        print(f"[OK] conflicts logged -> {stats['conflicts_path']}")


if __name__ == "__main__":
    main()
