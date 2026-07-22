"""Update Skill Lab credit link capacities to 4000 (cohort 1 + cohort 2 + cohort 3)."""
from server.app import create_app
from server.models import db
from sqlalchemy import inspect, text

NEW_CAPACITY = 4000
LEGACY_CAPS = (2000, 2500, 3000)


def main():
    app = create_app()
    with app.app_context():
        insp = inspect(db.engine)
        tables = set(insp.get_table_names(schema="public"))
        targets = [
            t for t in ("credit_links", "cohort_2_credit_links", "cohort_3_credit_links")
            if t in tables
        ]
        if not targets:
            print("No credit_links tables found.")
            return

        for table in targets:
            rows = db.session.execute(
                text(f"SELECT id, display_order, max_allocations FROM {table} ORDER BY display_order")
            ).fetchall()
            print(f"\n{table} — before ({len(rows)} link(s)):")
            for r in rows:
                print(f"  id={r[0]}  order={r[1]}  capacity={r[2]}")

            result = db.session.execute(
                text(
                    f"UPDATE {table} SET max_allocations = :cap "
                    f"WHERE max_allocations IN :legacy"
                ),
                {"cap": NEW_CAPACITY, "legacy": LEGACY_CAPS},
            )
            db.session.commit()
            print(f"Updated {result.rowcount} row(s) in {table} -> {NEW_CAPACITY}.")

            rows = db.session.execute(
                text(f"SELECT id, display_order, max_allocations FROM {table} ORDER BY display_order")
            ).fetchall()
            print(f"{table} — after:")
            for r in rows:
                print(f"  id={r[0]}  order={r[1]}  capacity={r[2]}")


if __name__ == "__main__":
    main()
