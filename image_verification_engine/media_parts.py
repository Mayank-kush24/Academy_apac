"""
Split downloaded bytes into one or more image parts for Gemini (single image or PDF pages).
"""
from __future__ import annotations

from urllib.parse import urlparse

from pdf_render import render_pdf_pages_to_png


def _looks_like_pdf(data: bytes, url: str, content_type: str | None) -> bool:
    if data[:4] == b"%PDF":
        return True
    ct = (content_type or "").lower()
    if "application/pdf" in ct:
        return True
    path = urlparse(url).path.lower()
    return path.endswith(".pdf")


def _sniff_image_mime(data: bytes, fallback: str) -> str:
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    fb = fallback.split(";")[0].strip().lower()
    if fb.startswith("image/"):
        return fb
    return "image/jpeg"


def bytes_to_verify_parts(
    *,
    data: bytes,
    url: str,
    content_type: str | None,
    max_pdf_pages: int,
    pdf_page_max_side_px: int,
) -> list[tuple[str, bytes, str]]:
    """
    Returns list of (label, bytes, mime_type) to send to Gemini.
    PDFs -> one part per rendered page (PNG). Images -> single part.
    """
    if _looks_like_pdf(data, url, content_type):
        pages = render_pdf_pages_to_png(
            data,
            max_pages=max_pdf_pages,
            page_max_side_px=pdf_page_max_side_px,
        )
        if not pages:
            raise ValueError("PDF has no renderable pages")
        return [(label, png, "image/png") for label, png in pages]

    mime = _sniff_image_mime(data, content_type or "")
    return [("Image", data, mime)]
