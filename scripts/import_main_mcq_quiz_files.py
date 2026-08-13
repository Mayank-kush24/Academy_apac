"""
Import Main MCQ sheets from Cohort 2 / Cohort 3 Action Center Quiz workbooks.

  python scripts/import_main_mcq_quiz_files.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

JOBS = [
    {
        "cohort_id": 2,
        "prefix": "cohort_2_",
        "path": Path("Gen_AI_Academy_APAC_Edition-ActionCenter-Quiz (4).xlsx"),
    },
    {
        "cohort_id": 3,
        "prefix": "cohort_3_",
        "path": Path("actionCenter-cohort3-deleted-quiz (1).xlsx"),
    },
]


def main() -> None:
    from server.app import create_app
    from server.models import MainMcqResponse, db
    from server.utils.cache import clear_cache
    from server.utils.cohort_participant_models import apply_cohort_globals, participant_model
    from server.utils.excel_parser import _match_detector, import_main_mcq_response

    app = create_app()
    with app.app_context():
        for job in JOBS:
            path = job["path"]
            if not path.exists():
                print(f"[SKIP] missing file: {path}")
                continue
            cid = job["cohort_id"]
            prefix = job["prefix"]
            print(f"\n=== Cohort {cid}: {path} ===")
            apply_cohort_globals(prefix, cid)
            MMR = participant_model(MainMcqResponse)

            xl = pd.ExcelFile(path)
            sheets = []
            for name in xl.sheet_names:
                det = _match_detector(name, cohort_id=cid)
                if not det or det.module != "main_mcq":
                    continue
                track = det.track
                if track is None:
                    continue
                df = pd.read_excel(xl, sheet_name=name)
                sheets.append({"track": track, "sheet_name": name, "df": df})
                print(f"  detected {name!r} -> track={track} rows={len(df)}")

            if not sheets:
                print("  No Main MCQ sheets detected.")
                continue

            before = MMR.query.count()
            for s in sheets:
                print(f"  importing track {s['track']} ({s['sheet_name']}) …")
                result = import_main_mcq_response(
                    s["df"],
                    s["track"],
                    score_from_sheet=True,
                )
                print(
                    f"    total={result.get('total_rows')} created={result.get('created')} "
                    f"updated={result.get('updated')} skipped={result.get('skipped')} "
                    f"pii_auto={result.get('pii_auto_created')} "
                    f"errors={(result.get('errors') or [])[:3]}"
                )
            after = MMR.query.count()
            by_track = (
                db.session.query(MMR.track_number, db.func.count())
                .group_by(MMR.track_number)
                .order_by(MMR.track_number)
                .all()
            )
            print(f"  table rows: {before} -> {after}; by track: {dict(by_track)}")

        try:
            clear_cache("_get_main_mcq_stats_cached")
        except Exception:
            pass
        print("\nDone.")


if __name__ == "__main__":
    main()
