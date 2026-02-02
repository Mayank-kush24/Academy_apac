"""
Book of Business (BOB) match utility.
Recalculates UserPII.bob_match by comparing organization_name (normalized) to bob_companies.
"""
from server.models import db, UserPII, BobCompany

BATCH_SIZE = 2000


def _normalize(s):
    """Trim and lower for matching."""
    if s is None or not isinstance(s, str):
        return ""
    return s.strip().lower()


def get_bob_normalized_set():
    """Load all normalized company names from bob_companies into a set."""
    names = set()
    for row in BobCompany.query.with_entities(
        BobCompany.normalized_name,
        BobCompany.company_name
    ).all():
        n = row[0] if row[0] else _normalize(row[1])
        if n:
            names.add(n)
    return names


def recalculate_bob_match():
    """
    Recalculate bob_match for all UserPII rows.
    bob_match = True iff normalized organization_name is in the BOB companies set.
    Commits in batches.
    """
    bob_set = get_bob_normalized_set()
    updated = 0
    offset = 0
    while True:
        batch = UserPII.query.order_by(UserPII.id).limit(BATCH_SIZE).offset(offset).all()
        if not batch:
            break
        for user in batch:
            org = user.organization_name
            match = bool(org and _normalize(org) in bob_set)
            if user.bob_match != match:
                user.bob_match = match
                updated += 1
        db.session.commit()
        offset += BATCH_SIZE
    return updated
