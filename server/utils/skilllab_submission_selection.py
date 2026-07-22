"""
Pick which Skill Lab submission rows count toward metrics vs. display-only history.

Rules:
- Every imported row is kept for verification.
- For a leader + skill-lab track (Student / Prof Track 1 / Prof Track 2, or legacy
  Track 1–3), only the latest row with valid=True by created_at is "counted".
- If none are valid for that track, the leader is not counted as verified there.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional, Sequence

# Legacy cohort / track-progress grid labels
TRACK_LABELS = {1: "Track 1", 2: "Track 2", 3: "Track 3"}

# Cohort 2 form options (problem_statement column)
SKILLLAB_TRACK_KEYS = ("student", "professional_1", "professional_2")


def skilllab_track_key(problem_statement: Optional[str]) -> Optional[str]:
    """
    Classify a submission into a skill-lab track bucket for counting and filters.
    Returns student | professional_1 | professional_2 | track_1 | track_2 | track_3 | None.
    """
    ps = (problem_statement or "").strip().lower()
    if not ps:
        return None
    if "building ai agents with adk" in ps or ("[student]" in ps and "track" in ps):
        return "student"
    if "conversational analytics with bigquery agents" in ps or (
        "professional" in ps and "track 1" in ps
    ):
        return "professional_1"
    if "ai-assisted data science with bigquery" in ps or (
        "professional" in ps and "track 2" in ps
    ):
        return "professional_2"
    # Legacy sheets (cohort 1 style)
    if "track 3" in ps:
        return "track_3"
    if "track 2" in ps:
        return "track_2"
    if "track 1" in ps:
        return "track_1"
    return None


def submission_matches_track(problem_statement: Optional[str], track_label: str) -> bool:
    """Match legacy Track 1/2/3 label or cohort-2 track via skilllab_track_key."""
    if not problem_statement or not track_label:
        return False
    key = skilllab_track_key(problem_statement)
    label = track_label.strip().lower()
    if label == "track 1":
        return key in ("track_1", "professional_1")
    if label == "track 2":
        return key in ("track_2", "professional_2")
    if label == "track 3":
        return key in ("track_3", "student")
    if label == "student":
        return key == "student"
    return label in (problem_statement or "").lower()


def submissions_for_track(submissions: Sequence, track_label: str) -> List:
    return [
        s
        for s in submissions
        if submission_matches_track(getattr(s, "problem_statement", None), track_label)
    ]


def submissions_for_track_key(submissions: Sequence, track_key: str) -> List:
    return [
        s
        for s in submissions
        if skilllab_track_key(getattr(s, "problem_statement", None)) == track_key
    ]


def _sort_key(row) -> tuple:
    created = getattr(row, "created_at", None) or datetime.min
    rid = getattr(row, "id", None)
    return (created, str(rid) if rid is not None else "")


def latest_valid_for_track_key(submissions: Sequence, track_key: str):
    valid = [
        s for s in submissions_for_track_key(submissions, track_key)
        if getattr(s, "valid", False)
    ]
    if not valid:
        return None
    return max(valid, key=_sort_key)


def latest_valid_for_track(submissions: Sequence, track_label: str):
    """Latest valid=True submission for this track label, or None."""
    valid = [s for s in submissions_for_track(submissions, track_label) if getattr(s, "valid", False)]
    if not valid:
        return None
    return max(valid, key=_sort_key)


def latest_submission_for_track(submissions: Sequence, track_label: str):
    """Newest submission row for this track (any validity), or None."""
    matches = submissions_for_track(submissions, track_label)
    if not matches:
        return None
    return max(matches, key=_sort_key)


def display_submission_for_track(submissions: Sequence, track_label: str):
    """
    Row to show in profile / track grid: counted valid if any, else newest for track.
    """
    return latest_valid_for_track(submissions, track_label) or latest_submission_for_track(
        submissions, track_label
    )


def is_counted_valid_submission(row, all_for_leader: Sequence) -> bool:
    """True when this row is the latest valid submission for its leader+track bucket."""
    if not getattr(row, "valid", False):
        return False
    tk = skilllab_track_key(getattr(row, "problem_statement", None))
    if not tk:
        return False
    winner = latest_valid_for_track_key(all_for_leader, tk)
    return winner is not None and getattr(winner, "id", None) == getattr(row, "id", None)


def count_counted_valid_rows(rows: Iterable) -> int:
    """Count latest-valid submission per leader per skill-lab track bucket."""
    by_leader: dict = {}
    for row in rows:
        email = (getattr(row, "leader_email", None) or "").strip().lower()
        if not email:
            continue
        by_leader.setdefault(email, []).append(row)

    total = 0
    for subs in by_leader.values():
        track_keys = set()
        for s in subs:
            tk = skilllab_track_key(getattr(s, "problem_statement", None))
            if tk:
                track_keys.add(tk)
        for tk in track_keys:
            if latest_valid_for_track_key(subs, tk) is not None:
                total += 1
    return total


def _sql_track_conditions(alias: str) -> list[tuple[str, str]]:
    """(track_key, SQL AND-fragment using alias) for counted-valid UNION branches."""
    a = alias
    return [
        (
            "student",
            f"({a}.problem_statement ILIKE '%building ai agents with adk%' "
            f"OR {a}.problem_statement ILIKE '%[Student] Track%')",
        ),
        (
            "professional_1",
            f"({a}.problem_statement ILIKE '%Conversational Analytics with BigQuery Agents%' "
            f"OR ({a}.problem_statement ILIKE '%Professional%' AND {a}.problem_statement ILIKE '%Track 1%'))",
        ),
        (
            "professional_2",
            f"({a}.problem_statement ILIKE '%AI-Assisted Data Science with BigQuery%' "
            f"OR ({a}.problem_statement ILIKE '%Professional%' AND {a}.problem_statement ILIKE '%Track 2%'))",
        ),
        (
            "track_1",
            f"({a}.problem_statement ILIKE '%Track 1%' "
            f"AND {a}.problem_statement NOT ILIKE '%Professional%' "
            f"AND {a}.problem_statement NOT ILIKE '%Student%' "
            f"AND {a}.problem_statement NOT ILIKE '%building ai agents%')",
        ),
        (
            "track_2",
            f"({a}.problem_statement ILIKE '%Track 2%' "
            f"AND {a}.problem_statement NOT ILIKE '%Professional%' "
            f"AND {a}.problem_statement NOT ILIKE '%Student%')",
        ),
        (
            "track_3",
            f"({a}.problem_statement ILIKE '%Track 3%' "
            f"AND {a}.problem_statement NOT ILIKE '%Professional%' "
            f"AND {a}.problem_statement NOT ILIKE '%Student%')",
        ),
    ]


def counted_valid_submissions_sql(table_name: str) -> str:
    """
    PostgreSQL: count latest valid row per (leader_email, skill-lab track).

    Uses a single-pass CASE + ROW_NUMBER plan instead of 6 correlated UNION
    branches (the latter nested-looped for tens of seconds on large cohorts).
    Track classification mirrors skilllab_track_key().
    """
    ps = "lower(sl.problem_statement)"
    track_case = f"""CASE
              WHEN {ps} LIKE '%building ai agents with adk%'
                OR ({ps} LIKE '%[student]%' AND {ps} LIKE '%track%')
                THEN 'student'
              WHEN {ps} LIKE '%conversational analytics with bigquery agents%'
                OR ({ps} LIKE '%professional%' AND {ps} LIKE '%track 1%')
                THEN 'professional_1'
              WHEN {ps} LIKE '%ai-assisted data science with bigquery%'
                OR ({ps} LIKE '%professional%' AND {ps} LIKE '%track 2%')
                THEN 'professional_2'
              WHEN {ps} LIKE '%track 3%' THEN 'track_3'
              WHEN {ps} LIKE '%track 2%' THEN 'track_2'
              WHEN {ps} LIKE '%track 1%' THEN 'track_1'
              ELSE NULL
            END"""
    return f"""
        SELECT COUNT(*) FROM (
          SELECT 1 FROM (
            SELECT ROW_NUMBER() OVER (
              PARTITION BY lower(sl.leader_email), track_key
              ORDER BY sl.created_at DESC NULLS LAST, sl.id DESC
            ) AS rn
            FROM (
              SELECT
                sl.id,
                sl.leader_email,
                sl.created_at,
                {track_case} AS track_key
              FROM {table_name} sl
              WHERE sl.valid = TRUE
                AND sl.leader_email IS NOT NULL
                AND TRIM(sl.leader_email) <> ''
            ) sl
            WHERE track_key IS NOT NULL
          ) ranked
          WHERE rn = 1
        ) counted
    """
