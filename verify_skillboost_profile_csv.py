"""
Standalone script: Skillboost Profile Verification from CSV

Reads a CSV with columns [email, Share your Google Skills Public profile link],
verifies each profile URL, and writes a new CSV with added verification columns.

Usage:
    python scripts/verify_skillboost_profile_csv.py --input path/to/input.csv
    python scripts/verify_skillboost_profile_csv.py --input input.csv --output verified.csv
    python scripts/verify_skillboost_profile_csv.py --input input.csv --workers 5

Output CSV columns: all original columns + Valid, Verification_Remarks, Verified_At
"""

import argparse
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlparse

try:
    import pandas as pd
except ImportError:
    print("Error: pandas is required. Install with: pip install pandas")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Error: requests is required. Install with: pip install requests")
    sys.exit(1)


# Default settings (aligned with app config: Config.VERIFICATION_TIMEOUT, RATE_LIMIT_DELAY, etc.)
DEFAULT_TIMEOUT = 10
DEFAULT_RETRIES = 3
DEFAULT_RATE_LIMIT_DELAY = 2.5  # used only on 429 or retry
VALID_DOMAINS = ["www.cloudskillsboost.google", "www.skills.google"]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# Thread-local HTTP session for connection keep-alive (faster repeated requests to same host)
_thread_local = threading.local()


def _get_session():
    if not getattr(_thread_local, "session", None):
        _thread_local.session = requests.Session()
    return _thread_local.session


def verify_profile_url(url, timeout=DEFAULT_TIMEOUT, retries=DEFAULT_RETRIES, session=None):
    """
    Verify a Google Skills Boost / Skillboost profile URL.
    Uses optional session for connection keep-alive (faster when called from same thread).
    Returns (is_valid: bool, remarks: str).
    """
    if not isinstance(url, str) or not str(url).strip():
        return False, "Empty or Invalid URL"

    url = str(url).strip()

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"URL parsing error: {str(e)}"

    if parsed.netloc not in VALID_DOMAINS:
        return False, f"Incorrect Domain (must be {' or '.join(VALID_DOMAINS)})"

    if not parsed.path.startswith("/public_profiles/"):
        return False, "Incorrect Path (must start with /public_profiles/)"

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
                wait = (attempt + 1) * DEFAULT_RATE_LIMIT_DELAY
                time.sleep(wait)
                continue
            return False, f"Invalid Profile (Status Code: {resp.status_code})"
        except requests.RequestException as e:
            if attempt < retries - 1:
                time.sleep((attempt + 1) * DEFAULT_RATE_LIMIT_DELAY)
                continue
            return False, f"Request Failed: {str(e)[:100]}"

    return False, "Request Failed After Retries"


def find_profile_link_column(df):
    """Find column that contains 'Share your Google Skills' or similar profile link header."""
    for col in df.columns:
        col_lower = str(col).strip().lower()
        if "share your google skills" in col_lower or "share your google skills public profile" in col_lower:
            return col
        if "profile link" in col_lower and "skill" in col_lower:
            return col
        if "google skills" in col_lower and "link" in col_lower:
            return col
    return None


def find_email_column(df):
    """Find email column (case-insensitive)."""
    for col in df.columns:
        if str(col).strip().lower() == "email":
            return col
    return None


def verify_row(args):
    """Verify a single row (worker). Uses thread-local session for connection reuse."""
    idx, profile_url, timeout, retries = args
    # Small random delay to distribute load (same as existing verify_skillboost.py)
    time.sleep(random.uniform(0.1, 0.5))
    session = _get_session()
    valid, remarks = verify_profile_url(
        profile_url, timeout=timeout, retries=retries, session=session
    )
    return idx, valid, remarks


def main():
    parser = argparse.ArgumentParser(
        description="Verify Skillboost profile URLs from a CSV and output a new CSV with verification columns."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to input CSV file (must have 'email' and a column containing 'Share your Google Skills Public profile link')",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Path to output CSV file (default: <input_basename>_verified_<timestamp>.csv)",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=10,
        help="Number of parallel workers (default: 10, same as main verify_skillboost.py)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Request timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help="Retries per URL on failure (default: 3)",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Input/output CSV encoding (default: utf-8)",
    )
    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    if not os.path.isfile(input_path):
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    # Output path
    if args.output:
        output_path = os.path.abspath(args.output)
    else:
        base, ext = os.path.splitext(os.path.basename(input_path))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(os.path.dirname(input_path), f"{base}_verified_{timestamp}{ext}")

    print("=" * 60)
    print("Skillboost Profile Verification (CSV)")
    print("=" * 60)
    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print(f"Workers: {args.workers}")
    print("=" * 60)

    # Read CSV
    try:
        df = pd.read_csv(input_path, encoding=args.encoding)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)

    email_col = find_email_column(df)
    profile_col = find_profile_link_column(df)

    if not email_col:
        print("Error: No 'email' column found in CSV.")
        sys.exit(1)
    if not profile_col:
        print("Error: No column containing 'Share your Google Skills' / profile link found.")
        print("Columns in file:", list(df.columns))
        sys.exit(1)

    print(f"Using email column: '{email_col}'")
    print(f"Using profile link column: '{profile_col}'")
    print(f"Total rows: {len(df)}")
    print()

    # Prepare verification tasks (skip empty URLs)
    rows_to_verify = []
    for idx in df.index:
        url = df.at[idx, profile_col]
        if pd.isna(url) or not str(url).strip() or str(url).strip() in ("-", ""):
            continue
        rows_to_verify.append((idx, str(url).strip(), args.timeout, args.retries))

    if not rows_to_verify:
        print("No non-empty profile URLs to verify.")
        df["Valid"] = ""
        df["Verification_Remarks"] = "No URL"
        df["Verified_At"] = ""
        df.to_csv(output_path, index=False, encoding=args.encoding)
        print(f"Wrote: {output_path}")
        return

    # Run verification (with small delay between starting workers to avoid thundering herd)
    results = {}
    task_list = [(idx, url, args.timeout, args.retries) for idx, url, _, _ in rows_to_verify]

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(verify_row, t): t[0] for t in task_list}
        done = 0
        for future in as_completed(futures):
            idx, valid, remarks = future.result()
            results[idx] = (valid, remarks)
            done += 1
            if done % 10 == 0 or done == len(task_list):
                print(f"  Verified {done}/{len(task_list)} ...")

    # Add new columns
    verified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df["Valid"] = ""
    df["Verification_Remarks"] = ""
    df["Verified_At"] = ""

    for idx in df.index:
        if idx in results:
            valid, remarks = results[idx]
            df.at[idx, "Valid"] = "TRUE" if valid else "FALSE"
            df.at[idx, "Verification_Remarks"] = remarks
            df.at[idx, "Verified_At"] = verified_at
        else:
            url_val = df.at[idx, profile_col]
            if pd.isna(url_val) or not str(url_val).strip() or str(url_val).strip() in ("-", ""):
                df.at[idx, "Valid"] = ""
                df.at[idx, "Verification_Remarks"] = "No URL"
                df.at[idx, "Verified_At"] = ""
            else:
                df.at[idx, "Valid"] = ""
                df.at[idx, "Verification_Remarks"] = "Skipped"
                df.at[idx, "Verified_At"] = ""

    # Write output CSV
    df.to_csv(output_path, index=False, encoding=args.encoding)
    print()
    print("=" * 60)
    valid_count = sum(1 for v in results.values() if v[0])
    fail_count = len(results) - valid_count
    print(f"Verified: {valid_count} valid, {fail_count} failed")
    print(f"Output written: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
