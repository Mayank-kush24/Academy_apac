"""
Dashboard Data Intelligence: aggregate metrics -> Gemini -> short insight strings.
Uses only pre-aggregated summary/charts; no row-level PII.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import APIError

log = logging.getLogger(__name__)

# AI Studio / generateContent: use a model id from "List models" in Google AI Studio.
# Legacy ids like gemini-1.5-flash-002 often return 404 on current API versions.
_FALLBACK_GEMINI_MODEL = "gemini-2.0-flash"


def _model_try_order(primary: str) -> list[str]:
    p = (primary or "").strip() or _FALLBACK_GEMINI_MODEL
    if p == _FALLBACK_GEMINI_MODEL:
        return [p]
    return [p, _FALLBACK_GEMINI_MODEL]

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.I)

_SYSTEM = """You are a senior data strategist briefing program leadership on an academy / upskilling dashboard.

You receive ONLY aggregate JSON (counts, rates, top-N buckets). There is no per-user row data.

What to produce:
- 5 to 7 distinct insights. Each insight should be 1–2 sentences (aim under 320 characters per item).
- Prioritize synthesis and interpretation: momentum, concentration risk, channel or persona skew, regional balance, funnel health (registrations vs verification vs submissions), and one concrete implication or priority implied by the numbers.
- Each insight must cover a different angle; do not repeat the same idea with different wording.
- You may compare metrics that appear together in the JSON (e.g. verified vs total, India vs APAC, top city share vs tail). Do not invent entities, regions, or numbers not supported by the input.

Hard rules:
- Every number, name (city, org, country, domain bucket), and percentage must be traceable to the input JSON.
- No individual identification; aggregates only.
- Output a single JSON value only (no markdown fences, no commentary). Prefer this object shape: {"insights": ["...", "..."]}.
- If most metrics are zero or null, return 4 brief insights explaining sparsity and what is missing."""


def _row_label(row: dict[str, Any]) -> str | None:
    for key in ("label", "state", "country", "name"):
        v = row.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _trim_label_value(items: list[dict[str, Any]] | None, cap: int) -> list[dict[str, Any]]:
    if not items:
        return []
    out = []
    for row in items[:cap]:
        if not isinstance(row, dict):
            continue
        label = _row_label(row)
        value = row.get("value")
        if label is not None and value is not None:
            out.append({"label": label[:120], "value": value})
    return out


def _compact_track_rows(rows: Any, cap: int = 6) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows[:cap]:
        if not isinstance(row, dict):
            continue
        slim = {k: row.get(k) for k in ("track", "total", "verified", "passed_6", "unique_users", "unique_passed_6") if row.get(k) is not None}
        if slim:
            out.append(slim)
    return out


def build_insights_context(
    summary: dict[str, Any],
    charts: dict[str, Any],
    period: str,
    cohort_id: int | None,
) -> dict[str, Any]:
    """Compact JSON-serializable dict for the model (length-capped lists)."""
    reg = charts.get("registration_trends") or []
    if isinstance(reg, list) and len(reg) > 21:
        reg = reg[-21:]

    seg = charts.get("user_segmentation") or {}
    industries = seg.get("industries") if isinstance(seg, dict) else None

    ctx: dict[str, Any] = {
        "period_filter": period or "all",
        "cohort_id": cohort_id,
        "summary": {
            "total_users": summary.get("total_users"),
            "unique_organizations": summary.get("unique_organizations"),
            "unique_countries": summary.get("unique_countries"),
            "top_domain": summary.get("top_domain"),
            "top_city": summary.get("top_city"),
            "top_organization": summary.get("top_organization"),
            "average_age": summary.get("average_age"),
            "apac_except_india_users": summary.get("apac_except_india_users"),
            "india_registrations": summary.get("india_registrations"),
            "sea_registrations": summary.get("sea_registrations"),
            "anz_registrations": summary.get("anz_registrations"),
            "greater_china_registrations": summary.get("greater_china_registrations"),
            "korea_registrations": summary.get("korea_registrations"),
            "others_registrations": summary.get("others_registrations"),
            "top_india_state": summary.get("top_india_state"),
            "top_india_city": summary.get("top_india_city"),
            "top_apac_country": summary.get("top_apac_country"),
            "total_skillboost_profiles": summary.get("total_skillboost_profiles"),
            "verified_skillboost_profiles": summary.get("verified_skillboost_profiles"),
            "skillboost_verification_rate": summary.get("skillboost_verification_rate"),
            "total_skilllab_submissions": summary.get("total_skilllab_submissions"),
            "verified_skilllab_submissions": summary.get("verified_skilllab_submissions"),
            "skilllab_submission_verification_rate": summary.get("skilllab_submission_verification_rate"),
            "total_codelab_submissions": summary.get("total_codelab_submissions"),
            "verified_codelab_submissions": summary.get("verified_codelab_submissions"),
            "codelab_submission_verification_rate": summary.get("codelab_submission_verification_rate"),
            "total_project_submissions": summary.get("total_project_submissions"),
            "verified_project_submissions": summary.get("verified_project_submissions"),
            "project_submission_verification_rate": summary.get("project_submission_verification_rate"),
            "project_submission_program_target": summary.get("project_submission_program_target"),
            "project_submission_track_target": summary.get("project_submission_track_target"),
            "project_submission_by_track": _compact_track_rows(summary.get("project_submission_by_track")),
            "optional_mcq_by_track": _compact_track_rows(summary.get("optional_mcq_by_track")),
            "main_mcq_by_track": _compact_track_rows(summary.get("main_mcq_by_track")),
            "users_with_github": summary.get("users_with_github"),
            "users_with_linkedin": summary.get("users_with_linkedin"),
            "previous_period_total_users": summary.get("previous_period_total_users"),
            "previous_period_apac_users": summary.get("previous_period_apac_users"),
            "book_of_business_registrations": summary.get("book_of_business_registrations"),
        },
        "charts": {
            "registration_trends": reg,
            "top_cities": _trim_label_value(charts.get("top_cities"), 10),
            "top_cities_outside_india": _trim_label_value(charts.get("top_cities_outside_india"), 8),
            "top_organizations": _trim_label_value(charts.get("top_organizations"), 10),
            "top_domains": _trim_label_value(charts.get("top_domains"), 10),
            "gender_distribution": _trim_label_value(charts.get("gender_distribution"), 12),
            "persona_distribution": _trim_label_value(charts.get("persona_distribution"), 12),
            "occupation_distribution": _trim_label_value(charts.get("occupation_distribution"), 10),
            "registration_source_bifurcation": _trim_label_value(
                charts.get("registration_source_bifurcation"), 8
            ),
            "age_groups": _trim_label_value(charts.get("age_groups"), 12),
            "india_state_registrations": _trim_label_value(charts.get("india_state_registrations"), 15),
            "apac_country_registrations": _trim_label_value(charts.get("apac_country_registrations"), 15),
            "user_segmentation_industries": _trim_label_value(industries, 12),
        },
    }
    return ctx


def _extract_json_value(text: str) -> Any | None:
    """Parse first JSON object or array from model text."""
    text = (text or "").strip()
    if not text:
        return None
    for attempt in (text,):
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            pass
    m = _JSON_FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    start_obj = text.find("{")
    start_arr = text.find("[")
    if start_obj >= 0 and (start_arr < 0 or start_obj <= start_arr):
        decoder = json.JSONDecoder()
        try:
            obj, _end = decoder.raw_decode(text, start_obj)
            return obj
        except (json.JSONDecodeError, ValueError):
            pass
    if start_arr >= 0:
        decoder = json.JSONDecoder()
        try:
            obj, _end = decoder.raw_decode(text, start_arr)
            return obj
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _normalize_one_item(item: Any) -> str | None:
    if isinstance(item, str) and item.strip():
        s = " ".join(item.strip().split())
        if len(s) > 450:
            s = s[:447] + "..."
        return s
    if isinstance(item, dict):
        for key in ("insight", "text", "statement", "summary", "message"):
            t = item.get(key)
            if isinstance(t, str) and t.strip():
                s = " ".join(t.strip().split())
                if len(s) > 450:
                    s = s[:447] + "..."
                return s
    return None


def _insights_from_parsed_root(data: Any) -> list[str]:
    out: list[str] = []
    if isinstance(data, list):
        for item in data:
            s = _normalize_one_item(item)
            if s:
                out.append(s)
            if len(out) >= 8:
                break
        return out
    if isinstance(data, dict):
        for key in ("insights", "items", "points", "bullets", "findings"):
            raw = data.get(key)
            if isinstance(raw, list):
                for item in raw:
                    s = _normalize_one_item(item)
                    if s:
                        out.append(s)
                    if len(out) >= 8:
                        return out
    return out


def _collect_model_text(response: Any) -> str:
    text = ""
    if response.candidates:
        for cand in response.candidates:
            if not cand.content or not cand.content.parts:
                continue
            for part in cand.content.parts:
                if part.text:
                    text += part.text
    return (text or "").strip()


def _generate_insights_with_model(
    client: genai.Client,
    resolved_model: str,
    contents: list,
    base_kw: dict,
) -> list[str]:
    """Single model id: try JSON MIME mode then plain text; raise APIError 404 to caller for fallback."""
    last_text = ""
    for use_json_mime in (True, False):
        try:
            if use_json_mime:
                config = types.GenerateContentConfig(
                    **base_kw,
                    response_mime_type="application/json",
                )
            else:
                config = types.GenerateContentConfig(**base_kw)
            response = client.models.generate_content(
                model=resolved_model,
                contents=contents,
                config=config,
            )
        except APIError as e:
            if getattr(e, "code", None) == 404:
                raise
            if use_json_mime:
                log.debug("Gemini JSON mime mode failed, retrying without: %s", e)
                continue
            raise
        except Exception as e:
            if use_json_mime:
                log.debug("Gemini JSON mime mode failed, retrying without: %s", e)
                continue
            raise
        text = _collect_model_text(response)
        if not text:
            fr = None
            if response.candidates:
                fr = getattr(response.candidates[0], "finish_reason", None)
            raise RuntimeError(
                "empty model response" + (f" (finish_reason={fr!s})" if fr else "")
            )
        last_text = text
        parsed = _extract_json_value(last_text)
        insights = _insights_from_parsed_root(parsed) if parsed is not None else []
        if insights:
            return insights[:8]

    if last_text:
        log.debug("Could not parse insights from model text (first 400 chars): %s", last_text[:400])
    raise RuntimeError("could not parse any insights from model output")


def generate_dashboard_insights(api_key: str, model: str, context: dict[str, Any]) -> list[str]:
    """
    Call Gemini; return insight strings. Raises only when the model returns nothing usable.
    On 404 NOT_FOUND for the configured model id, retries with a known-good fallback model.
    """
    client = genai.Client(api_key=api_key)
    user_text = (
        "Analyze the JSON below and write the insights JSON per your system instructions.\n"
        "Cover multiple facets of the dataset; avoid repeating one metric across bullets.\n\n"
        + json.dumps(context, default=str, ensure_ascii=False)
    )
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_text)],
        )
    ]
    base_kw = dict(system_instruction=_SYSTEM.strip(), temperature=0.58)

    candidates = _model_try_order(model)
    for resolved_model in candidates:
        try:
            return _generate_insights_with_model(client, resolved_model, contents, base_kw)
        except APIError as e:
            if getattr(e, "code", None) == 404 and resolved_model != candidates[-1]:
                log.warning(
                    "Gemini model %r not found for generateContent (404); trying %r",
                    resolved_model,
                    candidates[-1],
                )
                continue
            raise
