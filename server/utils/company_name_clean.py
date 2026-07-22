"""Clean raw company names from imports and free-text form fields."""
import re

import ftfy

_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_DASH_JUNK_RE = re.compile(r"^[-\u2013\u2014.]+$")
_QUOTE_ONLY_RE = re.compile(r'^["\'\u201c\u201d\u2018\u2019\s]+$')
_NUMERIC_JUNK_RE = re.compile(r"^\d+$")
_LEADING_JUNK_RE = re.compile(r'^[-\u2013\u2014\s@]+')
_TRAILING_JUNK_RE = re.compile(r'[-\u2013\u2014./|\\@]+$')
_REPLACEMENT_RUN_RE = re.compile(r"[\?\uFFFD\ufffe\ufeff\uFFFE]+")
_LATIN1_REPLACEMENT_RE = re.compile(r"(?:\u00ef\u00bf\u00bd)+")
_STUDENT_STATUS_RE = re.compile(
    r"^n/a\b[\s\-–—:]*.*\b(class\s*\d+|school\s+student|student)\b",
    re.IGNORECASE,
)

# UTF-8 bytes misread as Windows-1252 appear as â + € + <third char>.
_MOJIBAKE_REPLACEMENTS = (
    ("\u00e2\u20ac\u0153", "\u201c"),  # â€œ -> "
    ("\u00e2\u20ac\u009d", "\u201d"),  # â€\x9d -> "
    ("\u00e2\u20ac\u02dc", "\u2018"),   # â€˜ -> '
    ("\u00e2\u20ac\u2122", "\u2019"),   # â€™ -> '
    ("\u00e2\u20ac\u201c", "\u2013"),  # â€" -> en dash
    ("\u00e2\u20ac\u201d", "\u2014"),  # â€" -> em dash
    ("\u00e2\u20ac\u0093", "\u2013"),
    ("\u00e2\u20ac\u0094", "\u2014"),
    ("\u00e2\u201e\u00a2", "\u2122"),  # â„¢ -> ™
    ("\u00e2\"\u00a2", "\u2122"),      # â"¢ after ftfy -> ™
    ("\u00c3\u00a9", "\u00e9"),
    ("\u00c3\u00a0", "\u00e0"),
    ("\u00c3\u00a2", "\u00e2"),
)

_JUNK_NAMES = frozenset({
    "na", "n/a", "none", "nil", "-", "--", ".", "other", "others",
    "self", "self employed", "freelance", "freelancer", "student",
    "not applicable", "null", "undefined", "unknown",
})


def _fix_mojibake(text: str) -> str:
    s = text
    for bad, good in _MOJIBAKE_REPLACEMENTS:
        s = s.replace(bad, good)
    return s


def _fix_text_encoding(text: str) -> str:
    return ftfy.fix_text(text, normalization="NFKC")


def _strip_replacement_chars(text: str) -> str:
    s = _LATIN1_REPLACEMENT_RE.sub(" ", text)
    s = re.sub(r"\([\?\uFFFD\s\uFFFE\u00ef\u00bf\u00bd]+\)", "", s)
    s = _REPLACEMENT_RUN_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_smart_quotes(text: str) -> str:
    return (
        text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )


def _strip_wrapping_quotes(text: str) -> str:
    s = text.strip()
    while s:
        before = s
        s = _LEADING_JUNK_RE.sub("", s)
        s = re.sub(r'^["\']+', "", s)
        s = re.sub(r'["\']+$', "", s)
        s = s.strip()
        if s == before:
            break
    return s


def _is_student_status(text: str) -> bool:
    return bool(_STUDENT_STATUS_RE.match(text.strip()))


def clean_company_name(raw: str) -> str:
    """
    Return a display-ready company name with quotes, escape noise, and junk removed.

    Empty string means no usable company name was provided.
    """
    s = _INVISIBLE_RE.sub("", str(raw or ""))
    s = _fix_text_encoding(s)
    s = _fix_mojibake(s)
    s = _normalize_smart_quotes(s)
    s = s.replace("\t", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = _strip_replacement_chars(s)
    s = _strip_wrapping_quotes(s)
    s = re.sub(r"\s+", " ", s).strip()
    s = _TRAILING_JUNK_RE.sub("", s).strip()

    if not s:
        return ""
    if _is_student_status(s):
        return ""
    if _DASH_JUNK_RE.match(s) or _QUOTE_ONLY_RE.match(s) or _NUMERIC_JUNK_RE.match(s):
        return ""
    if _REPLACEMENT_RUN_RE.fullmatch(s.replace(" ", "")):
        return ""
    if s.lower() in _JUNK_NAMES:
        return ""
    return s
