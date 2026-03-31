"""Update all Skill Lab credit link capacities to 4000."""
from server.app import create_app
from server.models import db

app = create_app()
with app.app_context():
    rows = db.session.execute(db.text("SELECT id, display_order, max_allocations FROM credit_links ORDER BY display_order")).fetchall()
    print(f"Found {len(rows)} credit link(s):")
    for r in rows:
        print(f"  id={r[0]}  order={r[1]}  current capacity={r[2]}")

    result = db.session.execute(db.text("UPDATE credit_links SET max_allocations = 4000"))
    db.session.commit()
    print(f"\nUpdated {result.rowcount} row(s) to max_allocations = 4000.")

    rows = db.session.execute(db.text("SELECT id, display_order, max_allocations FROM credit_links ORDER BY display_order")).fetchall()
    print("\nVerification:")
    for r in rows:
        print(f"  id={r[0]}  order={r[1]}  capacity={r[2]}")
