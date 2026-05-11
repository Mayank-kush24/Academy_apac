"""
Persist a byte-identical copy of each uploaded import file under the repo's archive tree.
Strict mode: callers must not parse or mutate DB until this returns successfully.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.utils import secure_filename

log = logging.getLogger(__name__)

_KIND_RE = re.compile(r"^[a-z0-9_]{1,80}$")

CHUNK = 1024 * 1024


class ImportArchiveError(Exception):
    """Raised when the upload cannot be written to the archive (strict: abort import)."""


def get_repo_root() -> Path:
    """Repository root (parent of ``server/``)."""
    return Path(__file__).resolve().parents[2]


def get_default_archive_root() -> str:
    env = (os.environ.get("IMPORT_FILE_ARCHIVE_DIR") or "").strip()
    if env:
        return os.path.abspath(env)
    return str(get_repo_root() / "import_file_archive")


def _resolve_archive_root() -> str:
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            cfg = current_app.config.get("IMPORT_FILE_ARCHIVE_DIR")
            if cfg:
                return os.path.abspath(str(cfg))
    except Exception:
        pass
    return get_default_archive_root()


def archive_upload(file, *, kind: str) -> str:
    """
    Copy the raw upload body to
    ``{root}/{UTC-date}/{kind}/{UTCstamp}_{uuid}_{secure_name}``.

    :param file: werkzeug ``FileStorage``
    :param kind: slug e.g. ``main_import_preview`` (lowercase letters, digits, underscore)
    :returns: absolute path to the archived file
    :raises ImportArchiveError: on invalid input, non-rewindable stream, or I/O failure
    """
    if not _KIND_RE.match(kind or ""):
        raise ImportArchiveError("Invalid archive kind identifier")

    filename = getattr(file, "filename", None) or ""
    if not file or not str(filename).strip():
        raise ImportArchiveError("No file to archive")

    stream = getattr(file, "stream", None)
    if stream is None:
        raise ImportArchiveError("Upload has no stream")

    try:
        stream.seek(0)
    except (OSError, IOError, AttributeError) as e:
        raise ImportArchiveError(
            "Could not rewind the upload stream; save the file and upload again."
        ) from e

    root = _resolve_archive_root()
    date_part = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dest_dir = os.path.join(root, date_part, kind)
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except OSError as e:
        log.exception("import archive mkdir failed kind=%s dir=%s", kind, dest_dir)
        raise ImportArchiveError(f"Cannot create archive directory: {e}") from e

    orig_name = str(filename).strip() or "upload"
    safe = secure_filename(orig_name) or "upload"
    if safe in (".", ".."):
        safe = "upload"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    short_uuid = uuid.uuid4().hex[:12]
    final_name = f"{stamp}_{short_uuid}_{safe}"
    final_path = os.path.join(dest_dir, final_name)
    tmp_path = final_path + ".part"

    try:
        with open(tmp_path, "wb") as out:
            while True:
                chunk = stream.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp_path, final_path)
    except Exception as e:
        try:
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        log.exception(
            "import archive failed kind=%s original_filename=%r",
            kind,
            orig_name,
        )
        raise ImportArchiveError(f"Failed to save import archive: {e}") from e

    log.info(
        "import archive ok kind=%s path=%s original_filename=%r",
        kind,
        final_path,
        orig_name,
    )
    return final_path
