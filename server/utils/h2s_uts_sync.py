"""
Cohort 3 on-demand sync from Hack2Skill UTS APIs into cohort_3_* tables.

Uses:
  - Registration incremental pull via ?start=ISO watermark in cohort_3_sync_state
  - Modules list + per-module data upsert via existing excel_parser importers
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
from server.utils.h2s_uts_client import (
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

_TRACK_RE = re.compile(r"track\s*(\d+)", re.IGNORECASE)


def _sync_table(prefix: str) -> str:
    return f"{prefix}sync_state"


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


def get_sync_status(prefix: str = "cohort_3_") -> Dict[str, Any]:
    return {
        "registration_start": get_sync_value(prefix, SYNC_KEY_REGISTRATION_START),
        "last_sync_at": get_sync_value(prefix, SYNC_KEY_LAST_SYNC_AT),
        "last_sync_status": get_sync_value(prefix, SYNC_KEY_LAST_SYNC_STATUS),
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _sync_registrations(client: H2SUtsClient, prefix: str, watermark: Optional[str]) -> Dict[str, Any]:
    payload = client.fetch_registrations(start=watermark)
    records = extract_records(payload)
    # Some APIs return the list at top level already handled; if empty but payload is list of non-dicts, ignore.
    df = _records_to_dataframe(records)
    if df.empty:
        return {
            "fetched": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
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
    """
    sync_started = _utc_now_iso()
    watermark = None if full else get_sync_value(prefix, SYNC_KEY_REGISTRATION_START)

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
        "error": None,
    }

    try:
        out["registrations"] = _sync_registrations(client, prefix, watermark)
        # Advance watermark to sync invocation time so next incremental pull is contiguous.
        set_sync_value(prefix, SYNC_KEY_REGISTRATION_START, sync_started)
        out["registration_start_new"] = sync_started

        out["modules"] = _sync_modules(client)

        clear_cache()
        set_sync_value(prefix, SYNC_KEY_LAST_SYNC_AT, sync_started)
        mode = "full" if full else "incremental"
        set_sync_value(prefix, SYNC_KEY_LAST_SYNC_STATUS, f"ok ({mode})")
        return out
    except H2SUtsError as exc:
        out["ok"] = False
        out["error"] = str(exc)
        set_sync_value(prefix, SYNC_KEY_LAST_SYNC_AT, sync_started)
        set_sync_value(prefix, SYNC_KEY_LAST_SYNC_STATUS, f"error: {exc}")
        return out
    except Exception as exc:
        out["ok"] = False
        out["error"] = str(exc)[:500]
        set_sync_value(prefix, SYNC_KEY_LAST_SYNC_AT, sync_started)
        set_sync_value(prefix, SYNC_KEY_LAST_SYNC_STATUS, f"error: {exc}")
        return out
