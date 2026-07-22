"""
Raw organization name -> Book of Business (BOB) company mapping.

Uses a client-provided BOB company list with exact lookup and RapidFuzz fuzzy
matching. When no confident match is found the original company name is returned
unchanged.
"""
import functools
import gzip
import os
import pickle
import re
from collections import Counter

from rapidfuzz import fuzz, process

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_INDEX_PATH = os.path.join(_ROOT, "data", "company_index.pkl.gz")

FUZZY_THRESHOLD = int(os.environ.get("COMPANY_FUZZY_THRESHOLD", "88"))
FUZZY_CANDIDATE_LIMIT = int(os.environ.get("COMPANY_FUZZY_CANDIDATE_LIMIT", "2000"))
FUZZY_MAX_POSTING = int(os.environ.get("COMPANY_FUZZY_MAX_POSTING", "15000"))
FUZZY_MAX_SCAN = int(os.environ.get("COMPANY_FUZZY_MAX_SCAN", "80000"))
FUZZY_RERANK_LIMIT = int(os.environ.get("COMPANY_FUZZY_RERANK_LIMIT", "20"))

_index_cache: dict | None = None
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")

# Legal / corporate suffixes stripped before matching (longest first).
_LEGAL_SUFFIXES = (
    " india private limited", " india pvt limited", " india pvt. ltd.", " india pvt ltd",
    " private limited", " pvt. ltd.", " pvt ltd", " pvt. ltd", " limited liability company",
    " incorporated", " corporation",
    " limited", " ltd.", " ltd", " llc", " llp", " plc", " gmbh", " inc.", " inc", " corp.", " corp",
    " co.", " co",
)

# Trailing region modifiers stripped only for alternate lookup attempts.
_REGION_SUFFIXES = (
    " india", " usa", " us", " uk", " uae", " singapore", " australia", " apac", " emea",
)

# Whole-name placeholders that should not be fuzzy-matched to a BOB company.
_JUNK_NAMES = {
    "na", "n/a", "none", "nil", "-", "--", ".", "other", "others",
    "self", "self employed", "freelance", "freelancer", "student", "not applicable",
}


def _tokenize(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2}


def _index_path() -> str:
    return os.environ.get("COMPANY_INDEX_PATH", DEFAULT_INDEX_PATH)


def _load_index() -> dict:
    global _index_cache
    if _index_cache is not None:
        return _index_cache
    path = _index_path()
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Company index not found at {path}. Run: python scripts/build_company_index.py"
        )
    with gzip.open(path, "rb") as f:
        _index_cache = pickle.load(f)
    return _index_cache


def clear_index_cache() -> None:
    """Clear in-memory index (for tests)."""
    global _index_cache
    _index_cache = None
    _lookup_cleaned.cache_clear()


def normalize_company_key(text: str) -> str:
    """Normalize a company name for exact/fuzzy lookup."""
    s = _INVISIBLE_RE.sub("", str(text or ""))
    s = s.strip().strip('"').strip("'")
    if not s or s.lower() == "nan":
        return ""
    s = s.lower()
    s = re.sub(r"\s*&\s*", " and ", s)
    s = re.sub(r"[.,;]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    changed = True
    while changed:
        changed = False
        for suffix in _LEGAL_SUFFIXES:
            if s.endswith(suffix):
                s = s[: -len(suffix)].strip()
                changed = True
                break
    s = re.sub(r"\s+", " ", s).strip(" -./|")
    return s


def _fuzzy_candidate_indices(cleaned: str, index: dict) -> list[int]:
    choices = index["choices"]
    if not choices:
        return []

    token_index = index.get("token_index") or {}
    tokens = _tokenize(cleaned)
    if not tokens or not token_index:
        return list(range(min(FUZZY_CANDIDATE_LIMIT, len(choices))))

    postings = sorted((token_index.get(t, ()) for t in tokens), key=len)
    scores: Counter[int] = Counter()
    scanned = 0
    for posting in postings:
        if scores and len(posting) > FUZZY_MAX_POSTING:
            continue
        scores.update(posting)
        scanned += len(posting)
        if scanned >= FUZZY_MAX_SCAN and scores:
            break

    if not scores:
        return list(range(min(FUZZY_CANDIDATE_LIMIT, len(choices))))

    return [idx for idx, _ in scores.most_common(FUZZY_CANDIDATE_LIMIT)]


def _lookup_variants(cleaned: str) -> list[str]:
    """Normalized keys to try, including region-stripped alternates."""
    variants = [cleaned]
    for suffix in _REGION_SUFFIXES:
        if cleaned.endswith(suffix):
            alt = cleaned[: -len(suffix)].strip()
            if alt and alt not in variants:
                variants.append(alt)
    return variants


@functools.lru_cache(maxsize=8192)
def _lookup_cleaned(cleaned: str) -> str | None:
    """Return BOB company display name for a normalized key, or None."""
    if not cleaned or cleaned in _JUNK_NAMES:
        return None

    index = _load_index()
    exact = index["exact"]
    for variant in _lookup_variants(cleaned):
        if variant in exact:
            return exact[variant]

    choices = index["choices"]
    display_names = index["display_names"]
    if not choices:
        return None

    candidate_idxs = _fuzzy_candidate_indices(cleaned, index)
    candidate_choices = [choices[i] for i in candidate_idxs]
    results = process.extract(
        cleaned,
        candidate_choices,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=FUZZY_THRESHOLD,
        limit=FUZZY_RERANK_LIMIT,
    )
    if not results:
        return None

    qlen = len(cleaned)
    _match_text, _score, local_idx = max(
        results, key=lambda r: (r[1], -abs(len(r[0]) - qlen))
    )
    return display_names[candidate_idxs[local_idx]]


def get_bob_company(raw_company: str) -> str | None:
    """Return matched BOB company name, or None if no confident match."""
    raw = str(raw_company or "")
    if not raw.strip():
        return None
    cleaned = normalize_company_key(raw)
    if not cleaned:
        return None
    return _lookup_cleaned(cleaned)


def map_company(raw_company: str) -> str:
    """
    Map a raw company name to the BOB canonical name.

    Returns the original raw company name unchanged when there is no match.
    """
    raw = str(raw_company or "")
    if not raw.strip():
        return raw
    matched = get_bob_company(raw)
    return matched if matched else raw
