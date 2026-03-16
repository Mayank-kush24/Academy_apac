"""
Revert the credit remapping: restore each link to 3000 allocations (the state before remapping).
"""
from server.app import create_app
from server.models import db, SkillboostProfile, CreditLink

app = create_app()
with app.app_context():
    from sqlalchemy import func

    links = CreditLink.query.order_by(CreditLink.display_order).all()
    print("Current state:")
    for link in links:
        total = SkillboostProfile.query.filter(SkillboostProfile.credit_link_id == link.id).count()
        sent = SkillboostProfile.query.filter(
            SkillboostProfile.credit_link_id == link.id,
            SkillboostProfile.email_sent_at.isnot(None)
        ).count()
        not_sent = total - sent
        print(f"  Link #{link.display_order}: capacity={link.max_allocations}, allocated={total}, sent={sent}, not_sent={not_sent}")

    # Step 1: Clear all unsent allocations
    cleared = SkillboostProfile.query.filter(
        SkillboostProfile.credit_link_id.isnot(None),
        SkillboostProfile.email_sent_at.is_(None)
    ).update(
        {SkillboostProfile.credit_link_id: None},
        synchronize_session=False
    )
    db.session.commit()
    print(f"\nCleared {cleared} unsent allocation(s).")

    # Step 2: Re-allocate with original cap of 3000 per link
    ORIGINAL_CAP = 3000

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
            if n >= ORIGINAL_CAP:
                continue
            all_previous_full = all(
                link_counts.get(links[j].id, 0) >= ORIGINAL_CAP
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
    print(f"Re-allocated {allocated} profile(s) with cap=3000, skipped {skipped}.")

    # Final state
    print("\nReverted state:")
    for link in links:
        total = SkillboostProfile.query.filter(SkillboostProfile.credit_link_id == link.id).count()
        sent = SkillboostProfile.query.filter(
            SkillboostProfile.credit_link_id == link.id,
            SkillboostProfile.email_sent_at.isnot(None)
        ).count()
        not_sent = total - sent
        print(f"  Link #{link.display_order}: capacity={link.max_allocations}, allocated={total}, sent={sent}, not_sent={not_sent}")
