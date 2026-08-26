#!/usr/bin/env python3
"""
Build a trimmed Gen AI APAC dataset with remapped designations.

Takes the BOB-tagged registration export and produces a smaller dataset:

    * every non-India record is kept
    * India is capped at --india-cap rows, keeping all BOB Account == "Yes"
      rows first and filling the remainder with a random sample of the rest
    * each row's designation title is replaced by its closest match in the
      700 job-titles list, keeping the original "( years )" suffix

Usage:
    python scripts/build_gen_ai_sampled_dataset.py
    python scripts/build_gen_ai_sampled_dataset.py --india-cap 5000 --seed 7
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SOURCE = _ROOT / "exports" / "coco_cli_gen_ai_bob_tagged_v2.csv"
DEFAULT_TITLES = _ROOT / "700 Job titles _ C3 _ Gen ai apac - 700 New Job Titles.csv"
DEFAULT_OUTPUT = _ROOT / "exports" / "coco_cli_gen_ai_sampled_mapped.csv"

COUNTRY_COL = "Country"
BOB_COL = "BOB Account"
DESIGNATION_COL = "Designation (Year of exp.)"

# Designations arrive as "Project Manager( 7 )"; the suffix is preserved as-is.
_SUFFIX_RE = re.compile(r"\s*\(\s*[^()]*\s*\)\s*$")

# Below this rapidfuzz score the closest match is coincidental character
# overlap rather than a real job-title relative ("Lecturer" scores 69 against
# "Senior Manager, IT Infrastructure"), so it falls back to a weighted draw.
MATCH_THRESHOLD = 72

# Abbreviations and stack names the fuzzy matcher scores on characters alone;
# keys are casefolded source titles, values are exact entries in the 700 list.
ALIASES = {
    "swe": "Software Engineer",
    "sw engineer": "Software Engineer",
    "sde": "SDE",
    "sde 1": "SDE",
    "sde 2": "SDE",
    "sde-1": "SDE",
    "sde-2": "SDE",
    "sde intern": "SDE",
    "mern stack developer": "Full Stack Developer",
    "mern developer": "Full Stack Developer",
    "mern stack": "Full Stack Developer",
    "fullstack developer": "Full Stack Developer",
    "full-stack developer": "Full Stack Developer",
    "fullstack engineer": "Full Stack Developer",
    "mean stack developer": "Full Stack Developer",
    "programmer": "Software Developer",
    "coder": "Software Developer",
    "ml engineer": "Machine Learning Engineer",
    "ai/ml engineer": "Machine Learning Engineer",
    "ai ml engineer": "Machine Learning Engineer",
    "genai engineer": "Generative AI Engineer",
    "sre": "SRE",
}


def split_designation(value: object) -> tuple[str, str]:
    """Return the (title, suffix) halves of a raw designation cell."""
    text = "" if pd.isna(value) else str(value).strip()
    match = _SUFFIX_RE.search(text)
    if not match:
        return text, ""
    return text[: match.start()].strip(), match.group().strip()


def build_designation_map(
    designations: pd.Series, titles: pd.DataFrame, seed: int
) -> tuple[dict[str, str], pd.DataFrame]:
    """Map each distinct designation title to its closest of the 700 titles."""
    choices = titles["title"].tolist()
    unknown_aliases = sorted(set(ALIASES.values()) - set(choices))
    if unknown_aliases:
        raise SystemExit(f"ALIASES target titles missing from list: {unknown_aliases}")

    unique_titles = sorted({split_designation(v)[0] for v in designations})

    weights = titles["num_title"].astype(float)
    fallback_pool = titles.sample(
        n=len(unique_titles), replace=True, weights=weights, random_state=seed
    )["title"].tolist()

    mapping: dict[str, str] = {}
    audit_rows = []
    for source_title, fallback in zip(unique_titles, fallback_pool):
        alias = ALIASES.get(source_title.casefold())
        if alias:
            mapping[source_title] = alias
            audit_rows.append(
                {
                    "source_title": source_title,
                    "mapped_title": alias,
                    "match_score": 100.0,
                    "match_kind": "alias",
                }
            )
            continue

        hit = (
            process.extractOne(source_title, choices, scorer=fuzz.WRatio)
            if source_title
            else None
        )
        score = hit[1] if hit else 0.0
        is_match = bool(hit and score >= MATCH_THRESHOLD)
        matched = hit[0] if is_match else fallback
        mapping[source_title] = matched
        audit_rows.append(
            {
                "source_title": source_title,
                "mapped_title": matched,
                "match_score": round(score, 1),
                "match_kind": "fuzzy" if is_match else "fallback",
            }
        )

    audit = pd.DataFrame(audit_rows).sort_values("match_score", ascending=False)
    return mapping, audit


def sample_rows(df: pd.DataFrame, india_cap: int, seed: int) -> pd.DataFrame:
    """Keep all non-India rows plus a BOB-first sample of india_cap India rows."""
    is_india = df[COUNTRY_COL].astype(str).str.strip().str.casefold() == "india"
    india = df[is_india]
    is_bob = india[BOB_COL].astype(str).str.strip().str.casefold() == "yes"

    kept = india[is_bob]
    remaining = india_cap - len(kept)
    if remaining < 0:
        raise SystemExit(
            f"--india-cap {india_cap} is below the {len(kept)} India BOB=Yes rows"
        )
    rest = india[~is_bob]
    filler = rest.sample(n=min(remaining, len(rest)), random_state=seed)

    selected = pd.concat([df[~is_india], kept, filler])
    return selected.sort_index()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--titles", type=Path, default=DEFAULT_TITLES)
    parser.add_argument("--india-cap", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    df = pd.read_csv(args.source, dtype=str, keep_default_na=False)
    titles = pd.read_csv(args.titles)
    titles = titles.dropna(subset=["title"]).drop_duplicates(subset=["title"])

    selected = sample_rows(df, args.india_cap, args.seed)

    mapping, audit = build_designation_map(
        selected[DESIGNATION_COL], titles, args.seed
    )
    segments = titles.set_index("title")[["buyer_segment_rollup", "buyer_segment"]]

    def remap(value: object) -> str:
        source_title, suffix = split_designation(value)
        mapped = mapping[source_title]
        return f"{mapped}{suffix}" if suffix else mapped

    selected[DESIGNATION_COL] = selected[DESIGNATION_COL].map(remap)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(args.output, index=False)

    audit = audit.join(segments, on="mapped_title")
    audit_path = args.output.with_name(f"{args.output.stem}_designation_map.csv")
    audit.to_csv(audit_path, index=False)

    is_india = selected[COUNTRY_COL].astype(str).str.strip().str.casefold() == "india"
    bob_yes = selected[BOB_COL].astype(str).str.strip().str.casefold() == "yes"
    print(f"source rows        : {len(df)}")
    print(f"output rows        : {len(selected)}")
    print(f"  India            : {is_india.sum()} (BOB Yes {(is_india & bob_yes).sum()})")
    print(f"  outside India    : {(~is_india).sum()} (BOB Yes {(~is_india & bob_yes).sum()})")
    print(f"distinct titles in : {len(audit)}")
    for kind, count in audit["match_kind"].value_counts().items():
        print(f"  {kind:<15}  : {count}")
    print(f"wrote {args.output}")
    print(f"wrote {audit_path}")


if __name__ == "__main__":
    main()
