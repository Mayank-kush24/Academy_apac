"""
Deduplicate Skill Lab submission rows by (leader_email, upload_screenshot).

When multiple rows share the same key, keeps the row with the strongest
verification state (valid / remark / timestamps) and removes the rest.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

from server.models import db, SkillLabSubmission
from server.utils.cohort_participant_models import apply_cohort_globals, participant_model
from server.utils.excel_parser import _skilllab_submission_fingerprint


def _keeper_score(row) -> tuple:
    """Higher tuple = preferred row to keep."""
    remark = (getattr(row, "remark", None) or "").strip()
    reviewed = bool(getattr(row, "valid", False)) or bool(remark)
    return (
        1 if reviewed else 0,
        1 if getattr(row, "valid", False) else 0,
        getattr(row, "last_verified_at", None) or datetime.min,
        getattr(row, "updated_at", None) or datetime.min,
        getattr(row, "created_at", None) or datetime.min,
        str(getattr(row, "id", "")),
    )


def repair_skilllab_submission_duplicates(
    table_prefix: str = "cohort_2_",
    cohort_id: Optional[int] = 2,
    *,
    dry_run: bool = True,
) -> dict:
    """
    Collapse duplicate rows per (email, submission link).

    Returns counts: total_before, total_after, duplicate_groups, rows_removed.
    """
    apply_cohort_globals(table_prefix or "", cohort_id)
    SL = participant_model(SkillLabSubmission)

    rows = SL.query.all()
    total_before = len(rows)

    groups: dict[tuple, list] = defaultdict(list)
    for row in rows:
        email = (row.leader_email or "").strip().lower()
        fp = _skilllab_submission_fingerprint(
            email, {"upload_screenshot": row.upload_screenshot},
        )
        groups[fp].append(row)

    duplicate_groups = sum(1 for g in groups.values() if len(g) > 1)
    rows_removed = 0
    to_delete = []

    for group in groups.values():
        if len(group) <= 1:
            continue
        winner = max(group, key=_keeper_score)
        for row in group:
            if row.id != winner.id:
                to_delete.append(row)
                rows_removed += 1

    if not dry_run and to_delete:
        for row in to_delete:
            db.session.delete(row)
        db.session.commit()

    total_after = total_before - rows_removed
    return {
        "table": f"{table_prefix}skilllab_submission",
        "dry_run": dry_run,
        "total_before": total_before,
        "total_after": total_after,
        "unique_keys": len(groups),
        "duplicate_groups": duplicate_groups,
        "rows_removed": rows_removed,
    }
