"""
Backfill Cohort 2 codelab_submission upload_screenshot + problem_statement + track_number
from the latest Action Center Forms archive (Upload File column).

Usage:
  python scripts/backfill_c2_codelab_screenshots.py           # dry run
  python scripts/backfill_c2_codelab_screenshots.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from dotenv import load_dotenv

load_dotenv()


def _latest_c2_forms_xlsx(archive_root: Path) -> Path | None:
    candidates = []
    for p in archive_root.rglob("*.xlsx"):
        name = p.name.lower()
        if "actioncenter" in name.replace("-", "").replace("_", "") or "action-center" in name or "action_center" in name:
            # Prefer Forms workbooks that contain Professional Track Codelab tabs
            if "forms" in name or "actioncenter" in name.replace("-", "").replace("_", ""):
                candidates.append(p)
        elif "gen_ai_academy" in name or "genai" in name.replace(" ", ""):
            candidates.append(p)
    # Prefer skillboost_import and newest mtime
    def sort_key(p: Path):
        score = 0
        parts = str(p).lower()
        if "skillboost_import" in parts:
            score += 100
        if "forms" in p.name.lower():
            score += 10
        return (score, p.stat().st_mtime)

    if not candidates:
        # Fallback: any xlsx under skillboost_import with Codelab in sheets checked later
        candidates = list(archive_root.rglob("skillboost_import/*.xlsx"))
    if not candidates:
        return None
    return max(candidates, key=sort_key)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--file", default="", help="Optional path to Action Center xlsx")
    args = ap.parse_args()

    from server.app import create_app
    from server.models import db
    from server.utils.cohort_participant_models import apply_cohort_globals, participant_model
    from server.models import CodeLabSubmission as BaseCL
    from server.utils.excel_parser import (
        import_codelab_submission_sheets,
        _match_detector,
        _codelab_sheet_track_number,
        _codelab_default_problem_statement,
    )

    archive_root = Path("import_file_archive")
    xlsx = Path(args.file) if args.file else _latest_c2_forms_xlsx(archive_root)
    if not xlsx or not xlsx.exists():
        print("No Action Center Forms xlsx found.")
        sys.exit(1)
    print(f"Source: {xlsx}")

    xl = pd.ExcelFile(xlsx)
    sheets = []
    for name in xl.sheet_names:
        det = _match_detector(name, cohort_id=2)
        if not det or det.module != "codelab_submission":
            continue
        track = _codelab_sheet_track_number(name, det.track)
        default_ps = _codelab_default_problem_statement(name, track)
        df = pd.read_excel(xl, sheet_name=name)
        print(f"  sheet={name!r} track={track} default_ps={default_ps!r} rows={len(df)} cols={list(df.columns)}")
        sheets.append({
            "track": track,
            "sheet_name": name,
            "df": df,
            "default_problem_statement": default_ps,
        })

    if not sheets:
        print("No codelab sheets detected.")
        sys.exit(1)

    if not args.apply:
        # Preview how many Upload File values are present
        for s in sheets:
            df = s["df"]
            upload_col = next((c for c in df.columns if str(c).strip().lower() == "upload file"), None)
            n = 0
            if upload_col:
                n = df[upload_col].dropna().astype(str).str.strip().ne("").sum()
            print(f"  preview {s['sheet_name']}: upload_file_nonempty={n}")
        print("\nDry run. Re-run with --apply to import into cohort_2_codelab_submission.")
        return

    app = create_app()
    with app.app_context():
        apply_cohort_globals("cohort_2_", 2)
        # Smoke: ensure model resolves
        CL = participant_model(BaseCL)
        before = {
            "total": CL.query.count(),
            "with_ss": CL.query.filter(CL.upload_screenshot.isnot(None), CL.upload_screenshot != "").count(),
            "with_ps": CL.query.filter(CL.problem_statement.isnot(None), CL.problem_statement != "").count(),
        }
        print("Before:", before)

        result = import_codelab_submission_sheets(sheets)
        print("Import result:", {
            "total_rows": result.get("total_rows"),
            "created": result.get("created"),
            "updated": result.get("updated"),
            "skipped": result.get("skipped"),
            "errors": (result.get("errors") or [])[:5],
        })

        after = {
            "total": CL.query.count(),
            "with_ss": CL.query.filter(CL.upload_screenshot.isnot(None), CL.upload_screenshot != "").count(),
            "with_ps": CL.query.filter(CL.problem_statement.isnot(None), CL.problem_statement != "").count(),
        }
        print("After:", after)


if __name__ == "__main__":
    main()
