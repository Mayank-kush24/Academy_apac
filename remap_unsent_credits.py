"""
Clear credit_link_id for profiles where credits were allocated but NOT sent
(email_sent_at IS NULL), then re-allocate starting from the first credit link.
"""
from server.app import create_app
from server.models import db, SkillboostProfile, CreditLink

app = create_app()
with app.app_context():
    from sqlalchemy import func

    # --- Current state ---
    links = CreditLink.query.order_by(CreditLink.display_order).all()
    print("Credit links:")
    for link in links:
        total = SkillboostProfile.query.filter(SkillboostProfile.credit_link_id == link.id).count()
        sent = SkillboostProfile.query.filter(
            SkillboostProfile.credit_link_id == link.id,
            SkillboostProfile.email_sent_at.isnot(None)
        ).count()
        not_sent = SkillboostProfile.query.filter(
            SkillboostProfile.credit_link_id == link.id,
            SkillboostProfile.email_sent_at.is_(None)
        ).count()
        print(f"  Link #{link.display_order} (id={link.id}): capacity={link.max_allocations}, "
              f"allocated={total}, sent={sent}, not_sent={not_sent}")

    # --- Step 1: Clear credit_link_id for unsent profiles ---
    cleared = SkillboostProfile.query.filter(
        SkillboostProfile.credit_link_id.isnot(None),
        SkillboostProfile.email_sent_at.is_(None)
    ).update(
        {SkillboostProfile.credit_link_id: None},
        synchronize_session=False
    )
    db.session.commit()
    print(f"\nCleared {cleared} unsent allocation(s).")

    # --- Step 2: Re-allocate from the first link ---
    counts_q = db.session.query(
        SkillboostProfile.credit_link_id,
        func.count(SkillboostProfile.email).label('cnt')
    ).filter(
        SkillboostProfile.credit_link_id.isnot(None)
    ).group_by(SkillboostProfile.credit_link_id).all()
    link_counts = {lid: c for lid, c in counts_q}

    pending = SkillboostProfile.query.filter(
        SkillboostProfile.valid == True,
        SkillboostProfile.credit_link_id.is_(None)
    ).order_by(SkillboostProfile.created_at, SkillboostProfile.email).all()

    allocated = 0
    skipped = 0
    for profile in pending:
        chosen = None
        for i, link in enumerate(links):
            n = link_counts.get(link.id, 0)
            if n >= link.max_allocations:
                continue
            all_previous_full = all(
                link_counts.get(links[j].id, 0) >= links[j].max_allocations
                for j in range(i)
            )
            if all_previous_full:
                chosen = link
                break
        if chosen:
            profile.credit_link_id = chosen.id
            link_counts[chosen.id] = link_counts.get(chosen.id, 0) + 1
            allocated += 1
        else:
            skipped += 1

    db.session.commit()
    print(f"Re-allocated {allocated} profile(s), skipped {skipped} (no capacity).")

    # --- Final state ---
    print("\nFinal state:")
    for link in links:
        total = SkillboostProfile.query.filter(SkillboostProfile.credit_link_id == link.id).count()
        sent = SkillboostProfile.query.filter(
            SkillboostProfile.credit_link_id == link.id,
            SkillboostProfile.email_sent_at.isnot(None)
        ).count()
        not_sent = SkillboostProfile.query.filter(
            SkillboostProfile.credit_link_id == link.id,
            SkillboostProfile.email_sent_at.is_(None)
        ).count()
        print(f"  Link #{link.display_order} (id={link.id}): capacity={link.max_allocations}, "
              f"allocated={total}, sent={sent}, not_sent={not_sent}")
