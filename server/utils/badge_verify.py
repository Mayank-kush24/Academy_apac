"""
Unified public badge verification for Google Cloud Skills Boost / Google Skills
and Credly. Pure library (no Flask/DB).

Public entry: verify_badge(url, expected_course_name, platform=..., min_date=...)
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from server.utils.skillboost_verify import (
    DEFAULT_RATE_LIMIT_DELAY,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    USER_AGENTS,
)

# --- expected course cleaning (problem_statement column) ---

_TRACK_PREFIX_RE = re.compile(
    r"^\s*\*?\s*(?:\[(?:Professional|Student)\]\s*)?Track\s+\d+\s*-\s*",
    re.IGNORECASE,
)


def clean_expected_course(text: Any) -> str:
    """
    Strip tier/track prefixes like [Professional] Track X - or [Student] Track Y -
    and trailing commas/whitespace.
    """
    if text is None:
        return ""
    s = str(text).strip()
    s = _TRACK_PREFIX_RE.sub("", s)
    s = s.rstrip(" ,").strip()
    return s


# --- course name normalization + fuzzy match ---

_NON_ALNUM = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_course_name(s: str) -> str:
    if not s:
        return ""
    t = _NON_ALNUM.sub(" ", str(s).lower())
    t = _WS.sub(" ", t).strip()
    return t


def _core_name(s: str) -> str:
    """Remove trailing parenthetical segments for looser matching."""
    n = normalize_course_name(s)
    # strip one trailing (...)
    n = re.sub(r"\s*\([^)]*\)\s*$", "", n).strip()
    return _WS.sub(" ", n)


def _word_set(s: str) -> set:
    return {w for w in normalize_course_name(s).split() if len(w) > 1}


def match_course_names(expected: str, actual: str) -> bool:
    """
    Fuzzy match: exact normalized, contains either way, core-name contains,
    or word-overlap ratio >= 0.6 on the smaller word set.
    """
    e = normalize_course_name(expected)
    a = normalize_course_name(actual)
    if not e or not a:
        return False
    if e == a:
        return True
    if e in a or a in e:
        return True
    ec = _core_name(expected)
    ac = _core_name(actual)
    if ec and ac and (ec in ac or ac in ec or ec == ac):
        return True
    we, wa = _word_set(expected), _word_set(actual)
    if not we or not wa:
        return False
    inter = len(we & wa)
    smaller = min(len(we), len(wa))
    if smaller == 0:
        return False
    return (inter / smaller) >= 0.6


# --- HTTP ---

def make_request(
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    session=None,
) -> Tuple[int, str, str]:
    """
    GET url with rotating User-Agent, backoff on 429 / transient errors.
    Returns (status_code, text, final_url).
    Raises requests.RequestException on exhausted retries.
    `session` may be a requests.Session() or None (uses requests module .get).
    """
    import requests

    http = session if session is not None else requests
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        headers = {
            "User-Agent": USER_AGENTS[attempt % len(USER_AGENTS)],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
        }
        try:
            resp = http.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if resp.status_code == 429:
                time.sleep((attempt + 1) * DEFAULT_RATE_LIMIT_DELAY)
                continue
            return resp.status_code, resp.text or "", getattr(resp, "url", url) or url
        except requests.RequestException as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep((attempt + 1) * DEFAULT_RATE_LIMIT_DELAY)
                continue
            raise
    if last_exc:
        raise last_exc
    return 0, "", url


# --- date parsing ---

_DATE_ISO = re.compile(r"(\d{4}-\d{2}-\d{2})")
_DATE_US = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b",
    re.I,
)
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_date_from_text(text: str) -> Optional[date]:
    if not text or not str(text).strip():
        return None
    s = str(text).strip()
    m = _DATE_ISO.search(s)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            pass
    m2 = _DATE_US.search(s)
    if m2:
        mon = _MONTH_MAP.get(m2.group(1).lower()[:3])
        if mon:
            try:
                return date(int(m2.group(3)), mon, int(m2.group(2)))
            except ValueError:
                pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s[:32].strip(), fmt).date()
        except ValueError:
            continue
    return None


def _date_to_iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


# --- Google ---

GOOGLE_HOSTS = frozenset({"www.cloudskillsboost.google", "www.skills.google"})
GOOGLE_BADGE_PATH_RE = re.compile(
    r"^/public_profiles/[a-zA-Z0-9\-]+/badges/\d+/?$",
)


class GoogleSkillboostVerifier:
    ALLOWED_HOSTS = GOOGLE_HOSTS
    PATH_RE = GOOGLE_BADGE_PATH_RE

    @staticmethod
    def validate_url(parsed) -> Tuple[bool, str]:
        host = (parsed.netloc or "").lower()
        if not host:
            return False, "Invalid host (empty)"
        if host not in GOOGLE_HOSTS:
            return False, "Incorrect Domain (must be www.cloudskillsboost.google or www.skills.google)"
        path = parsed.path or ""
        if not GoogleSkillboostVerifier.PATH_RE.match(path):
            return False, "Incorrect Path (must match /public_profiles/{id}/badges/{numeric_id})"
        return True, ""

    @staticmethod
    def extract_course(html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        h1_bt = soup.select_one("h1.badge-title")
        if h1_bt and h1_bt.get_text(strip=True):
            return h1_bt.get_text(strip=True)
        if soup.title and soup.title.string:
            t = soup.title.string.strip()
            if t:
                return t
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return str(og["content"]).strip()
        for tag in ("h1", "h2"):
            el = soup.find(tag)
            if el and el.get_text(strip=True):
                return el.get_text(strip=True)
        return None

    @staticmethod
    def extract_completion_date(html: str) -> Optional[date]:
        soup = BeautifulSoup(html, "html.parser")
        for sel in ("span.completed-at", ".completed-at"):
            el = soup.select_one(sel)
            if el:
                d = parse_date_from_text(el.get_text(" ", strip=True))
                if d:
                    return d
        # ql-badge JSON in script tags
        for script in soup.find_all("script"):
            txt = script.string or script.get_text() or ""
            if "completedAt" in txt or "completed_at" in txt:
                for key in ("completedAt", "completed_at"):
                    m = re.search(r'"%s"\s*:\s*"([^"]+)"' % re.escape(key), txt)
                    if m:
                        d = parse_date_from_text(m.group(1))
                        if d:
                            return d
        for div in soup.select(".public-profile-badge [class*='date'], .public-profile-badge div"):
            d = parse_date_from_text(div.get_text(" ", strip=True))
            if d:
                return d
        d = parse_date_from_text(html)
        return d


# --- Credly ---

CREDLY_HOSTS = frozenset({"www.credly.com"})
CREDLY_BADGE_PATH_RE = re.compile(
    r"^/badges/[a-zA-Z0-9\-]+(?:/public_url)?/?$",
)
CREDLY_BADGE_ID_RE = re.compile(r"/badges/([a-zA-Z0-9\-]+)")


class CredlyVerifier:
    ALLOWED_HOSTS = CREDLY_HOSTS
    PATH_RE = CREDLY_BADGE_PATH_RE

    @staticmethod
    def validate_url(parsed) -> Tuple[bool, str]:
        host = (parsed.netloc or "").lower()
        if not host:
            return False, "Invalid host (empty)"
        if host not in CREDLY_HOSTS:
            return False, "Incorrect Domain (must be www.credly.com)"
        path = parsed.path or ""
        if not CredlyVerifier.PATH_RE.match(path):
            return False, "Incorrect Path (must match /badges/{id}/public_url or /badges/{id})"
        return True, ""

    @staticmethod
    def extract_course(html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            c = str(og["content"]).strip()
            if c:
                return c
        if soup.title and soup.title.string:
            t = soup.title.string.strip()
            if t:
                return t
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            return h1.get_text(strip=True)
        return None

    @staticmethod
    def extract_completion_date_from_html(html: str) -> Optional[date]:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            raw = script.string or script.get_text() or ""
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                for key in ("dateIssued", "datePublished"):
                    v = item.get(key)
                    if v:
                        d = parse_date_from_text(str(v))
                        if d:
                            return d
        for prop in ("article:published_time", "og:updated_time"):
            m = soup.find("meta", property=prop)
            if m and m.get("content"):
                d = parse_date_from_text(str(m["content"]))
                if d:
                    return d
        return None

    @staticmethod
    def badge_id_from_url(url: str) -> Optional[str]:
        m = CREDLY_BADGE_ID_RE.search(urlparse(url).path or "")
        return m.group(1) if m else None

    @classmethod
    def extract_completion_date(
        cls,
        html: str,
        page_url: str,
        *,
        fetch_json: Optional[Callable[[str], Tuple[int, str]]] = None,
    ) -> Optional[date]:
        d = cls.extract_completion_date_from_html(html)
        if d:
            return d
        bid = cls.badge_id_from_url(page_url)
        if not bid or fetch_json is None:
            return None
        api_url = "https://www.credly.com/api/v2/badges/%s.json" % bid
        try:
            status, body = fetch_json(api_url)
        except Exception:
            return None
        if status != 200 or not body:
            return None
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return None
        issued = payload.get("issued_at") or payload.get("issued_on")
        if issued:
            return parse_date_from_text(str(issued))
        return None


def _detect_platform(parsed) -> Optional[str]:
    host = (parsed.netloc or "").lower()
    if host in GOOGLE_HOSTS:
        return "google"
    if host in CREDLY_HOSTS:
        return "credly"
    return None


def verify_badge(
    url: str,
    expected_course: str,
    *,
    platform: Optional[str] = None,
    min_date: Optional[date] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    session=None,
) -> dict:
    """
    Verify a public badge URL against expected course name and optional minimum completion date.

    Returns dict with keys: status ('verified'|'failed'|'pending'), valid (bool),
    platform, url, expected_course, actual_course, completion_date (ISO date str or None),
    remarks, checked_at (ISO UTC).
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    base = {
        "status": "failed",
        "valid": False,
        "platform": None,
        "url": (str(url).strip() if url else "") or "",
        "expected_course": clean_expected_course(expected_course),
        "actual_course": None,
        "completion_date": None,
        "remarks": "",
        "checked_at": checked_at,
    }

    if not isinstance(url, str) or not str(url).strip():
        base["remarks"] = "Empty or invalid URL"
        return base

    url = str(url).strip()
    try:
        parsed = urlparse(url)
    except Exception as e:
        base["remarks"] = "URL parsing error: %s" % str(e)
        return base

    pf = (platform or "").strip().lower() if platform else None
    detected = _detect_platform(parsed)
    if pf not in (None, "", "google", "credly"):
        base["remarks"] = "Invalid platform parameter (use google, credly, or omit for auto-detect)"
        return base
    if pf in ("google", "credly") and detected and detected != pf:
        base["remarks"] = "URL host does not match requested platform"
        return base
    use_platform = pf if pf in ("google", "credly") else detected
    base["platform"] = use_platform

    if use_platform is None:
        base["remarks"] = "Unsupported badge host (must be Google Skills Boost or www.credly.com)"
        return base

    if use_platform == "google":
        ok, msg = GoogleSkillboostVerifier.validate_url(parsed)
        verifier = GoogleSkillboostVerifier
    else:
        ok, msg = CredlyVerifier.validate_url(parsed)
        verifier = CredlyVerifier

    if not ok:
        base["remarks"] = msg
        return base

    import requests

    own_session = None
    sess = session
    if sess is None:
        own_session = requests.Session()
        sess = own_session

    try:
        status, html, final_url = make_request(url, timeout=timeout, retries=retries, session=sess)
    except requests.RequestException as e:
        base["status"] = "pending"
        base["valid"] = False
        base["remarks"] = "Pending: page unreachable (%s)" % str(e)[:120]
        if own_session is not None:
            try:
                own_session.close()
            except Exception:
                pass
        return base

    if status != 200:
        base["status"] = "pending"
        base["valid"] = False
        base["remarks"] = "Pending: HTTP status %s (expected 200)" % status
        if own_session is not None:
            try:
                own_session.close()
            except Exception:
                pass
        return base

    actual = verifier.extract_course(html)
    base["actual_course"] = actual

    expected_clean = clean_expected_course(expected_course)
    if not expected_clean:
        base["remarks"] = "Failed: could not derive expected course name from problem statement"
        if own_session is not None:
            try:
                own_session.close()
            except Exception:
                pass
        return base

    if not actual:
        base["status"] = "pending"
        base["valid"] = False
        base["remarks"] = "Pending: could not parse badge title from page"
        if own_session is not None:
            try:
                own_session.close()
            except Exception:
                pass
        return base

    if not match_course_names(expected_clean, actual):
        base["remarks"] = "Course mismatch: expected %r, badge shows %r" % (expected_clean, actual)
        if own_session is not None:
            try:
                own_session.close()
            except Exception:
                pass
        return base

    if use_platform == "google":
        comp = GoogleSkillboostVerifier.extract_completion_date(html)
    else:

        def _fetch_json(api_url: str) -> Tuple[int, str]:
            st, body, _ = make_request(api_url, timeout=timeout, retries=retries, session=sess)
            return st, body

        comp = CredlyVerifier.extract_completion_date(html, final_url or url, fetch_json=_fetch_json)

    base["completion_date"] = _date_to_iso(comp)

    if min_date is not None:
        if comp is None:
            base["remarks"] = "Failed: minimum completion date was set but badge completion date could not be parsed"
            if own_session is not None:
                try:
                    own_session.close()
                except Exception:
                    pass
            return base
        if comp < min_date:
            base["remarks"] = "Completed before cutoff (%s < %s)" % (_date_to_iso(comp), _date_to_iso(min_date))
            if own_session is not None:
                try:
                    own_session.close()
                except Exception:
                    pass
            return base

    base["status"] = "verified"
    base["valid"] = True
    base["remarks"] = "Verified"
    if own_session is not None:
        try:
            own_session.close()
        except Exception:
            pass
    return base
