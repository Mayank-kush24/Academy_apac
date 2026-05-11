"""Render PDF pages to PNG bytes for vision verification."""
from __future__ import annotations

import logging
from typing import List, Tuple

import fitz  # PyMuPDF

log = logging.getLogger(__name__)


def render_pdf_pages_to_png(
    pdf_bytes: bytes,
    *,
    max_pages: int,
    page_max_side_px: int,
) -> List[Tuple[str, bytes]]:
    """
    Returns [(label, png_bytes), ...] one entry per page (up to max_pages).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        n = min(len(doc), max_pages)
        if len(doc) > max_pages:
            log.warning("PDF has %s pages; only first %s are verified", len(doc), max_pages)
        out: List[Tuple[str, bytes]] = []
        for i in range(n):
            page = doc[i]
            rect = page.rect
            w, h = rect.width, rect.height
            if w <= 0 or h <= 0:
                continue
            scale = min(page_max_side_px / max(w, h), 3.0)
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            png = pix.tobytes("png")
            label = f"PDF page {i + 1}/{len(doc)}"
            out.append((label, png))
        return out
    finally:
        doc.close()
