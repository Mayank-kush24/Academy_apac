"""
Collapse duplicate SkillboostProfile rows per email for credits / verification.

Rules (same cohort table, email compared lowercased):
1. If any row has credit email dispatched (email_sent_at set), only one row may
   retain that state: the winner is the row with the latest email_sent_at; all
   other rows for that email are demoted (valid=False, credit cleared, sent cleared).
2. If no dispatch yet but more than two rows are valid=True, keep only the latest
   by updated_at (then created_at); other valid rows are demoted.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy import func

from server.models import db
from server.models import SkillboostProfile as SkillboostProfileBase
from server.utils.cohort_participant_models import participant_model


def _demote_row(r) -> bool:
    """Clear credit fields and mark invalid. Returns True if anything changed."""
    changed = False
    if r.valid:
        r.valid = False
        changed = True
    if r.credit_link_id is not None:
        r.credit_link_id = None
        changed = True
    if r.email_sent_at is not None:
        r.email_sent_at = None
        changed = True
    if changed:
        r.updated_at = datetime.utcnow()
    return changed


def _winner_among_sent(rows: list) -> object:
    """Latest dispatch wins."""
    sent = [r for r in rows if r.email_sent_at]
    return max(
        sent,
        key=lambda r: (r.email_sent_at, r.updated_at or r.created_at or datetime.min),
    )


def _winner_among_valid(valid_rows: list) -> object:
    """Latest profile activity wins."""
    return max(
        valid_rows,
        key=lambda r: (r.updated_at or r.created_at or datetime.min, r.created_at or datetime.min),
    )


def reconcile_skillboost_for_email(email: str) -> int:
    """
    Apply duplicate rules for one email. Returns number of rows demoted.
    """
    SB = participant_model(SkillboostProfileBase)
    em = (email or '').strip().lower()
    if not em:
        return 0
    rows = SB.query.filter(SB.email == em).all()
    if len(rows) <= 1:
        return 0

    demoted = 0
    any_sent = any(r.email_sent_at for r in rows)

    if any_sent:
        winner = _winner_among_sent(rows)
        for r in rows:
            if r is winner:
                continue
            if _demote_row(r):
                demoted += 1
        return demoted

    valid_rows = [r for r in rows if r.valid]
    if len(valid_rows) <= 2:
        return 0

    winner = _winner_among_valid(valid_rows)
    for r in valid_rows:
        if r is winner:
            continue
        if _demote_row(r):
            demoted += 1
    return demoted


def reconcile_skillboost_for_emails(emails: Iterable[str]) -> int:
    """Run reconcile for each distinct email; single commit. Returns total demotions."""
    seen = set()
    total = 0
    for raw in emails:
        em = (raw or '').strip().lower()
        if not em or em in seen:
            continue
        seen.add(em)
        total += reconcile_skillboost_for_email(em)
    if total:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    return total


def reconcile_skillboost_emails_with_multiple_rows() -> int:
    """
    Reconcile every email that has more than one profile row (any validity).
    For fixing existing DBs; safe to run multiple times.
    """
    SB = participant_model(SkillboostProfileBase)
    multi = (
        db.session.query(SB.email)
        .group_by(SB.email)
        .having(func.count() > 1)
        .all()
    )
    return reconcile_skillboost_for_emails(em[0] for em in multi if em)
