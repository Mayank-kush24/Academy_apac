"""Download https URLs (images or PDFs) with size limits."""
from __future__ import annotations

import mimetypes
from urllib.parse import urlparse

import requests

DEFAULT_TIMEOUT = 60


def _guess_declared_mime(url: str, content_type: str | None) -> str | None:
    if content_type:
        base = content_type.split(";")[0].strip().lower()
        if base and base != "application/octet-stream":
            return base
    path = urlparse(url).path.lower()
    mt, _ = mimetypes.guess_type(path)
    return mt


def download_https(url: str, max_bytes: int) -> tuple[bytes, str | None]:
    """
    Download URL body. Returns (data, Content-Type header value or None).
    """
    url = (url or "").strip()
    if not url.lower().startswith("https://"):
        raise ValueError("Only https:// URLs are allowed")
    r = requests.get(
        url,
        timeout=DEFAULT_TIMEOUT,
        stream=True,
        headers={"User-Agent": "ImageVerificationEngine/1.0"},
    )
    r.raise_for_status()
    ct = r.headers.get("Content-Type")
    total = 0
    chunks: list[bytes] = []
    for chunk in r.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"Download larger than {max_bytes} bytes")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise ValueError("Empty response body")
    return data, ct
