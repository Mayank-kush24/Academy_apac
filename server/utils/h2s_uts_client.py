"""
Hack2Skill UTS API client for Cohort 3 (apac-genaiacademy-c3).

Env:
  H2S_UTS_API_KEY          required
  H2S_UTS_AUTH_HEADER      default Authorization  (or e.g. x-api-key)
  H2S_UTS_AUTH_PREFIX      default Bearer  (empty string for raw key headers)
  H2S_UTS_BASE_URL         default https://hack2skill.com
  H2S_UTS_EVENT_SLUG       default apac-genaiacademy-c3
  H2S_UTS_TIMEOUT_SEC      default 120
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests


#: Hard server-side cap on rows returned by one registrations response.
REGISTRATION_PAGE_SIZE = 50000


class H2SUtsError(Exception):
    """Raised when the UTS API returns an error or is misconfigured."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip()


class H2SUtsClient:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        event_slug: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.api_key = (api_key if api_key is not None else _env("H2S_UTS_API_KEY")).strip()
        if not self.api_key:
            raise H2SUtsError(
                "H2S_UTS_API_KEY is not set. Add it to your .env file before syncing Cohort 3."
            )
        self.base_url = (
            base_url if base_url is not None else _env("H2S_UTS_BASE_URL", "https://hack2skill.com")
        ).rstrip("/")
        self.event_slug = (
            event_slug if event_slug is not None else _env("H2S_UTS_EVENT_SLUG", "apac-genaiacademy-c3")
        ).strip()
        try:
            self.timeout = float(
                timeout if timeout is not None else _env("H2S_UTS_TIMEOUT_SEC", "120") or "120"
            )
        except ValueError:
            self.timeout = 120.0

        self.auth_header = _env("H2S_UTS_AUTH_HEADER", "Authorization") or "Authorization"
        # Empty prefix → send raw key (typical for x-api-key).
        prefix = os.environ.get("H2S_UTS_AUTH_PREFIX")
        if prefix is None:
            prefix = "Bearer" if self.auth_header.lower() == "authorization" else ""
        self.auth_prefix = str(prefix).strip()

    def _headers(self) -> Dict[str, str]:
        value = f"{self.auth_prefix} {self.api_key}".strip() if self.auth_prefix else self.api_key
        return {
            self.auth_header: value,
            "Accept": "application/json",
        }

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self._url(path)
        try:
            resp = requests.get(
                url,
                headers=self._headers(),
                params=params or None,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise H2SUtsError(f"UTS request failed: {exc}") from exc

        if resp.status_code >= 400:
            body = (resp.text or "")[:1000]
            raise H2SUtsError(
                f"UTS API HTTP {resp.status_code} for {path}: {body}",
                status_code=resp.status_code,
                body=body,
            )
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as exc:
            raise H2SUtsError(f"UTS API returned non-JSON for {path}") from exc

    def fetch_registrations(self, start: Optional[str] = None) -> Any:
        """
        GET /api/v1/event/{slug}/uts[?start=ISO].

        The endpoint caps every response at REGISTRATION_PAGE_SIZE rows and ignores
        ``limit``, ``skip``, ``offset`` and ``pageSize``. The cap applies to a window
        anchored at ``start``, so callers reach past it by advancing ``start`` rather
        than by asking for a larger response.
        """
        params: Dict[str, Any] = {}
        if start:
            params["start"] = start
        return self._get(f"/api/v1/event/{self.event_slug}/uts", params=params)

    def fetch_modules(self) -> Any:
        """GET /api/v1/submission/{slug}/uts/modules."""
        return self._get(f"/api/v1/submission/{self.event_slug}/uts/modules")

    def fetch_module_data(self, module_id: str) -> Any:
        """GET /api/v1/submission/{slug}/uts/{module_id}."""
        mid = str(module_id).strip().strip("/")
        if not mid:
            raise H2SUtsError("module_id is required")
        return self._get(f"/api/v1/submission/{self.event_slug}/uts/{mid}")


def _tabular_rows_to_dicts(rows: List[Any]) -> List[Dict[str, Any]]:
    """
    Convert UTS tabular payloads [[header...], [row...], ...] into list of dicts.
    First row is treated as column headers when it is a list.
    """
    if not rows or not isinstance(rows[0], list):
        return []
    headers: List[str] = []
    for i, h in enumerate(rows[0]):
        if h is None or str(h).strip() == "":
            headers.append(f"col_{i}")
        else:
            headers.append(str(h).strip())
    out: List[Dict[str, Any]] = []
    for row in rows[1:]:
        if not isinstance(row, list):
            continue
        # Skip empty / all-null rows
        if not any(v is not None and str(v).strip() != "" for v in row):
            continue
        item: Dict[str, Any] = {}
        for i, header in enumerate(headers):
            item[header] = row[i] if i < len(row) else None
        out.append(item)
    return out


def extract_records(payload: Any) -> List[Dict[str, Any]]:
    """
    Normalize UTS list payloads into a list of dict rows.

    Supports:
      - list of dicts
      - { data: [ {...}, ... ] }
      - { data: [ [headers...], [values...], ... ] }  (Hack2Skill UTS tabular)
    """
    if payload is None:
        return []

    def _from_list(val: list) -> List[Dict[str, Any]]:
        if not val:
            return []
        if isinstance(val[0], list):
            return _tabular_rows_to_dicts(val)
        return [r for r in val if isinstance(r, dict)]

    if isinstance(payload, list):
        return _from_list(payload)
    if not isinstance(payload, dict):
        return []

    for key in (
        "data",
        "rows",
        "results",
        "registrations",
        "users",
        "submissions",
        "items",
        "records",
    ):
        val = payload.get(key)
        if isinstance(val, list):
            return _from_list(val)

    # Nested { data: { rows: [...] } }
    data = payload.get("data")
    if isinstance(data, dict):
        return extract_records(data)

    return []


def extract_modules(payload: Any) -> List[Dict[str, Any]]:
    """
    Normalize modules list. Each item should include an id and preferably a name.
    Accepts list of dicts or list of raw ids/strings.
    """
    if payload is None:
        return []

    raw_list: Optional[list] = None
    if isinstance(payload, list):
        raw_list = payload
    elif isinstance(payload, dict):
        for key in ("data", "modules", "results", "items"):
            val = payload.get(key)
            if isinstance(val, list):
                raw_list = val
                break
        if raw_list is None:
            if payload.get("id") or payload.get("moduleId") or payload.get("module_id") or payload.get("_id"):
                return [payload]
            return []

    out: List[Dict[str, Any]] = []
    for item in raw_list or []:
        if isinstance(item, dict):
            out.append(item)
        elif item is not None and str(item).strip():
            out.append({"id": str(item).strip(), "name": str(item).strip()})
    return out


def module_id_of(mod: Dict[str, Any]) -> str:
    for k in ("id", "moduleId", "module_id", "_id", "slug", "key"):
        v = mod.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def module_name_of(mod: Dict[str, Any]) -> str:
    for k in ("name", "title", "label", "moduleName", "module_name", "displayName"):
        v = mod.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return module_id_of(mod)
