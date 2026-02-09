"""
Skill Lab / Skillboost profile URL verification.
Aligned with verify_skillboost_profile_csv.py: same domains, path, retries, rate limit.
Shared by scripts/verify_skillboost.py and the import verify API.
"""
import random
import time
from urllib.parse import urlparse

# Default settings (aligned with verify_skillboost_profile_csv.py)
DEFAULT_TIMEOUT = 10
DEFAULT_RETRIES = 3
DEFAULT_RATE_LIMIT_DELAY = 2.5  # used on 429 or retry

# Domains allowed for Google Skills Boost profile (must match; reference uses these without .com)
VALID_DOMAINS = ["www.cloudskillsboost.google", "www.skills.google"]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def verify_profile_url(
    url,
    timeout=DEFAULT_TIMEOUT,
    retries=DEFAULT_RETRIES,
    session=None,
):
    """
    Verify a Google Skills Boost / Skillboost profile URL.
    Same logic as verify_skillboost_profile_csv.py: domain check, path /public_profiles/,
    GET with retries, rate limit on 429, success = 200 and 'public_profiles' in final URL.
    Returns (is_valid: bool, remarks: str).
    """
    if not isinstance(url, str) or not str(url).strip():
        return False, "Empty or Invalid URL"

    url = str(url).strip()

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, "URL parsing error: %s" % str(e)

    netloc = (parsed.netloc or "").lower()
    if not netloc:
        return False, "Invalid host"

    # Domain must be one of VALID_DOMAINS (e.g. www.cloudskillsboost.google or www.skills.google)
    if not any(d in netloc for d in VALID_DOMAINS):
        return False, "Incorrect Domain (must be %s)" % " or ".join(VALID_DOMAINS)

    path = parsed.path or ""
    if not path.startswith("/public_profiles/"):
        return False, "Incorrect Path (must start with /public_profiles/)"

    # Prefer requests if available (same as CSV script)
    try:
        import requests
    except ImportError:
        return _verify_with_urllib(url, timeout, retries)

    http = session if session is not None else requests
    for attempt in range(retries):
        try:
            headers = {
                "User-Agent": USER_AGENTS[attempt % len(USER_AGENTS)],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
            }
            resp = http.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if resp.status_code == 200 and "public_profiles" in resp.url:
                return True, "Valid Profile"
            if resp.status_code == 429:
                time.sleep((attempt + 1) * DEFAULT_RATE_LIMIT_DELAY)
                continue
            return False, "Invalid Profile (Status Code: %s)" % resp.status_code
        except requests.RequestException as e:
            if attempt < retries - 1:
                time.sleep((attempt + 1) * DEFAULT_RATE_LIMIT_DELAY)
                continue
            return False, "Request Failed: %s" % str(e)[:100]

    return False, "Request Failed After Retries"


def _verify_with_urllib(url, timeout, retries):
    """Fallback when requests is not installed: use urllib with same domain/path checks."""
    import urllib.request
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                method="GET",
                headers={"User-Agent": USER_AGENTS[attempt % len(USER_AGENTS)]},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if 200 <= resp.getcode() < 400:
                    return True, "Valid Profile"
                return False, "Invalid Profile (Status Code: %s)" % resp.getcode()
        except Exception as e:
            if attempt < retries - 1:
                time.sleep((attempt + 1) * DEFAULT_RATE_LIMIT_DELAY)
                continue
            return False, "Request Failed: %s" % str(e)[:100]
    return False, "Request Failed After Retries"
