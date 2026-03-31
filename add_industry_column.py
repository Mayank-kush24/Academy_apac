"""
Add 'industry' column to user_pii and user_pii_injected tables,
populate it using get_industry(domain, designation, organization_name),
and recreate the user_pii_combined view to include the new column.
"""
from server.app import create_app
from server.models import db
from server.utils.industry_map import get_industry

app = create_app()
with app.app_context():
    from sqlalchemy import text

    # Step 1: Add the column if it doesn't exist
    for table in ('user_pii', 'user_pii_injected'):
        try:
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN industry VARCHAR(255)"))
            db.session.commit()
            print(f"[OK] Added 'industry' column to {table}")
        except Exception as e:
            db.session.rollback()
            if 'already exists' in str(e).lower() or 'duplicate column' in str(e).lower():
                print(f"[OK] 'industry' column already exists in {table}")
            else:
                raise

    # Step 2: Populate user_pii (using domain, designation, org, and persona)
    rows = db.session.execute(text(
        "SELECT id, domain, designation, organization_name, persona FROM user_pii"
    )).fetchall()
    print(f"\nPopulating industry for {len(rows)} user_pii rows...")
    batch = []
    for row_id, domain, designation, org, persona in rows:
        ind = get_industry(domain, designation, org, persona) or ''
        batch.append({'rid': row_id, 'ind': ind})
        if len(batch) >= 1000:
            db.session.execute(
                text("UPDATE user_pii SET industry = :ind WHERE id = :rid"),
                batch
            )
            db.session.commit()
            batch = []
    if batch:
        db.session.execute(
            text("UPDATE user_pii SET industry = :ind WHERE id = :rid"),
            batch
        )
        db.session.commit()
    print(f"[OK] Populated industry for {len(rows)} user_pii rows")

    # Step 3: Populate user_pii_injected
    rows2 = db.session.execute(text(
        "SELECT id, domain, designation, organization_name, persona FROM user_pii_injected"
    )).fetchall()
    print(f"\nPopulating industry for {len(rows2)} user_pii_injected rows...")
    batch = []
    for row_id, domain, designation, org, persona in rows2:
        ind = get_industry(domain, designation, org, persona) or ''
        batch.append({'rid': row_id, 'ind': ind})
        if len(batch) >= 1000:
            db.session.execute(
                text("UPDATE user_pii_injected SET industry = :ind WHERE id = :rid"),
                batch
            )
            db.session.commit()
            batch = []
    if batch:
        db.session.execute(
            text("UPDATE user_pii_injected SET industry = :ind WHERE id = :rid"),
            batch
        )
        db.session.commit()
    print(f"[OK] Populated industry for {len(rows2)} user_pii_injected rows")

    # Step 4: Recreate the view to include industry
    db.session.execute(text("DROP VIEW IF EXISTS user_pii_combined CASCADE"))
    db.session.execute(text("""
        CREATE VIEW user_pii_combined AS
        SELECT id, registered_at, organization_name, class_stream, domain, designation, name, email,
               mobile_number, country, state, city, date_of_birth, gender, occupation,
               github_url, linkedin_url, utm_medium, bob_match, created_at, updated_at,
               industry, 'user_pii' AS source
        FROM user_pii
        UNION ALL
        SELECT id, registered_at, organization_name, class_stream, domain, designation, name, email,
               mobile_number, country, state, city, date_of_birth, gender, occupation,
               github_url, linkedin_url, utm_medium, bob_match, created_at, updated_at,
               industry, 'user_pii_injected' AS source
        FROM user_pii_injected i
        WHERE NOT EXISTS (SELECT 1 FROM user_pii u WHERE u.email = i.email)
    """))
    db.session.commit()
    print("\n[OK] Recreated user_pii_combined view with industry column")

    # Verify
    sample = db.session.execute(text(
        "SELECT industry, COUNT(*) as cnt FROM user_pii GROUP BY industry ORDER BY cnt DESC LIMIT 15"
    )).fetchall()
    print("\nIndustry distribution (user_pii):")
    for ind, cnt in sample:
        print(f"  {cnt:>6}  {ind or '(blank)'}")

    print("\nDone!")
