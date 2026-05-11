"""Read image URLs from CSV."""
from __future__ import annotations

import csv
import io
from typing import Iterator


def _normalize_header(h: str) -> str:
    return (h or "").strip().lower().replace(" ", "_")


def pick_url_column(fieldnames: list[str] | None, preferred: str | None) -> str:
    if not fieldnames:
        raise ValueError("CSV has no header row")
    headers = [h for h in fieldnames if h is not None]
    if preferred:
        p = preferred.strip()
        for h in headers:
            if h == p or _normalize_header(h) == _normalize_header(p):
                return h
        raise ValueError(f"Column not found: {preferred!r}")
    nh = [_normalize_header(h) for h in headers]
    for i, name in enumerate(nh):
        if "image" in name and "url" in name:
            return headers[i]
        if name in ("image_url", "image_link", "screenshot", "screenshot_url"):
            return headers[i]
        if "url" in name or name.endswith("_link"):
            return headers[i]
    for i, name in enumerate(nh):
        if "url" in name or "link" in name:
            return headers[i]
    return headers[0]


def iter_url_rows(
    file_bytes: bytes,
    *,
    url_column: str | None,
    encoding: str = "utf-8-sig",
) -> Iterator[tuple[int, dict[str, str], str]]:
    """
    Yields (row_index_1based, row_dict, url).
    Skips rows with empty URL.
    """
    text = file_bytes.decode(encoding, errors="replace")
    f = io.StringIO(text)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    f.seek(0)
    reader = csv.DictReader(f, dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("Could not read CSV headers")
    col = pick_url_column(list(reader.fieldnames), url_column)
    for i, row in enumerate(reader, start=1):
        url = (row.get(col) or "").strip()
        if not url:
            continue
        clean = {k: (v or "").strip() for k, v in row.items() if k is not None}
        yield i, clean, url
