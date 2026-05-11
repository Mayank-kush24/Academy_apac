"""
Gemini multimodal verification: image bytes + system instruction -> validity + usage tokens.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types

log = logging.getLogger(__name__)

USER_PROMPT = """Analyze the image according to your system instructions.
Respond with a single JSON object only (no markdown fences). Follow the output shape required there
(typically "status" + "reason", or "valid" + "notes"). Do not add labels like "Image:" before the JSON."""

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.I)


def _first_json_object(text: str) -> dict | None:
    """If the model prefixes prose (e.g. 'Image: {...}'), extract the first {...} object."""
    text = (text or "").strip()
    start = text.find("{")
    if start < 0:
        return None
    decoder = json.JSONDecoder()
    try:
        obj, _end = decoder.raw_decode(text, start)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _status_to_bool(status: Any) -> bool | None:
    if status is None:
        return None
    if isinstance(status, bool):
        return status
    if isinstance(status, str):
        s = status.strip().upper()
        if s == "PASS":
            return True
        if s == "FAIL":
            return False
    return None


def _dict_to_valid_notes(data: dict) -> tuple[bool | None, str] | None:
    """Returns (valid, notes) if this dict carries a verdict, else None."""
    if "valid" in data and isinstance(data.get("valid"), bool):
        notes = str(data.get("notes") or data.get("reason") or "").strip()
        return (data["valid"], notes)
    if "status" in data:
        vb = _status_to_bool(data.get("status"))
        if vb is not None:
            notes = str(data.get("reason") or data.get("notes") or "").strip()
            return (vb, notes)
    return None


def _usage_to_dict(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    keys = (
        "prompt_token_count",
        "candidates_token_count",
        "total_token_count",
        "cached_content_token_count",
        "thoughts_token_count",
    )
    out: dict[str, Any] = {}
    for key in keys:
        if hasattr(usage, key):
            v = getattr(usage, key)
            if v is not None:
                out[key] = v
    return out


def _parse_valid_json(text: str) -> tuple[bool | None, str, str | None]:
    """Returns (valid_bool, notes, raw_error)."""
    text = (text or "").strip()
    if not text:
        return None, "", "empty model text"
    # Whole string JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            got = _dict_to_valid_notes(data)
            if got is not None:
                v, notes = got
                return v, notes, None
    except json.JSONDecodeError:
        pass
    # Markdown fence
    m = _JSON_FENCE.search(text)
    if m:
        try:
            data = json.loads(m.group(1).strip())
            if isinstance(data, dict):
                got = _dict_to_valid_notes(data)
                if got is not None:
                    return got[0], got[1], None
        except json.JSONDecodeError:
            pass
    # Embedded object after prefix ("Image: { ... }", etc.)
    emb = _first_json_object(text)
    if emb is not None:
        got = _dict_to_valid_notes(emb)
        if got is not None:
            return got[0], got[1], None
    # Regex fallbacks (model sometimes returns slightly invalid JSON)
    sm = re.search(r'"status"\s*:\s*"([^"]+)"', text, re.I)
    if sm:
        vb = _status_to_bool(sm.group(1))
        if vb is not None:
            rm = re.search(r'"reason"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.I)
            notes = rm.group(1).replace('\\"', '"') if rm else text[:500]
            return vb, notes, None
    vm = re.search(r'"valid"\s*:\s*(true|false)', text, re.I)
    if vm:
        return vm.group(1).lower() == "true", text[:500], None
    return None, text[:2000], "could not parse verdict (valid/status) from model JSON"


def verify_image_bytes(
    *,
    api_key: str,
    model: str,
    system_instruction: str,
    image_bytes: bytes,
    mime_type: str,
) -> dict[str, Any]:
    client = genai.Client(api_key=api_key)
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type or "image/jpeg"),
                types.Part.from_text(text=USER_PROMPT),
            ],
        )
    ]
    base_config = dict(
        system_instruction=system_instruction.strip(),
        temperature=0.2,
    )
    try:
        config = types.GenerateContentConfig(
            **base_config,
            response_mime_type="application/json",
        )
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
    except Exception as e:
        log.debug("JSON response mode failed (%s), retrying without", e)
        config = types.GenerateContentConfig(**base_config)
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
    text = ""
    if response.candidates:
        for cand in response.candidates:
            if not cand.content or not cand.content.parts:
                continue
            for part in cand.content.parts:
                if part.text:
                    text += part.text
    usage = _usage_to_dict(getattr(response, "usage_metadata", None))
    prompt_tc = usage.get("prompt_token_count")
    cand_tc = usage.get("candidates_token_count")
    total_tc = usage.get("total_token_count")
    bifurcation = {
        "prompt_token_count": prompt_tc,
        "candidates_token_count": cand_tc,
        "total_token_count": total_tc,
    }
    if not text.strip():
        fr = None
        if response.candidates:
            fr = getattr(response.candidates[0], "finish_reason", None)
        return {
            "valid": None,
            "notes": "",
            "model_text": "",
            "parse_error": "empty model response" + (f" (finish_reason={fr!s})" if fr else ""),
            "usage_metadata": usage,
            "tokens": {"total": total_tc, "bifurcation": bifurcation},
        }
    valid, notes, parse_err = _parse_valid_json(text)
    return {
        "valid": valid,
        "notes": notes,
        "model_text": text[:8000] if text else "",
        "parse_error": parse_err,
        "usage_metadata": usage,
        "tokens": {
            "total": total_tc,
            "bifurcation": bifurcation,
        },
    }
