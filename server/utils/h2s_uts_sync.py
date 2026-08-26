"""
Cohort 3 on-demand sync from Hack2Skill UTS APIs into cohort_3_* tables.

Uses:
  - Registration incremental pull via ?start=ISO watermark in cohort_3_sync_state
  - Modules list + per-module data upsert via existing excel_parser importers
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text

from server.models import db
from server.utils.bob_match import recalculate_bob_match
from server.utils.cache import clear_cache
from server.utils.excel_parser import (
    _find_email_column,
    _find_profile_link_column,
    auto_map_fields,
    import_codelab_submission,
    import_data,
    import_optional_mcq_response,
    import_skillboost_profile,
    import_skilllab_submission,
)
from server.utils.cohort_participant_models import apply_cohort_globals
from server.utils.h2s_uts_client import (
    REGISTRATION_PAGE_SIZE,
    H2SUtsClient,
    H2SUtsError,
    extract_modules,
    extract_records,
    module_id_of,
    module_name_of,
)

SYNC_KEY_REGISTRATION_START = "registration_start"
SYNC_KEY_LAST_SYNC_AT = "last_sync_at"
SYNC_KEY_LAST_SYNC_STATUS = "last_sync_status"
SYNC_KEY_REGISTRATION_GAPS = "registration_gaps"
SYNC_KEY_FETCH_HINTS = "registration_fetch_hints"

_TRACK_RE = re.compile(r"track\s*(\d+)", re.IGNORECASE)
_COHORT_PREFIX_RE = re.compile(r"^cohort_([0-9]+)_$")
_OBJECTID_ERR_RE = re.compile(r"failed to parse objectid '([^']*)'", re.I)
_UTS_ISO_FMT = "%Y-%m-%dT%H:%M:%S.000Z"
#: Safety stop for window slides; 40 * 50k is far above any plausible cohort size.
MAX_REGISTRATION_WINDOWS = 40
#: Distinct poisoned rows to step over before giving up on the range.
MAX_REGISTRATION_GAPS = 4
#: UTS renders row ``Timestamp`` in IST but filters ``start`` in UTC.
UTS_TIMESTAMP_OFFSET = timedelta(hours=5, minutes=30)
POISON_GAP_REASON = (
    "UTS registrations endpoint returns HTTP 500 for any window containing this "
    "range (upstream $convert to ObjectId fails on a non-ObjectId value{bad}). "
    "Backfill once Hack2Skill fixes the record."
)


def _sync_table(prefix: str) -> str:
    return f"{prefix}sync_state"


def _bind_cohort_context(prefix: str) -> None:
    """
    Pin flask.g to the cohort being synced.

    import_data(), the module importers and recalculate_bob_match() all resolve their
    target tables from g.table_prefix, which is normally set per request. Outside a
    request (CLI, cron, worker thread) it is unset and they silently fall back to the
    cohort 1 tables, so bind it explicitly rather than trusting the caller's context.
    """
    match = _COHORT_PREFIX_RE.match(prefix or "")
    if not match:
        raise ValueError(
            f"refusing to sync with table prefix {prefix!r}; expected e.g. 'cohort_3_'"
        )
    apply_cohort_globals(prefix, int(match.group(1)))


def get_sync_value(prefix: str, key: str) -> Optional[str]:
    row = db.session.execute(
        text(f"SELECT value FROM {_sync_table(prefix)} WHERE key = :key"),
        {"key": key},
    ).fetchone()
    if not row:
        return None
    val = row[0]
    return str(val) if val is not None else None


def set_sync_value(prefix: str, key: str, value: Optional[str]) -> None:
    db.session.execute(
        text(
            f"""
            INSERT INTO {_sync_table(prefix)} (key, value, updated_at)
            VALUES (:key, :value, NOW())
            ON CONFLICT (key) DO UPDATE
              SET value = EXCLUDED.value, updated_at = NOW()
            """
        ),
        {"key": key, "value": value},
    )
    db.session.commit()


def get_registration_gaps(prefix: str) -> List[Dict[str, str]]:
    """
    Windows of registration time that were deliberately skipped and are still missing.

    Populated when the watermark is advanced past an upstream record that UTS cannot
    serve. Cleared by a successful full sync, which refetches the whole range.
    """
    raw = get_sync_value(prefix, SYNC_KEY_REGISTRATION_GAPS)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [g for g in parsed if isinstance(g, dict)] if isinstance(parsed, list) else []


def add_registration_gap(prefix: str, gap_from: str, gap_to: str, reason: str) -> None:
    gaps = get_registration_gaps(prefix)
    gaps.append(
        {
            "from": gap_from,
            "to": gap_to,
            "reason": reason,
            "recorded_at": _utc_now_iso(),
        }
    )
    set_sync_value(prefix, SYNC_KEY_REGISTRATION_GAPS, json.dumps(gaps))


def clear_registration_gaps(prefix: str) -> None:
    set_sync_value(prefix, SYNC_KEY_REGISTRATION_GAPS, None)


def get_sync_status(prefix: str = "cohort_3_") -> Dict[str, Any]:
    return {
        "registration_start": get_sync_value(prefix, SYNC_KEY_REGISTRATION_START),
        "last_sync_at": get_sync_value(prefix, SYNC_KEY_LAST_SYNC_AT),
        "last_sync_status": get_sync_value(prefix, SYNC_KEY_LAST_SYNC_STATUS),
        "registration_gaps": get_registration_gaps(prefix),
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def uts_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(_UTS_ISO_FMT)


def parse_uts_iso(value: str) -> datetime:
    cleaned = value.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(cleaned).astimezone(timezone.utc)


def is_uts_objectid_convert_error(exc: BaseException) -> bool:
    """True when Hack2Skill's Mongo $convert-to-ObjectId aggregation dies on a non-OID string."""
    msg = str(exc).lower()
    return "failed to parse objectid" in msg or ("$convert" in str(exc) and "oid" in msg)


def objectid_convert_bad_value(exc: BaseException) -> Optional[str]:
    match = _OBJECTID_ERR_RE.search(str(exc))
    return match.group(1) if match else None


def registration_start_works(client: H2SUtsClient, dt: datetime) -> bool:
    try:
        client.fetch_registrations(start=uts_iso(dt))
        return True
    except H2SUtsError:
        return False


def find_earliest_safe_registration_start(
    client: H2SUtsClient,
    lo: datetime,
    hi: datetime,
    *,
    on_probe: Optional[Callable[[datetime, datetime], None]] = None,
) -> datetime:
    """Binary-search the first ``start`` that the UTS registrations endpoint can serve."""
    lo = lo.astimezone(timezone.utc)
    hi = hi.astimezone(timezone.utc)
    if hi < lo:
        hi = lo
    if registration_start_works(client, lo):
        return lo
    if not registration_start_works(client, hi):
        bumped = hi + timedelta(seconds=2)
        if not registration_start_works(client, bumped):
            raise H2SUtsError(
                f"UTS registrations still fail at start={uts_iso(bumped)}. "
                "The poisoned record is at or after the search window."
            )
        hi = bumped
    while (hi - lo) > timedelta(seconds=1):
        mid = lo + (hi - lo) / 2
        if registration_start_works(client, mid):
            hi = mid
        else:
            lo = mid
        if on_probe:
            on_probe(lo, hi)
    return hi


def _registration_key(row: Dict[str, Any]) -> Optional[str]:
    for k in ("Email", "email", "_id", "id"):
        v = row.get(k)
        if v is not None and str(v).strip():
            return f"{k.lower()}:{str(v).strip().lower()}"
    return None


def _row_timestamp(row: Dict[str, Any]) -> Optional[str]:
    for k in ("Timestamp", "timestamp", "createdAt", "created_at"):
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _max_registration_timestamp(records: List[Dict[str, Any]]) -> Optional[str]:
    stamps = [t for t in (_row_timestamp(r) for r in records) if t]
    return max(stamps) if stamps else None


def start_param_for_timestamp(ts: str) -> str:
    """
    Convert a row ``Timestamp`` into the ``start`` value that selects that row.

    Only used to position the window; every candidate is confirmed by the request that
    follows, so a drifting offset costs coverage rather than correctness.
    """
    return uts_iso(parse_uts_iso(ts) - UTS_TIMESTAMP_OFFSET)


def timestamp_for_start_param(start: str) -> str:
    """Inverse of :func:`start_param_for_timestamp`, so both gap ends read in row time."""
    return uts_iso(parse_uts_iso(start) + UTS_TIMESTAMP_OFFSET)


def largest_safe_window(
    client: H2SUtsClient,
    stamps: List[str],
) -> Optional[Tuple[List[Dict[str, Any]], str]]:
    """
    Binary-search the furthest-forward window that still stops before the poisoned row.

    The 50k cap is a window anchored at ``start``, so anchoring at the k-th known row
    returns rows k..k+50k. Low k succeeds; high k reaches the poisoned row and 500s. The
    boundary is monotone, so the best anchor is searchable even though the rows between
    the last success and the poisoned row cannot be listed.

    Returns the best ``(records, start)``, or ``None`` if no anchor beat the first one.
    """
    if len(stamps) < 3:
        return None
    best: Optional[Tuple[List[Dict[str, Any]], str]] = None
    lo, hi = 0, len(stamps) - 1
    while lo < hi - 1:
        k = (lo + hi) // 2
        start = start_param_for_timestamp(stamps[k])
        try:
            batch = extract_records(client.fetch_registrations(start=start))
        except H2SUtsError as exc:
            if not is_uts_objectid_convert_error(exc):
                raise
            hi = k
            continue
        lo = k
        best = (batch, start)
    return best


def _resolve_safe_start(
    client: H2SUtsClient,
    hints: Dict[str, str],
    failing_start: Optional[str],
) -> str:
    """
    Earliest ``start`` the API can serve, reusing the cached boundary when it still holds.

    ``failing_start`` anchors the search. Whether a window fails is not monotone across
    all of time — a sufficiently early anchor stops short of the poisoned row and
    succeeds — but it is monotone from a known-failing anchor forward, which is what the
    binary search needs.
    """
    cached = hints.get("safe_start")
    if cached:
        try:
            client.fetch_registrations(start=cached)
            return cached
        except H2SUtsError:
            pass
    lo = (
        parse_uts_iso(failing_start)
        if failing_start
        else datetime.now(timezone.utc) - timedelta(days=400)
    )
    safe = uts_iso(
        find_earliest_safe_registration_start(client, lo, datetime.now(timezone.utc))
    )
    hints["safe_start"] = safe
    return safe


def _hinted_window(
    client: H2SUtsClient,
    hints: Dict[str, str],
) -> Optional[Tuple[List[Dict[str, Any]], str]]:
    cached = hints.get("window_start")
    if not cached:
        return None
    try:
        return extract_records(client.fetch_registrations(start=cached)), cached
    except H2SUtsError as exc:
        if not is_uts_objectid_convert_error(exc):
            raise
        return None


def fetch_reachable_registrations(
    client: H2SUtsClient,
    start: Optional[str],
    *,
    hints: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """
    Pull every registration the UTS API is willing to serve from ``start``.

    Each response is capped at ``REGISTRATION_PAGE_SIZE`` rows, and that cap is a window
    anchored at ``start`` rather than a fixed head of the collection, so coverage is
    extended by re-anchoring ``start`` on the newest row received.

    One upstream row holds a value that fails Mongo's ``$convert`` to ObjectId, and any
    window reaching it returns HTTP 500. When that happens the window is first slid as
    far forward as it can go without touching that row, then re-anchored just past it;
    whatever falls between is reported as a gap.

    ``hints`` caches the boundaries these searches discover and is updated in place, so
    later syncs skip the searches. Returns ``(records, gaps)``.
    """
    hints = hints if hints is not None else {}
    records: List[Dict[str, Any]] = []
    seen: set = set()
    gaps: List[Dict[str, str]] = []
    cur_start = start

    def absorb(batch: List[Dict[str, Any]]) -> int:
        fresh = 0
        for row in batch:
            key = _registration_key(row)
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)
            records.append(row)
            fresh += 1
        return fresh

    for _ in range(MAX_REGISTRATION_WINDOWS):
        try:
            batch = extract_records(client.fetch_registrations(start=cur_start))
        except H2SUtsError as exc:
            if not is_uts_objectid_convert_error(exc) or len(gaps) >= MAX_REGISTRATION_GAPS:
                raise

            stamps = sorted(
                t for t in (_row_timestamp(r) for r in records) if t
            )
            squeezed = _hinted_window(client, hints) or largest_safe_window(client, stamps)
            if squeezed:
                squeezed_rows, used = squeezed
                absorb(squeezed_rows)
                hints["window_start"] = used

            safe = _resolve_safe_start(client, hints, cur_start)
            if cur_start and safe == cur_start:
                raise
            # Both ends are reported as row timestamps; ``safe`` is a ``start`` value,
            # which is offset from the timestamps the rows themselves carry.
            gaps.append(
                {
                    "from": _max_registration_timestamp(records)
                    or (timestamp_for_start_param(cur_start) if cur_start else "(beginning)"),
                    "to": timestamp_for_start_param(safe),
                    "bad": objectid_convert_bad_value(exc) or "",
                }
            )
            cur_start = safe
            continue

        fresh = absorb(batch)
        # A short window means the server ran out of rows, not that the slide stalled.
        if len(batch) < REGISTRATION_PAGE_SIZE:
            break
        newest = _max_registration_timestamp(batch)
        if not newest:
            break
        nxt = start_param_for_timestamp(newest)
        if nxt == cur_start or fresh == 0:
            break
        cur_start = nxt

    return records, gaps


def _flatten_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten nested form payloads into a single-level dict of scalar values."""
    out: Dict[str, Any] = {}
    nest_keys = {
        "formdata",
        "form_data",
        "answers",
        "answer",
        "response",
        "responses",
        "fields",
        "data",
        "submission",
        "payload",
    }

    def _put(key: Any, value: Any) -> None:
        if key is None:
            return
        k = str(key).strip()
        if not k:
            return
        if isinstance(value, (dict, list)):
            return
        if k not in out or out[k] in (None, ""):
            out[k] = value

    for k, v in row.items():
        kl = str(k).strip().lower()
        if isinstance(v, dict) and kl in nest_keys:
            for sk, sv in v.items():
                _put(sk, sv)
            continue
        if isinstance(v, list):
            continue
        _put(k, v)
    return out


def _records_to_dataframe(records: List[Dict[str, Any]]) -> pd.DataFrame:
    flat = [_flatten_row(r) for r in records]
    if not flat:
        return pd.DataFrame()
    return pd.DataFrame(flat)


def _ensure_leader_email_column(df: pd.DataFrame) -> pd.DataFrame:
    """Make sure submission importers can find a Leader Email column."""
    if df.empty:
        return df
    from server.utils.excel_parser import _find_leader_email_column

    if _find_leader_email_column(list(df.columns)):
        return df
    aliases = {
        "email",
        "user email",
        "user_email",
        "participant email",
        "participant_email",
        "registered email",
        "registered_email",
    }
    for col in list(df.columns):
        if str(col).strip().lower() in aliases:
            return df.rename(columns={col: "Leader Email"})
    return df


def _classify_module(name: str, module_id: str = "") -> Tuple[str, Optional[int]]:
    """
    Return (kind, track_number) for a module label.
    kind: skillboost_profile | skilllab_submission | codelab_submission |
          optional_mcq | skip | unknown
    """
    label = f"{name} {module_id}".strip().lower()
    track = None
    m = _TRACK_RE.search(label)
    if m:
        try:
            track = int(m.group(1))
        except ValueError:
            track = None

    # Disabled for C3 (same as C2)
    if "project" in label and "submission" in label:
        return "skip", track
    if re.search(r"\bmcq\b", label) and "optional" not in label:
        return "skip", track

    if "optional" in label and "mcq" in label:
        return "optional_mcq", track if track is not None else 4

    if any(
        x in label
        for x in (
            "skill lab submission",
            "skills lab submission",
            "skilllab submission",
            "google skills lab",
        )
    ) or (("skill lab" in label or "skills lab" in label or "skilllab" in label) and "profile" not in label):
        return "skilllab_submission", track

    if "code lab" in label or "codelab" in label:
        return "codelab_submission", track

    if any(
        x in label
        for x in (
            "skillboost",
            "skills boost",
            "skills.google",
            "profile link",
            "share your google",
            "skills boost profile",
        )
    ) or ("profile" in label and ("skill" in label or "boost" in label or "google" in label)):
        return "skillboost_profile", track

    return "unknown", track


def get_fetch_hints(prefix: str) -> Dict[str, str]:
    """Upstream boundaries discovered by earlier syncs, so the searches run only once."""
    raw = get_sync_value(prefix, SYNC_KEY_FETCH_HINTS)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return {str(k): str(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}


def set_fetch_hints(prefix: str, hints: Dict[str, str]) -> None:
    set_sync_value(prefix, SYNC_KEY_FETCH_HINTS, json.dumps(hints) if hints else None)


def _sync_registrations(client: H2SUtsClient, prefix: str, watermark: Optional[str]) -> Dict[str, Any]:
    hints = get_fetch_hints(prefix)
    try:
        records, gaps = fetch_reachable_registrations(client, watermark, hints=hints)
    finally:
        set_fetch_hints(prefix, hints)
    for gap in gaps:
        add_registration_gap(
            prefix,
            gap_from=gap["from"],
            gap_to=gap["to"],
            reason=POISON_GAP_REASON.format(
                bad=f" {gap['bad']!r}" if gap.get("bad") else ""
            ),
        )
    df = _records_to_dataframe(records)
    if df.empty:
        return {
            "fetched": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "gaps": gaps,
            "errors": [],
        }

    mappings = auto_map_fields(list(df.columns))
    # Prefer create_update so re-sync refreshes changed PII without duplicates.
    result = import_data(df, mappings, mode="create_update")
    try:
        recalculate_bob_match()
    except Exception:
        pass
    return {
        "fetched": len(df),
        "created": result.get("created", 0) or 0,
        "updated": result.get("updated", 0) or 0,
        "skipped": result.get("skipped", 0) or 0,
        "gaps": gaps,
        "errors": (result.get("errors") or [])[:50],
    }


def _import_module_dataframe(kind: str, df: pd.DataFrame, track: Optional[int]) -> Dict[str, Any]:
    df = _ensure_leader_email_column(df)
    if kind == "skillboost_profile":
        email_col = _find_email_column(list(df.columns))
        link_col = _find_profile_link_column(list(df.columns))
        if not email_col:
            # After leader-email rename, email may be "Leader Email"
            email_col = "Leader Email" if "Leader Email" in df.columns else None
        if not email_col or not link_col:
            raise ValueError(
                f"Skillboost profile module missing email/link columns "
                f"(cols={list(df.columns)[:20]})"
            )
        return import_skillboost_profile(df, email_col, link_col)

    if kind == "skilllab_submission":
        return import_skilllab_submission(df)

    if kind == "codelab_submission":
        return import_codelab_submission(df, sheet_track_number=track)

    if kind == "optional_mcq":
        tn = track if track is not None else 4
        return import_optional_mcq_response(
            df,
            track_number=tn,
            score_from_sheet=True,
            allow_multiple_per_email=(tn == 4),
        )

    raise ValueError(f"Unsupported module kind: {kind}")


def _sync_modules(client: H2SUtsClient) -> Dict[str, Any]:
    mods_payload = client.fetch_modules()
    modules = extract_modules(mods_payload)
    summary: Dict[str, Any] = {
        "modules_listed": len(modules),
        "modules_imported": 0,
        "modules_skipped": 0,
        "modules_unknown": 0,
        "modules_failed": 0,
        "details": [],
    }

    for mod in modules:
        mid = module_id_of(mod)
        mname = module_name_of(mod)
        kind, track = _classify_module(mname, mid)
        detail: Dict[str, Any] = {
            "id": mid,
            "name": mname,
            "kind": kind,
            "track": track,
        }
        if not mid:
            detail["error"] = "missing module id"
            summary["modules_failed"] += 1
            summary["details"].append(detail)
            continue
        if kind == "skip":
            summary["modules_skipped"] += 1
            detail["status"] = "skipped"
            summary["details"].append(detail)
            continue
        if kind == "unknown":
            summary["modules_unknown"] += 1
            detail["status"] = "unknown"
            summary["details"].append(detail)
            continue

        try:
            raw = client.fetch_module_data(mid)
            records = extract_records(raw)
            df = _records_to_dataframe(records)
            if df.empty:
                detail["status"] = "empty"
                detail["fetched"] = 0
                summary["modules_imported"] += 1
                summary["details"].append(detail)
                continue
            result = _import_module_dataframe(kind, df, track)
            detail["status"] = "ok"
            detail["fetched"] = len(df)
            detail["created"] = result.get("created", 0) or 0
            detail["updated"] = result.get("updated", 0) or 0
            detail["skipped"] = result.get("skipped", 0) or 0
            summary["modules_imported"] += 1
        except Exception as exc:
            detail["status"] = "error"
            detail["error"] = str(exc)[:300]
            summary["modules_failed"] += 1
        summary["details"].append(detail)

    return summary


def run_cohort3_uts_sync(*, prefix: str = "cohort_3_", full: bool = False) -> Dict[str, Any]:
    """
    Cohort 3 sync: registrations + all recognised modules.

    full=False (Sync Now): pass stored registration ``start`` watermark (incremental).
    full=True (Sync all data): omit ``start`` and fetch all registrations.

    Advances registration watermark after a successful registration pull either way.

    If the registrations endpoint 500s on an upstream ObjectId ``$convert`` (a
    non-OID value in that field), the pull skips past the poisoned window, records
    a gap, and continues. A full pull that hits this falls back to the stored
    watermark rather than treating the whole history as missing.

    Registrations and modules are pulled independently: a failure of one is reported
    but does not prevent the other from running, because the UTS registrations
    endpoint can fail on upstream data problems while every module endpoint is healthy.
    """
    _bind_cohort_context(prefix)

    sync_started = _utc_now_iso()
    stored_watermark = get_sync_value(prefix, SYNC_KEY_REGISTRATION_START)
    watermark = None if full else stored_watermark

    try:
        client = H2SUtsClient()
    except H2SUtsError as exc:
        set_sync_value(prefix, SYNC_KEY_LAST_SYNC_AT, sync_started)
        set_sync_value(prefix, SYNC_KEY_LAST_SYNC_STATUS, f"error: {exc}")
        raise

    out: Dict[str, Any] = {
        "ok": True,
        "full": bool(full),
        "sync_started_at": sync_started,
        "registration_start_used": watermark,
        "registrations": None,
        "modules": None,
        "registration_start_new": None,
        "registrations_error": None,
        "modules_error": None,
        "full_range_unavailable": False,
        "error": None,
    }

    registrations_ok = False
    covered_full_range = False
    try:
        result = _sync_registrations(client, prefix, watermark)
        out["registrations"] = result
        # A full pull only covers the whole range if nothing had to be stepped over.
        covered_full_range = full and not result.get("gaps")
        out["full_range_unavailable"] = bool(full and result.get("gaps"))
        # Advance watermark to sync invocation time so next incremental pull is contiguous.
        set_sync_value(prefix, SYNC_KEY_REGISTRATION_START, sync_started)
        out["registration_start_new"] = sync_started
        registrations_ok = True
        # Only a true full-range pull proves recorded gaps have been filled.
        if covered_full_range:
            clear_registration_gaps(prefix)
    except Exception as exc:
        out["registrations_error"] = str(exc)[:1000]

    modules_ok = False
    try:
        out["modules"] = _sync_modules(client)
        modules_ok = True
    except Exception as exc:
        out["modules_error"] = str(exc)[:1000]

    clear_cache()

    out["registration_gaps"] = get_registration_gaps(prefix)
    out["ok"] = registrations_ok and modules_ok
    failures = []
    if not registrations_ok:
        failures.append(f"registrations: {out['registrations_error']}")
    if not modules_ok:
        failures.append(f"modules: {out['modules_error']}")
    out["error"] = " | ".join(failures) or None

    mode = "full" if full else "incremental"
    if out["ok"]:
        status = f"ok ({mode})"
    elif registrations_ok or modules_ok:
        done = "registrations" if registrations_ok else "modules"
        status = f"partial ({mode}, {done} ok): {out['error']}"
    else:
        status = f"error ({mode}): {out['error']}"
    set_sync_value(prefix, SYNC_KEY_LAST_SYNC_AT, sync_started)
    set_sync_value(prefix, SYNC_KEY_LAST_SYNC_STATUS, status)
    return out
