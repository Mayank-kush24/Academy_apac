#!/usr/bin/env python3
"""
Copy CDI auth helpers into another Flask project (flat layout: h2s_cdi_auth.py next to app).

Example:
  python scripts/copy_cdi_auth_into_module.py D:\\path\\to\\your_app
  python scripts/copy_cdi_auth_into_module.py D:\\path\\to\\your_app --force
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "server" / "h2s_cdi_auth.py"

JARVIS_FLAT = '''"""
Legacy import path for CDI auth (same as h2s_cdi_auth).
"""
from h2s_cdi_auth import (
    get_module_pages,
    get_portal_url,
    get_user,
    h2s_cdi_auth_required,
    register_h2s_cdi_auth,
    register_with_portal,
)

jarvis_auth_required = h2s_cdi_auth_required
register_with_jarvis = register_with_portal
register_jarvis_auth = register_h2s_cdi_auth


def set_module_pages(*args, **kwargs):
    return None


__all__ = [
    "jarvis_auth_required",
    "register_jarvis_auth",
    "register_with_jarvis",
    "register_with_portal",
    "register_h2s_cdi_auth",
    "h2s_cdi_auth_required",
    "get_portal_url",
    "get_module_pages",
    "get_user",
    "set_module_pages",
]
'''


def main() -> int:
    p = argparse.ArgumentParser(description="Copy h2s_cdi_auth.py (+ jarvis_auth.py) into a target directory.")
    p.add_argument("dest", type=Path, help="Destination directory (your app root or package folder).")
    p.add_argument("--force", action="store_true", help="Overwrite existing files.")
    args = p.parse_args()
    dest: Path = args.dest.expanduser().resolve()
    if not SOURCE.is_file():
        print(f"Missing source: {SOURCE}", file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    h2s_dest = dest / "h2s_cdi_auth.py"
    jarv_dest = dest / "jarvis_auth.py"
    if h2s_dest.exists() and not args.force:
        print(f"Refusing to overwrite {h2s_dest} (use --force).", file=sys.stderr)
        return 1
    shutil.copy2(SOURCE, h2s_dest)
    if jarv_dest.exists() and not args.force:
        print(f"Refusing to overwrite {jarv_dest} (use --force).", file=sys.stderr)
        return 1
    jarv_dest.write_text(JARVIS_FLAT, encoding="utf-8")
    print(f"Wrote {h2s_dest}")
    print(f"Wrote {jarv_dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
