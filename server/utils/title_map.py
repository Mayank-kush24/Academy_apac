"""
Designation -> sub_category and broad_category mapping (Cohort 2).

Uses a client-provided title reference index (~1M titles) with exact lookup
and RapidFuzz fuzzy matching (token-index pre-filter for performance).
"""
import functools
import gzip
import os
import pickle
import re
from collections import Counter

from rapidfuzz import fuzz, process

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_INDEX_PATH = os.path.join(_ROOT, "data", "title_index.pkl.gz")

FUZZY_THRESHOLD = int(os.environ.get("TITLE_FUZZY_THRESHOLD", "85"))
FUZZY_CANDIDATE_LIMIT = int(os.environ.get("TITLE_FUZZY_CANDIDATE_LIMIT", "3000"))
# A token whose posting list is larger than this is treated as non-discriminative
# (e.g. "engineer", "manager") and skipped once rarer tokens already yielded
# candidates. Keeps fuzzy lookup fast on million-row reference corpora.
FUZZY_MAX_POSTING = int(os.environ.get("TITLE_FUZZY_MAX_POSTING", "40000"))
# Hard cap on total posting entries scanned per query.
FUZZY_MAX_SCAN = int(os.environ.get("TITLE_FUZZY_MAX_SCAN", "120000"))
# Number of top fuzzy hits to re-rank by length closeness before choosing one.
FUZZY_RERANK_LIMIT = int(os.environ.get("TITLE_FUZZY_RERANK_LIMIT", "25"))

#: Seniority signal for compound titles: these outrank end-user roles.
DECISION_MAKER_CATEGORIES = frozenset({"Information Decision Maker"})

BROAD_CATEGORIES = frozenset({
    "Data End User",
    "Information End User",
    "Product End User",
    "Technology End User",
    "Security End User",
    "Information Decision Maker",
    "Operations End User",
})

# Legacy export kept for tests / callers that reference taxonomy broad groups.
CATEGORY_MAP = {broad: [] for broad in BROAD_CATEGORIES}

_index_cache: dict | None = None
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# Honorifics / placeholders / non-informative tokens that carry no role signal.
_JUNK_TOKENS = {
    "mr", "ms", "mrs", "dr", "miss", "sir", "madam",
    "na", "n/a", "none", "no", "nil", "--", "-", ".",
    "required", "title", "self", "me", "i", "ab", "own", "yes",
    "test", "abc", "xyz", "asdf", "demo",
}

# Academic degrees (when the "designation" is actually a qualification).
_DEGREE_RE = re.compile(
    r"\b(bachelor|master|diploma|b\.?e\.?|b\.?tech|m\.?tech|b\.?sc|m\.?sc|"
    r"mba|bca|mca|ph\.?d|b\.?com|m\.?com|b\.?a|m\.?a)\b",
    re.IGNORECASE,
)


def _tokenize(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2}


def _index_path() -> str:
    return os.environ.get("TITLE_INDEX_PATH", DEFAULT_INDEX_PATH)


def _load_index() -> dict:
    global _index_cache
    if _index_cache is not None:
        return _index_cache
    path = _index_path()
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Title index not found at {path}. Run: python scripts/build_title_index.py"
        )
    with gzip.open(path, "rb") as f:
        _index_cache = pickle.load(f)
    return _index_cache


def _fuzzy_candidate_indices(cleaned: str, index: dict) -> list[int]:
    """Narrow fuzzy search to titles sharing tokens with the query.

    Posting lists are visited rarest-first so discriminative tokens drive
    candidate selection. Very common tokens are skipped once we already have
    candidates, and total work is capped, keeping each lookup fast even when
    the reference corpus holds 1M+ titles.
    """
    choices = index["choices"]
    if not choices:
        return []

    token_index = index.get("token_index") or {}
    tokens = _tokenize(cleaned)
    if not tokens or not token_index:
        return list(range(min(FUZZY_CANDIDATE_LIMIT, len(choices))))

    postings = sorted(
        (token_index.get(t, ()) for t in tokens),
        key=len,
    )

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


def _normalize_designation(text):
    """Strip form noise (e.g. 'Owner( 5 )', 'Analyst( 2.5 )', honorifics) before matching."""
    s = str(text or "").strip()
    if not s or s.lower() == "nan":
        return ""
    s = re.sub(r"\(\s*[\d.]+\s*\)", "", s)
    s = re.sub(r"^(mr|ms|mrs|dr|miss)\.?\s+", "", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def _clean_text(text):
    s = _normalize_designation(text)
    if not s:
        return ""
    if not re.search(r"[a-z0-9]", s.lower()):
        return ""
    return re.sub(r"\s+", " ", s.lower()).rstrip(" ,./|")


def is_excluded_title(title: str) -> bool:
    """True for blanks, students, freelancers, bare degrees, and junk placeholders."""
    t = _clean_text(title)
    if not t or t in _JUNK_TOKENS:
        return True
    if re.search(r"\bstudent\b", t):
        return True
    if re.search(r"\bfreelancer\b", t):
        return True
    if _DEGREE_RE.search(t) and not re.search(
        r"\b(engineer|developer|analyst|manager|officer|executive|"
        r"consultant|designer|scientist|architect|lead|specialist)\b",
        t,
    ):
        return True
    return False


@functools.lru_cache(maxsize=8192)
def _lookup_cleaned(cleaned: str) -> tuple[str | None, str | None]:
    """Map normalized designation to (sub_category, broad_category) or (None, None)."""
    if not cleaned:
        return None, None

    index = _load_index()
    exact = index["exact"]
    if cleaned in exact:
        return exact[cleaned]

    choices = index["choices"]
    choice_meta = index["choice_meta"]
    if not choices:
        return None, None

    candidate_idxs = _fuzzy_candidate_indices(cleaned, index)
    candidate_choices = [choices[i] for i in candidate_idxs]
    results = process.extract(
        cleaned,
        candidate_choices,
        scorer=fuzz.token_set_ratio,
        score_cutoff=FUZZY_THRESHOLD,
        limit=FUZZY_RERANK_LIMIT,
    )
    if not results:
        return None, None

    # token_set_ratio scores a long noisy title 100 whenever the query is a
    # subset of it, so re-rank the top candidates: keep the highest score but
    # break ties toward the title closest in length to the query (i.e. the most
    # concise canonical match rather than a verbose scraped variant).
    qlen = len(cleaned)
    _match_text, _score, local_idx = max(
        results, key=lambda r: (r[1], -abs(len(r[0]) - qlen))
    )
    return choice_meta[candidate_idxs[local_idx]]


_SPLIT_RE = re.compile(r"\s*(?:[,&/|+]|\band\b)\s*", re.IGNORECASE)


def _title_parts(cleaned: str) -> list[str]:
    """Split a compound designation ("ceo, co-founder") into candidate titles."""
    parts = (p.strip(" -.") for p in _SPLIT_RE.split(cleaned))
    return [p for p in parts if len(re.sub(r"[^a-z0-9]", "", p)) >= 2]


@functools.lru_cache(maxsize=8192)
def _lookup_compound(cleaned: str) -> tuple[str | None, str | None]:
    """
    Resolve a compound designation from its parts.

    Only reached once the whole string has failed, so legitimate comma-bearing titles
    ("manager, information technology") still match intact and are never split.

    Parts are resolved against the exact index only. Fuzzy matching a short fragment is
    actively misleading — "ceo" scores a perfect token_set_ratio against "assistante
    ceo", and free text splits into words that match unrelated titles — so a part that
    is not a known title on its own is skipped rather than guessed at. Where several
    parts resolve, a decision-maker role wins over an end-user one.
    """
    parts = _title_parts(cleaned)
    if len(parts) < 2:
        return None, None
    exact = _load_index()["exact"]
    best: tuple[str, str] | None = None
    best_rank: tuple[int, int] | None = None
    for pos, part in enumerate(parts):
        hit = exact.get(part)
        if hit is None:
            continue
        sub, broad = hit
        rank = (0 if broad in DECISION_MAKER_CATEGORIES else 1, pos)
        if best_rank is None or rank < best_rank:
            best, best_rank = (sub, broad), rank
    return best if best is not None else (None, None)


def map_title(raw_title: str):
    """
    Map a designation to (sub_category, broad_category).

    Strategy: exact client index lookup -> fuzzy match against client corpus ->
    split compound titles and match on the strongest part.
    Returns ("Unclassified", "Unclassified") when no match meets the threshold.
    """
    cleaned = _clean_text(raw_title)
    if not cleaned:
        return "Unclassified", "Unclassified"
    sub, broad = _lookup_cleaned(cleaned)
    if sub is None or broad is None:
        sub, broad = _lookup_compound(cleaned)
    if sub is None or broad is None:
        return "Unclassified", "Unclassified"
    return sub, broad


def get_title_categories(raw_title: str):
    """Return (sub_category, broad_category) or (None, None) if excluded/blank."""
    if is_excluded_title(raw_title):
        return None, None
    sub, broad = map_title(raw_title)
    if sub == "Unclassified":
        return None, None
    return sub, broad
