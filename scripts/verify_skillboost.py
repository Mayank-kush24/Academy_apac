#!/usr/bin/env python3
"""
Verify Skill Lab / Google Skills Boost profile URLs in skillboost_profile.
Updates valid (TRUE/FALSE) and remarks based on URL accessibility and domain.

Usage (from project root):
  python scripts/verify_skillboost.py
  python scripts/verify_skillboost.py --pending-only
  python scripts/verify_skillboost.py --profiles-only --workers 4

Options:
  --profiles-only   Only verify skillboost profiles (default; no-op if other tables added later).
  --pending-only    Only verify rows where valid = FALSE (skip already verified).
  --workers N       Number of concurrent workers (default 1).
"""
import argparse
import os
import sys
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from server.utils.skillboost_verify import verify_profile_url


def main():
    parser = argparse.ArgumentParser(description='Verify Skill Lab / Skillboost profile URLs')
    parser.add_argument('--profiles-only', action='store_true', default=True, help='Only verify skillboost profiles (default)')
    parser.add_argument('--pending-only', action='store_true', help='Only verify rows where valid = FALSE')
    parser.add_argument('--workers', type=int, default=1, help='Number of concurrent workers (default 1)')
    args = parser.parse_args()

    from server.app import create_app
    from server.models import db, SkillboostProfile

    app = create_app()
    with app.app_context():
        query = SkillboostProfile.query
        if getattr(args, 'pending_only', False):
            query = query.filter(SkillboostProfile.valid == False)
        rows = query.all()
        total = len(rows)
        if total == 0:
            print('No profiles to verify.')
            return 0
        print('Verifying %d profile(s)...' % total)
        verified_ok = 0
        verified_fail = 0
        for rec in rows:
            url = rec.google_cloud_skills_boost_profile_link
            valid, remarks = verify_profile_url(url)
            try:
                rec.valid = valid
                rec.remarks = remarks
                rec.updated_at = datetime.utcnow()
                db.session.commit()
                if valid:
                    verified_ok += 1
                else:
                    verified_fail += 1
            except Exception as e:
                db.session.rollback()
                print('Error updating %s: %s' % (url[:60], e))
        print('Done. Verified OK: %d, Failed: %d' % (verified_ok, verified_fail))
    return 0


if __name__ == '__main__':
    sys.exit(main())
