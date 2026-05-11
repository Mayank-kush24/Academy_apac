"""
Dashboard analytics routes
"""
import logging
import os
from collections import defaultdict
from flask import Blueprint, jsonify, request, current_app, g
from sqlalchemy import func, desc, case, or_, and_, text
from datetime import datetime, timedelta, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from server.models import db, UserPIICombined, SkillboostProfile, SkillLabSubmission, CodeLabSubmission, ProjectSubmission, OptionalMcqResponse, MainMcqResponse
from server.utils.auth import get_current_user
from server.utils.mcq_answer_key import score_submission, get_response_score
from server.utils.permissions import require_page_access
from server.utils.cache import cache_result
from server.config import Config
from server.utils.dashboard_gemini_insights import (
    build_insights_context,
    generate_dashboard_insights,
)
from server.utils.state_normalize import normalize_state, merge_state_count_rows
from server.utils.country_normalize import (
    country_column_matches_canonical,
    country_column_matches_any_canonical,
    merge_country_count_rows,
    normalize_country,
)

logger = logging.getLogger(__name__)

# Gemini insights cache. Successful responses kept long (data only changes on import); rate-limit
# responses cooled-off process-wide; previously-good ("stale") insights served while rate-limited
# instead of falling back to rule-based bullets.
_AI_INSIGHTS_FRESH_TTL_SEC = int(os.environ.get("GEMINI_INSIGHTS_FRESH_TTL_SEC", "3600"))
_AI_INSIGHTS_STALE_MAX_AGE_SEC = int(os.environ.get("GEMINI_INSIGHTS_STALE_MAX_AGE_SEC", "86400"))
_AI_INSIGHTS_RATE_LIMIT_COOLDOWN_SEC = int(
    os.environ.get("GEMINI_INSIGHTS_RATE_LIMIT_COOLDOWN_SEC", "600")
)

_ai_insights_success_store: dict = {}
_ai_insights_rate_limit_until = None  # type: datetime | None


def _is_rate_limit_message(msg: str) -> bool:
    upper = (msg or "").upper()
    return "429" in upper and ("RESOURCE_EXHAUSTED" in upper or "RATE" in upper or "QUOTA" in upper)

# Canonical APAC names for filters (aliases like "Asia Pacific" roll up via "APAC" in country map)
APAC_COUNTRIES_CANONICAL = [
    'Australia', 'Bangladesh', 'Bhutan', 'Brunei', 'Cambodia', 'China',
    'Fiji', 'Hong Kong', 'Indonesia', 'Japan', 'Laos', 'Malaysia',
    'Maldives', 'Mongolia', 'Myanmar', 'Nepal', 'New Zealand',
    'North Korea', 'Pakistan', 'Papua New Guinea', 'Philippines',
    'Singapore', 'South Korea', 'Sri Lanka', 'Taiwan', 'Thailand',
    'Timor-Leste', 'Vietnam', 'APAC',
]
APAC_FOR_MAP_EXCL_INDIA = APAC_COUNTRIES_CANONICAL

bp = Blueprint('dashboard', __name__)

from server.utils.industry_map import INDUSTRY_DOMAIN_MAP, _DOMAIN_INDUSTRY_LOOKUP, get_industry
from server.utils.persona_map import get_persona

# Module-level cached combined dashboard (summary + charts) - one cache entry per period
@cache_result(ttl=900)
def _get_dashboard_data_cached(period, table_prefix=''):
    """Fetch summary and charts in parallel; cached per (period, cohort prefix) for 15 min."""
    from server.utils.cohort_participant_models import apply_cohort_globals

    app = current_app._get_current_object()
    cohort_id = getattr(g, 'cohort_id', None)

    def _run_summary():
        with app.app_context():
            apply_cohort_globals(table_prefix, cohort_id)
            return _fetch_summary_data(period)

    def _run_charts():
        with app.app_context():
            apply_cohort_globals(table_prefix, cohort_id)
            return _fetch_charts_data(period)

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_summary = pool.submit(_run_summary)
        fut_charts = pool.submit(_run_charts)
        summary = fut_summary.result()
        charts = fut_charts.result()

    return {'summary': summary, 'charts': charts}


def _safe_scalar(sql: str, params: dict = None) -> int:
    """Execute a scalar SQL query; return 0 on any error (e.g. table does not exist)."""
    try:
        result = db.session.execute(text(sql), params or {})
        val = result.scalar()
        return int(val) if val is not None else 0
    except Exception:
        db.session.rollback()
        return 0


def _safe_rows(sql: str, params: dict = None) -> list:
    """Execute a row-returning SQL query; return [] on any error."""
    try:
        result = db.session.execute(text(sql), params or {})
        return result.fetchall()
    except Exception:
        db.session.rollback()
        return []


def _period_sql_filter(period: str, ts_col: str = "registered_at") -> tuple[str, dict]:
    """Return (WHERE clause fragment, params dict) for the given period."""
    if not period or period == "all":
        return "", {}
    now = datetime.now()
    if period == "month":
        cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        cutoff = now - timedelta(days=7)
    elif period == "30d":
        cutoff = now - timedelta(days=30)
    elif period == "90d":
        cutoff = now - timedelta(days=90)
    else:
        return "", {}
    return f" AND {ts_col} >= :cutoff", {"cutoff": cutoff}


def _prefixed_persona_distribution(pii: str, date_frag: str, date_params: dict) -> list:
    """
    Personas for cohort-prefixed combined PII: count stored persona when present; for rows
    with empty persona, bucket by get_persona(designation, occupation) — same mapping as imports.
    """
    agg = defaultdict(int)

    rows_p = _safe_rows(
        f"""SELECT persona, COUNT(*) AS n FROM {pii}
            WHERE persona IS NOT NULL AND TRIM(persona) != ''{date_frag}
            GROUP BY persona""",
        date_params,
    )
    for row in rows_p:
        pname, n = row[0], row[1]
        if pname and n is not None:
            agg[pname] += int(n)

    rows_d = _safe_rows(
        f"""SELECT designation, occupation, COUNT(*) AS n FROM {pii}
            WHERE (persona IS NULL OR TRIM(persona) = '')
              AND designation IS NOT NULL AND TRIM(designation) != ''{date_frag}
            GROUP BY designation, occupation""",
        date_params,
    )
    for desig, occ, n in rows_d:
        if n is None:
            continue
        agg[get_persona(desig, occupation=occ)] += int(n)

    out = [{"label": k, "value": v} for k, v in agg.items()]
    out.sort(key=lambda x: -x["value"])
    return out


def _fetch_prefixed_dashboard(prefix: str, period: str) -> dict:
    """
    Raw-SQL dashboard data for cohort-prefixed tables (Cohort 2+).
    Returns the same structure as _get_dashboard_data_cached().
    Gracefully returns zeros/empty arrays when tables have no data or don't exist.
    """
    pii   = f"{prefix}user_pii_combined"
    sb    = f"{prefix}skillboost_profile"
    sl    = f"{prefix}skilllab_submission"
    cl    = f"{prefix}codelab_submission"
    proj  = f"{prefix}project_submission"
    omcq  = f"{prefix}optional_mcq_response"
    mmcq  = f"{prefix}main_mcq_response"

    date_frag, date_params = _period_sql_filter(period)

    # --- Summary ---
    total_users = _safe_scalar(f"SELECT COUNT(*) FROM {pii} WHERE 1=1{date_frag}", date_params)

    india_count = _safe_scalar(
        f"SELECT COUNT(*) FROM {pii} WHERE LOWER(country) = 'india'{date_frag}", date_params
    )
    apac_excl_india = _safe_scalar(
        f"""SELECT COUNT(*) FROM {pii}
            WHERE country IS NOT NULL AND country != ''
              AND LOWER(country) != 'india'{date_frag}""",
        date_params,
    )

    top_india_state = None
    top_india_state_count = None
    row = _safe_rows(
        f"""SELECT state, COUNT(*) AS n FROM {pii}
            WHERE LOWER(country) = 'india' AND state IS NOT NULL AND state != ''{date_frag}
            GROUP BY state ORDER BY n DESC LIMIT 1""",
        date_params,
    )
    if row:
        top_india_state, top_india_state_count = row[0][0], int(row[0][1])

    top_india_city = None
    top_india_city_count = None
    row = _safe_rows(
        f"""SELECT city, COUNT(*) AS n FROM {pii}
            WHERE LOWER(country) = 'india' AND city IS NOT NULL AND city != ''{date_frag}
            GROUP BY city ORDER BY n DESC LIMIT 1""",
        date_params,
    )
    if row:
        top_india_city, top_india_city_count = row[0][0], int(row[0][1])

    top_apac_country = None
    top_apac_country_count = None
    row = _safe_rows(
        f"""SELECT country, COUNT(*) AS n FROM {pii}
            WHERE country IS NOT NULL AND country != '' AND LOWER(country) != 'india'{date_frag}
            GROUP BY country ORDER BY n DESC LIMIT 1""",
        date_params,
    )
    if row:
        top_apac_country, top_apac_country_count = row[0][0], int(row[0][1])

    bob_count = _safe_scalar(
        f"SELECT COUNT(*) FROM {pii} WHERE bob_match = TRUE{date_frag}", date_params
    )

    # Cohort 2 only: distinct users (email) present in Cohort 1 combined PII and in this cohort's PII
    users_in_cohort1_and_cohort2 = 0
    if prefix == "cohort_2_":
        c1_pii = "user_pii_combined"
        overlap_date = ""
        if date_frag:
            overlap_date = " AND c2.registered_at >= :cutoff"
        users_in_cohort1_and_cohort2 = _safe_scalar(
            f"""SELECT COUNT(DISTINCT LOWER(TRIM(c2.email))) FROM {pii} c2
                WHERE c2.email IS NOT NULL AND TRIM(c2.email) <> ''{overlap_date}
                  AND EXISTS (
                    SELECT 1 FROM {c1_pii} c1
                    WHERE c1.email IS NOT NULL AND TRIM(c1.email) <> ''
                      AND LOWER(TRIM(c1.email)) = LOWER(TRIM(c2.email))
                  )""",
            date_params,
        )

    # --- Regional counts (SEA, ANZ, Greater China, Korea) ---
    _SEA = ('brunei','cambodia','indonesia','laos','malaysia','myanmar',
            'philippines','singapore','thailand','timor-leste','vietnam')
    _ANZ = ('australia','new zealand')
    _GC  = ('china','hong kong','taiwan','mongolia')
    _KR  = ('south korea','north korea')

    def _region_count(canonical_tuple: tuple) -> int:
        placeholders = ','.join(f':c{i}' for i in range(len(canonical_tuple)))
        params = {f'c{i}': v for i, v in enumerate(canonical_tuple)}
        params.update(date_params)
        return _safe_scalar(
            f"SELECT COUNT(*) FROM {pii} WHERE LOWER(TRIM(country)) IN ({placeholders}){date_frag}",
            params,
        )

    def _region_top(canonical_tuple: tuple) -> str:
        placeholders = ','.join(f':c{i}' for i in range(len(canonical_tuple)))
        params = {f'c{i}': v for i, v in enumerate(canonical_tuple)}
        params.update(date_params)
        rows = _safe_rows(
            f"SELECT country, COUNT(*) AS n FROM {pii} WHERE LOWER(TRIM(country)) IN ({placeholders}){date_frag} GROUP BY country ORDER BY n DESC LIMIT 1",
            params,
        )
        return rows[0][0] if rows else None

    sea_registrations      = _region_count(_SEA)
    sea_top_country        = _region_top(_SEA)
    anz_registrations      = _region_count(_ANZ)
    anz_top_country        = _region_top(_ANZ)
    gc_registrations       = _region_count(_GC)
    gc_top_country         = _region_top(_GC)
    korea_registrations    = _region_count(_KR)
    korea_top_country      = _region_top(_KR)

    total_sb   = _safe_scalar(f"SELECT COUNT(*) FROM {sb}")
    verified_sb = _safe_scalar(f"SELECT COUNT(*) FROM {sb} WHERE valid = TRUE")
    sb_rate    = round(100.0 * verified_sb / total_sb, 1) if total_sb else None

    total_sl   = _safe_scalar(f"SELECT COUNT(*) FROM {sl}")
    verified_sl = _safe_scalar(f"SELECT COUNT(*) FROM {sl} WHERE valid = TRUE")
    sl_rate    = round(100.0 * verified_sl / total_sl, 1) if total_sl else None

    total_cl   = _safe_scalar(f"SELECT COUNT(*) FROM {cl}")
    verified_cl = _safe_scalar(f"SELECT COUNT(*) FROM {cl} WHERE valid = TRUE")
    cl_rate    = round(100.0 * verified_cl / total_cl, 1) if total_cl else None

    total_proj   = _safe_scalar(f"SELECT COUNT(*) FROM {proj}")
    verified_proj = _safe_scalar(f"SELECT COUNT(*) FROM {proj} WHERE valid = TRUE")
    proj_rate    = round(100.0 * verified_proj / total_proj, 1) if total_proj else None

    proj_by_track = []
    for t in (1, 2, 3):
        tot_t = _safe_scalar(f"SELECT COUNT(*) FROM {proj} WHERE track_number = :t", {"t": t})
        ver_t = _safe_scalar(f"SELECT COUNT(*) FROM {proj} WHERE track_number = :t AND valid = TRUE", {"t": t})
        proj_by_track.append({"track": t, "total": tot_t, "verified": ver_t})

    if prefix == "cohort_2_":
        tot_om = _safe_scalar(f"SELECT COUNT(*) FROM {omcq} WHERE track_number = 4", {})
        pass_om = _safe_scalar(
            f"SELECT COUNT(*) FROM {omcq} WHERE track_number = 4 AND score >= 6", {}
        )
        uniq_om = _safe_scalar(
            f"""SELECT COUNT(DISTINCT LOWER(TRIM(email))) FROM {omcq}
                WHERE track_number = 4 AND email IS NOT NULL AND TRIM(email) <> ''""",
            {},
        )
        uniq_pass_om = _safe_scalar(
            f"""SELECT COUNT(DISTINCT LOWER(TRIM(email))) FROM {omcq}
                WHERE track_number = 4 AND score >= 6
                  AND email IS NOT NULL AND TRIM(email) <> ''""",
            {},
        )
        opt_mcq_by_track = [
            {
                "track": 4,
                "total": tot_om,
                "passed_6": pass_om,
                "unique_users": uniq_om,
                "unique_passed_6": uniq_pass_om,
            }
        ]
    else:
        opt_mcq_by_track = [{"track": t, "total": 0, "passed_6": 0} for t in (1, 2, 3)]
        for i, t in enumerate((1, 2, 3)):
            tot_t = _safe_scalar(f"SELECT COUNT(*) FROM {omcq} WHERE track_number = :t", {"t": t})
            pass_t = _safe_scalar(
                f"SELECT COUNT(*) FROM {omcq} WHERE track_number = :t AND score >= 6", {"t": t}
            )
            opt_mcq_by_track[i] = {"track": t, "total": tot_t, "passed_6": pass_t}

    main_mcq_by_track = [{"track": t, "total": 0, "passed_6": 0} for t in (1, 2, 3)]
    for i, t in enumerate((1, 2, 3)):
        tot_t  = _safe_scalar(f"SELECT COUNT(*) FROM {mmcq} WHERE track_number = :t", {"t": t})
        pass_t = _safe_scalar(f"SELECT COUNT(*) FROM {mmcq} WHERE track_number = :t AND score >= 6", {"t": t})
        main_mcq_by_track[i] = {"track": t, "total": tot_t, "passed_6": pass_t}

    # ── average age ──────────────────────────────────────────────────────────
    avg_age_row = _safe_rows(
        f"SELECT AVG(EXTRACT(year FROM age(NOW()::date, date_of_birth::date))) FROM {pii} WHERE date_of_birth IS NOT NULL",
        {},
    )
    average_age = int(avg_age_row[0][0]) if avg_age_row and avg_age_row[0][0] else None

    # ── top organization (professionals / startups / freelancers) ─────────
    top_org_rows = _safe_rows(
        f"""SELECT organization_name, COUNT(*) AS n FROM {pii}
            WHERE organization_name IS NOT NULL AND organization_name != ''
              AND (LOWER(occupation) LIKE '%professional%'
                   OR LOWER(occupation) LIKE '%startup%'
                   OR LOWER(occupation) LIKE '%freelance%'){date_frag}
            GROUP BY organization_name ORDER BY n DESC LIMIT 1""",
        date_params,
    )
    top_organization = top_org_rows[0][0] if top_org_rows else "N/A"

    # --- Charts (group-bys) ---
    def _grp(col: str, limit: int = 20) -> list:
        rows = _safe_rows(
            f"SELECT {col}, COUNT(*) AS n FROM {pii} WHERE {col} IS NOT NULL AND {col} != ''{date_frag} GROUP BY {col} ORDER BY n DESC LIMIT {limit}",
            date_params,
        )
        return [{"label": r[0], "value": int(r[1])} for r in rows]

    gender_dist       = _grp("gender")
    top_domains       = _grp("domain", 10)
    top_cities        = _grp("city", 10)
    persona_dist      = _prefixed_persona_distribution(pii, date_frag, date_params)
    class_stream_dist = _grp("class_stream")

    # States – normalise + merge (e.g. "Uttar Pradesh" / "UP")
    raw_states = _safe_rows(
        f"SELECT state, COUNT(*) AS n FROM {pii} WHERE state IS NOT NULL AND state != ''{date_frag} GROUP BY state ORDER BY n DESC",
        date_params,
    )
    top_states = [{"label": lbl, "value": val}
                  for lbl, val in merge_state_count_rows([(r[0], int(r[1])) for r in raw_states])[:10]]

    # Country distribution – normalise + merge aliases
    raw_countries = _safe_rows(
        f"SELECT country, COUNT(*) AS n FROM {pii} WHERE country IS NOT NULL AND country != ''{date_frag} GROUP BY country ORDER BY n DESC",
        date_params,
    )
    country_dist = [{"label": lbl, "value": val}
                    for lbl, val in merge_country_count_rows([(r[0], int(r[1])) for r in raw_countries])[:10]]

    # Industry (user segmentation) – skip "Other"
    raw_ind = _safe_rows(
        f"SELECT industry, COUNT(*) AS n FROM {pii} WHERE industry IS NOT NULL AND industry != ''{date_frag} GROUP BY industry ORDER BY n DESC",
        date_params,
    )
    industry_list = []
    for ind_name, cnt in raw_ind:
        if not ind_name or ind_name == "Other":
            continue
        label = "Information Technology" if ind_name == "Technology" else ind_name
        industry_list.append({"label": label, "value": int(cnt)})
    industry_list.sort(key=lambda x: -x["value"])

    # Designation (top 10)
    designation_dist = _grp("designation", 10)

    # Registration source via UTM
    utm_rows = _safe_rows(
        f"SELECT utm_medium, COUNT(*) AS n FROM {pii}{(' WHERE 1=1' + date_frag) if date_frag else ''} GROUP BY utm_medium",
        date_params,
    )
    agg_src = {"Google": 0, "Outreach": 0, "Marketing": 0, "Ads": 0, "Hack2skill": 0, "Other": 0}
    for utm_val, cnt in utm_rows:
        agg_src[_utm_to_registration_source(utm_val)] += int(cnt or 0)
    reg_src = [{"label": k, "value": v} for k, v in agg_src.items()]

    # Occupation distribution (4 buckets)
    occ_rows = _safe_rows(
        f"SELECT occupation, COUNT(*) AS n FROM {pii} WHERE occupation IS NOT NULL AND occupation != ''{date_frag} GROUP BY occupation",
        date_params,
    )
    occ_agg = {"Professional": 0, "Student": 0, "Startup": 0, "Freelance": 0}
    for raw_occ, cnt in occ_rows:
        occ_agg[_normalize_occupation(raw_occ)] += int(cnt or 0)
    occ_dist = [{"label": k, "value": v} for k, v in occ_agg.items()]

    # Age groups via SQL CASE
    today_str = date.today().isoformat()
    age_rows = _safe_rows(
        f"""SELECT
              CASE
                WHEN EXTRACT(year FROM age('{today_str}'::date, date_of_birth::date)) BETWEEN 18 AND 25 THEN '18-25'
                WHEN EXTRACT(year FROM age('{today_str}'::date, date_of_birth::date)) BETWEEN 26 AND 35 THEN '26-35'
                WHEN EXTRACT(year FROM age('{today_str}'::date, date_of_birth::date)) BETWEEN 36 AND 45 THEN '36-45'
                WHEN EXTRACT(year FROM age('{today_str}'::date, date_of_birth::date)) BETWEEN 46 AND 55 THEN '46-55'
                WHEN EXTRACT(year FROM age('{today_str}'::date, date_of_birth::date)) > 55  THEN '56+'
              END AS grp,
              COUNT(*) AS n
            FROM {pii}
            WHERE date_of_birth IS NOT NULL
              AND EXTRACT(year FROM age('{today_str}'::date, date_of_birth::date)) >= 18
            GROUP BY grp ORDER BY grp""",
        {},
    )
    age_groups = [{"label": r[0], "value": int(r[1])} for r in age_rows if r[0]]

    # Social media presence (GitHub / LinkedIn)
    github_count   = _safe_scalar(f"SELECT COUNT(*) FROM {pii} WHERE github_url   IS NOT NULL AND github_url   != ''{date_frag}", date_params)
    linkedin_count = _safe_scalar(f"SELECT COUNT(*) FROM {pii} WHERE linkedin_url IS NOT NULL AND linkedin_url != ''{date_frag}", date_params)
    both_count     = _safe_scalar(
        f"SELECT COUNT(*) FROM {pii} WHERE github_url IS NOT NULL AND github_url != '' AND linkedin_url IS NOT NULL AND linkedin_url != ''{date_frag}",
        date_params,
    )
    neither_count  = max(0, total_users - github_count - linkedin_count + both_count)
    social_media = [
        {"label": "GitHub Only",   "value": max(0, github_count - both_count)},
        {"label": "LinkedIn Only", "value": max(0, linkedin_count - both_count)},
        {"label": "Both",          "value": both_count},
        {"label": "Neither",       "value": neither_count},
    ]
    social_media = [item for item in social_media if item["value"] > 0]

    # Top cities outside India ("City (Country)")
    city_outside_rows = _safe_rows(
        f"""SELECT city, country, COUNT(*) AS n FROM {pii}
            WHERE city IS NOT NULL AND city != ''
              AND country IS NOT NULL AND country != ''
              AND LOWER(TRIM(country)) != 'india'{date_frag}
            GROUP BY city, country ORDER BY n DESC""",
        date_params,
    )
    _out = defaultdict(int)
    for city, raw_cty, cnt in city_outside_rows:
        cty = normalize_country(raw_cty) or (raw_cty or "")
        _out[(city, cty)] += int(cnt or 0)
    top_cities_outside_india = [
        {"label": f"{k[0]} ({k[1]})", "value": v}
        for k, v in sorted(_out.items(), key=lambda x: -x[1])[:10]
    ]

    # Top organizations (professionals / startups / freelancers, merged)
    from server.utils.org_normalize import merge_org_counts
    org_rows = _safe_rows(
        f"""SELECT organization_name, COUNT(*) AS n FROM {pii}
            WHERE organization_name IS NOT NULL AND organization_name != ''
              AND (LOWER(occupation) LIKE '%professional%'
                   OR LOWER(occupation) LIKE '%startup%'
                   OR LOWER(occupation) LIKE '%freelance%'){date_frag}
            GROUP BY organization_name ORDER BY n DESC""",
        date_params,
    )
    top_organizations = merge_org_counts([(r[0], int(r[1])) for r in org_rows])[:20]

    # India state-wise (for heatmap)
    india_state_rows = _safe_rows(
        f"""SELECT state, COUNT(*) AS n FROM {pii}
            WHERE LOWER(TRIM(country)) = 'india'
              AND state IS NOT NULL AND state != ''{date_frag}
            GROUP BY state ORDER BY n DESC""",
        date_params,
    )
    india_state_registrations = [
        {"state": lbl, "value": val}
        for lbl, val in merge_state_count_rows([(r[0], int(r[1])) for r in india_state_rows])
    ]

    # APAC country-wise (for map) – outside India
    apac_lc = tuple(c.lower() for c in APAC_FOR_MAP_EXCL_INDIA)
    apac_ph = ",".join(f":apac{i}" for i in range(len(apac_lc)))
    apac_params = {f"apac{i}": v for i, v in enumerate(apac_lc)}
    apac_params.update(date_params)
    apac_country_rows = _safe_rows(
        f"""SELECT country, COUNT(*) AS n FROM {pii}
            WHERE country IS NOT NULL AND country != ''
              AND LOWER(TRIM(country)) != 'india'
              AND LOWER(TRIM(country)) IN ({apac_ph}){date_frag}
            GROUP BY country ORDER BY n DESC""",
        apac_params,
    )
    apac_country_registrations = [
        {"country": lbl, "value": val}
        for lbl, val in merge_country_count_rows([(r[0], int(r[1])) for r in apac_country_rows])
    ]

    # Registration trends (daily, complete series with zero-fill)
    trend_rows = _safe_rows(
        f"""SELECT DATE_TRUNC('day', registered_at)::date AS d, COUNT(*) AS n
            FROM {pii} WHERE registered_at IS NOT NULL GROUP BY d ORDER BY d""",
        {},
    )
    now = datetime.now()
    if "cutoff" in date_params:
        _co = date_params["cutoff"]
        start_date = _co.date() if hasattr(_co, "date") else datetime.fromisoformat(str(_co)).date()
    else:
        start_date = date(now.year, 1, 15)
        if start_date > date.today():
            start_date = date(now.year - 1, 1, 15)
    date_dict = {}
    for r in trend_rows:
        dk = r[0] if isinstance(r[0], type(date.today())) else (r[0].date() if hasattr(r[0], "date") else r[0])
        date_dict[dk] = int(r[1])
    reg_trends = []
    cur = start_date
    today_d = date.today()
    while cur <= today_d:
        reg_trends.append({"label": cur.strftime("%b %d"), "value": date_dict.get(cur, 0), "date": cur.isoformat()})
        cur += timedelta(days=1)

    summary = {
        "total_users": total_users,
        "unique_organizations": _safe_scalar(
            f"SELECT COUNT(DISTINCT organization_name) FROM {pii} WHERE organization_name IS NOT NULL AND organization_name != ''{date_frag}",
            date_params,
        ),
        "unique_countries": _safe_scalar(
            f"SELECT COUNT(DISTINCT country) FROM {pii} WHERE country IS NOT NULL AND country != ''{date_frag}",
            date_params,
        ),
        "top_domain":       (top_domains[0]["label"] if top_domains else "N/A"),
        "top_city":         (top_cities[0]["label"]  if top_cities  else "N/A"),
        "top_organization": top_organization,
        "users_with_github": _safe_scalar(
            f"SELECT COUNT(*) FROM {pii} WHERE github_url IS NOT NULL AND github_url != ''{date_frag}", date_params
        ),
        "users_with_linkedin": _safe_scalar(
            f"SELECT COUNT(*) FROM {pii} WHERE linkedin_url IS NOT NULL AND linkedin_url != ''{date_frag}", date_params
        ),
        "average_age": average_age,
        "apac_except_india_users": apac_excl_india,
        "top_india_state":       top_india_state or "N/A",
        "top_india_city":        top_india_city  or "N/A",
        "top_india_state_count": top_india_state_count,
        "top_india_city_count":  top_india_city_count,
        "top_india_location_count": top_india_city_count or top_india_state_count,
        "top_apac_country":       top_apac_country or "N/A",
        "top_apac_country_count": top_apac_country_count,
        "sea_registrations":           sea_registrations,      "sea_top_country":           sea_top_country    or "N/A",
        "anz_registrations":           anz_registrations,      "anz_top_country":           anz_top_country    or "N/A",
        "greater_china_registrations": gc_registrations,       "greater_china_top_country": gc_top_country     or "N/A",
        "korea_registrations":         korea_registrations,    "korea_top_country":         korea_top_country  or "N/A",
        "india_registrations": india_count,
        "book_of_business_registrations": bob_count,
        "total_skillboost_profiles":    total_sb,
        "verified_skillboost_profiles": verified_sb,
        "skillboost_verification_rate": sb_rate,
        "skillboost_credits_allocated": _safe_scalar(
            f"SELECT COUNT(*) FROM {sb} WHERE valid = TRUE AND credit_link_id IS NOT NULL"
        ),
        "skillboost_credits_not_sent": _safe_scalar(
            f"SELECT COUNT(*) FROM {sb} WHERE valid = TRUE AND credit_link_id IS NOT NULL AND email_sent_at IS NULL"
        ),
        "skillboost_credits_sent": _safe_scalar(
            f"SELECT COUNT(*) FROM {sb} WHERE valid = TRUE AND credit_link_id IS NOT NULL AND email_sent_at IS NOT NULL"
        ),
        "total_skilllab_submissions":          total_sl,
        "verified_skilllab_submissions":       verified_sl,
        "skilllab_submission_verification_rate": sl_rate,
        "total_codelab_submissions":           total_cl,
        "verified_codelab_submissions":        verified_cl,
        "codelab_submission_verification_rate": cl_rate,
        "total_project_submissions":           total_proj,
        "verified_project_submissions":        verified_proj,
        "project_submission_verification_rate": proj_rate,
        "project_submission_program_target": 15000,
        "project_submission_track_target":   5000,
        "project_submission_by_track": proj_by_track,
        "optional_mcq_by_track":  opt_mcq_by_track,
        "main_mcq_by_track":      main_mcq_by_track,
        "optional_mcq_top5_winners": [],
        "previous_period_total_users":   None,
        "previous_period_apac_users":    None,
        "previous_period_average_age":   None,
        "users_in_cohort1_and_cohort2": users_in_cohort1_and_cohort2,
        "net_new_registrations": (
            max(0, int(total_users or 0) - int(users_in_cohort1_and_cohort2 or 0))
            if prefix == "cohort_2_"
            else None
        ),
    }

    charts = {
        "gender_distribution":            gender_dist,
        "registration_source_bifurcation": reg_src,
        "top_domains":                    top_domains,
        "user_segmentation":              {"industries": industry_list},
        "top_cities":                     top_cities,
        "top_cities_outside_india":       top_cities_outside_india,
        "top_states":                     top_states,
        "country_distribution":           country_dist,
        "top_organizations":              top_organizations,
        "class_stream_distribution":      class_stream_dist,
        "designation_distribution":       designation_dist,
        "persona_distribution":           persona_dist,
        "occupation_distribution":        occ_dist,
        "age_groups":                     age_groups,
        "registration_trends":            reg_trends,
        "social_media":                   social_media,
        "india_state_registrations":      india_state_registrations,
        "apac_country_registrations":     apac_country_registrations,
    }

    return {"summary": summary, "charts": charts}


@bp.route('/data', methods=['GET'])
@require_page_access('dashboard')
def get_dashboard_data():
    """Combined dashboard summary + charts (single request, cached)."""
    try:
        period = request.args.get('period', 'all')
        prefix = getattr(g, 'table_prefix', '')
        if prefix:
            result = _fetch_prefixed_dashboard(prefix, period)
            return jsonify(result), 200
        result = _get_dashboard_data_cached(period, getattr(g, 'table_prefix', ''))
        return jsonify(result), 200
    except Exception:
        return jsonify({
            'summary': {
                'total_users': 0, 'apac_except_india_users': 0, 'top_india_state': 'N/A',
                'top_india_city': 'N/A', 'top_india_state_count': None, 'top_india_city_count': None, 'top_india_location_count': None, 'top_apac_country': 'N/A',
                'top_apac_country_count': None,
                'sea_registrations': 0, 'sea_top_country': 'N/A',
                'anz_registrations': 0, 'anz_top_country': 'N/A',
                'greater_china_registrations': 0, 'greater_china_top_country': 'N/A',
                'korea_registrations': 0, 'korea_top_country': 'N/A',
                'india_registrations': 0
            },
            'charts': {
                'registration_trends': [], 'gender_distribution': [],
                'registration_source_bifurcation': [{'label': 'Google', 'value': 0}, {'label': 'Outreach', 'value': 0}, {'label': 'Marketing', 'value': 0}, {'label': 'Ads', 'value': 0}, {'label': 'Hack2skill', 'value': 0}, {'label': 'Other', 'value': 0}],
                'occupation_distribution': [], 'persona_distribution': [], 'top_domains': [], 'user_segmentation': {'industries': []}, 'top_cities': [], 'top_cities_outside_india': [], 'top_organizations': [],
                'india_state_registrations': [], 'apac_country_registrations': []
            }
        }), 200


def _dashboard_ai_insights_compute(period: str, table_prefix: str, cohort_id: int | None) -> dict:
    """
    Load dashboard summary+charts, call Gemini, return a JSON-serializable dict.
    Successful responses are cached at the route layer (see _get_cached_ai_insights_success).
    """
    global _ai_insights_rate_limit_until

    api_key = (os.getenv("GEMINI_API_KEY") or "").strip() or Config.GEMINI_API_KEY
    if not api_key:
        return {
            "insights": [],
            "source": "disabled",
            "message": "GEMINI_API_KEY is not set; configure AI Studio key in environment.",
        }

    if _ai_insights_rate_limit_until and datetime.now() < _ai_insights_rate_limit_until:
        seconds = int((_ai_insights_rate_limit_until - datetime.now()).total_seconds())
        return {
            "insights": [],
            "source": "rate_limited",
            "message": f"Gemini quota exhausted; try again in ~{seconds}s.",
            "retry_after_seconds": max(seconds, 1),
        }

    if table_prefix:
        blob = _fetch_prefixed_dashboard(table_prefix, period)
    else:
        blob = _get_dashboard_data_cached(period, table_prefix)
    summary = blob.get("summary") or {}
    charts = blob.get("charts") or {}
    ctx = build_insights_context(summary, charts, period, cohort_id)
    model = (os.getenv("GEMINI_DASHBOARD_MODEL") or "").strip() or Config.GEMINI_DASHBOARD_MODEL
    # Release DB pool connection before slow external Gemini call (retries used to block /data).
    try:
        db.session.remove()
    except Exception:
        pass
    try:
        insights = generate_dashboard_insights(api_key, model, ctx)
        logger.info(
            "Dashboard AI insights: %d strings (period=%s cohort=%s prefix=%r)",
            len(insights),
            period,
            cohort_id,
            table_prefix,
        )
        return {"insights": insights, "source": "gemini", "message": None}
    except Exception as e:
        msg = str(e)
        if _is_rate_limit_message(msg):
            _ai_insights_rate_limit_until = datetime.now() + timedelta(
                seconds=_AI_INSIGHTS_RATE_LIMIT_COOLDOWN_SEC
            )
            logger.warning(
                "Dashboard AI insights rate-limited; cooling off for %ss",
                _AI_INSIGHTS_RATE_LIMIT_COOLDOWN_SEC,
            )
            return {
                "insights": [],
                "source": "rate_limited",
                "message": f"Gemini quota exhausted; try again in ~{_AI_INSIGHTS_RATE_LIMIT_COOLDOWN_SEC}s.",
                "retry_after_seconds": _AI_INSIGHTS_RATE_LIMIT_COOLDOWN_SEC,
            }
        logger.warning("Dashboard AI insights failed: %s", e)
        return {"insights": [], "source": "error", "message": msg[:500]}


def _ai_insights_cache_key(period: str, table_prefix: str, cohort_id: int | None) -> tuple:
    return (period or "all", table_prefix or "", cohort_id)


def _get_cached_ai_insights_entry(period: str, table_prefix: str, cohort_id: int | None):
    """Return (age_seconds, body) for any stored Gemini success, even if past fresh TTL."""
    key = _ai_insights_cache_key(period, table_prefix, cohort_id)
    entry = _ai_insights_success_store.get(key)
    if not entry:
        return None
    ts, body = entry
    if not (body.get("source") == "gemini" and body.get("insights")):
        _ai_insights_success_store.pop(key, None)
        return None
    age = (datetime.now() - ts).total_seconds()
    if age > _AI_INSIGHTS_STALE_MAX_AGE_SEC:
        _ai_insights_success_store.pop(key, None)
        return None
    return age, body


def _set_cached_ai_insights_success(period: str, table_prefix: str, cohort_id: int | None, body: dict) -> None:
    if body.get("source") == "gemini" and body.get("insights"):
        key = _ai_insights_cache_key(period, table_prefix, cohort_id)
        _ai_insights_success_store[key] = (datetime.now(), body)


def _serve_stale_with_status(body: dict, age: float, cohort_id: int | None, period: str, reason: str, retry_after: int | None = None) -> dict:
    out = dict(body)
    out["source"] = "gemini_stale"
    out["stale_age_seconds"] = int(age)
    out["stale_reason"] = reason
    if retry_after is not None:
        out["retry_after_seconds"] = retry_after
    logger.info(
        "Dashboard AI insights: serving stale (%ss old, reason=%s, period=%s cohort=%s)",
        int(age),
        reason,
        period,
        cohort_id,
    )
    return out


@bp.route('/ai-insights', methods=['GET'])
@require_page_access('dashboard')
def get_dashboard_ai_insights():
    """
    Gemini narrative insights from aggregate dashboard metrics.

    Caching strategy:
      * Fresh cache (default 1h, GEMINI_INSIGHTS_FRESH_TTL_SEC) — return immediately.
      * Stale cache up to 24h (GEMINI_INSIGHTS_STALE_MAX_AGE_SEC) — returned when Gemini is
        rate-limited or fails, so users keep seeing real AI text while quota recovers.
      * refresh=1 bypasses the fresh cache (still falls back to stale on failure).
    """
    try:
        period = request.args.get('period', 'all')
        prefix = getattr(g, 'table_prefix', '')
        cohort_id = getattr(g, 'cohort_id', None)
        refresh_raw = (request.args.get('refresh') or '').strip().lower()
        force_refresh = refresh_raw in ('1', 'true', 'yes')

        if not ((os.getenv("GEMINI_API_KEY") or "").strip() or Config.GEMINI_API_KEY):
            return jsonify(
                {
                    "insights": [],
                    "source": "disabled",
                    "message": "GEMINI_API_KEY is not set; configure AI Studio key in environment.",
                }
            ), 200

        cached = _get_cached_ai_insights_entry(period, prefix, cohort_id)
        if cached is not None and not force_refresh:
            age, body = cached
            if age <= _AI_INSIGHTS_FRESH_TTL_SEC:
                return jsonify(body), 200

        body = _dashboard_ai_insights_compute(period, prefix, cohort_id)

        if body.get("source") == "gemini" and body.get("insights"):
            _set_cached_ai_insights_success(period, prefix, cohort_id, body)
            return jsonify(body), 200

        if cached is not None:
            age, stale_body = cached
            reason = body.get("source") or "error"
            retry_after = body.get("retry_after_seconds")
            return jsonify(
                _serve_stale_with_status(stale_body, age, cohort_id, period, reason, retry_after)
            ), 200

        return jsonify(body), 200
    except Exception as e:
        logger.warning("get_dashboard_ai_insights: %s", e)
        return jsonify({"insights": [], "source": "error", "message": str(e)[:500]}), 200


@bp.route('/summary', methods=['GET'])
@require_page_access('dashboard')
def get_summary():
    """Get dashboard summary statistics. Prefer GET /data for single round-trip + cache."""
    try:
        period = request.args.get('period', 'all')
        prefix = getattr(g, 'table_prefix', '')
        if prefix:
            result = _fetch_prefixed_dashboard(prefix, period)
            return jsonify(result['summary']), 200
        result = _fetch_summary_data(period)
        return jsonify(result), 200
    except Exception:
        return jsonify({
            'total_users': 0, 'unique_organizations': 0, 'top_domain': 'N/A', 'top_city': 'N/A',
            'average_age': None, 'apac_except_india_users': 0, 'top_india_state': 'N/A',
            'top_india_city': 'N/A', 'top_apac_country': 'N/A',
            'sea_registrations': 0, 'sea_top_country': 'N/A',
            'anz_registrations': 0, 'anz_top_country': 'N/A',
            'greater_china_registrations': 0, 'greater_china_top_country': 'N/A',
            'korea_registrations': 0, 'korea_top_country': 'N/A',
            'india_registrations': 0
        }), 200


@cache_result(ttl=900)
def _get_region_breakdown_cached(region, period):
    """Cached region breakdown data (15 min)."""
    cutoff_date = _get_period_dates(period)
    date_cond = _date_filter_condition(cutoff_date)
    SEA_COUNTRIES = [
        'Brunei', 'Cambodia', 'Indonesia', 'Laos', 'Malaysia', 'Myanmar',
        'Philippines', 'Singapore', 'Thailand', 'Timor-Leste', 'Vietnam'
    ]
    ANZ_COUNTRIES = ['Australia', 'New Zealand']
    GREATER_CHINA_COUNTRIES = ['China', 'Hong Kong', 'Taiwan', 'Mongolia']
    KOREA_COUNTRIES = ['South Korea', 'North Korea']
    if region == 'india':
        label = 'India'
        q = db.session.query(
            UserPIICombined.state,
            func.count(UserPIICombined.id).label('count')
        ).filter(
            UserPIICombined.country.isnot(None),
            UserPIICombined.country != '',
            country_column_matches_canonical(UserPIICombined.country, 'India'),
            UserPIICombined.state.isnot(None),
            UserPIICombined.state != ''
        )
        if date_cond is not None:
            q = q.filter(date_cond)
        rows = q.group_by(UserPIICombined.state).order_by(desc('count')).all()
        merged_list = merge_state_count_rows([(r[0], r[1]) for r in rows])
        items = [{'name': k, 'count': v} for k, v in merged_list]
    else:
        region_map = {
            'sea': ('SEA (Southeast Asia)', SEA_COUNTRIES),
            'anz': ('ANZ (Australia & New Zealand)', ANZ_COUNTRIES),
            'greater_china': ('Greater China', GREATER_CHINA_COUNTRIES),
            'korea': ('Korea', KOREA_COUNTRIES),
        }
        label, countries = region_map[region]
        reg_cond = country_column_matches_any_canonical(UserPIICombined.country, countries)
        q = db.session.query(
            UserPIICombined.country,
            func.count(UserPIICombined.id).label('count')
        ).filter(
            UserPIICombined.country.isnot(None),
            UserPIICombined.country != '',
            reg_cond,
        )
        if date_cond is not None:
            q = q.filter(date_cond)
        rows = q.group_by(UserPIICombined.country).order_by(desc('count')).all()
        merged = merge_country_count_rows([(r[0], r[1]) for r in rows])
        items = [{'name': k, 'count': v} for k, v in merged]
    total = sum(i['count'] for i in items)
    return {'region': region, 'label': label, 'items': items, 'total': total}


@bp.route('/region-breakdown', methods=['GET'])
@require_page_access('dashboard')
def get_region_breakdown():
    """Get per-country (or per-state for India) registration counts for a region (cached 5 min)."""
    region = (request.args.get('region') or '').strip().lower()
    period = request.args.get('period', 'all')
    if region not in ('sea', 'anz', 'greater_china', 'korea', 'india'):
        return jsonify({'error': 'Invalid region'}), 400
    prefix = getattr(g, 'table_prefix', '')
    if prefix:
        # Raw-SQL path for cohort-prefixed tables
        pii = f"{prefix}user_pii_combined"
        date_frag, date_params = _period_sql_filter(period)
        SEA = ('brunei','cambodia','indonesia','laos','malaysia','myanmar','philippines','singapore','thailand','timor-leste','vietnam')
        ANZ = ('australia','new zealand')
        GC  = ('china','hong kong','taiwan','mongolia')
        KR  = ('south korea','north korea')
        region_map = {'sea': ('SEA (Southeast Asia)', SEA), 'anz': ('ANZ (Australia & New Zealand)', ANZ), 'greater_china': ('Greater China', GC), 'korea': ('Korea', KR)}
        try:
            if region == 'india':
                rows = _safe_rows(
                    f"SELECT state, COUNT(*) AS n FROM {pii} WHERE LOWER(TRIM(country))='india' AND state IS NOT NULL AND state != ''{date_frag} GROUP BY state ORDER BY n DESC",
                    date_params)
                from server.utils.state_normalize import merge_state_count_rows
                merged = merge_state_count_rows([(r[0], int(r[1])) for r in rows])
                items = [{'name': k, 'count': v} for k, v in merged]
                return jsonify({'region': region, 'label': 'India', 'items': items, 'total': sum(i['count'] for i in items)}), 200
            label, countries = region_map[region]
            placeholders = ','.join(f':rc{i}' for i in range(len(countries)))
            rc_params = {f'rc{i}': v for i, v in enumerate(countries)}
            rc_params.update(date_params)
            rows = _safe_rows(
                f"SELECT country, COUNT(*) AS n FROM {pii} WHERE LOWER(TRIM(country)) IN ({placeholders}){date_frag} GROUP BY country ORDER BY n DESC",
                rc_params)
            from server.utils.country_normalize import merge_country_count_rows
            merged = merge_country_count_rows([(r[0], int(r[1])) for r in rows])
            items = [{'name': k, 'count': v} for k, v in merged]
            return jsonify({'region': region, 'label': label, 'items': items, 'total': sum(i['count'] for i in items)}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    try:
        data = _get_region_breakdown_cached(region, period)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _get_period_dates(period):
    """Return cutoff_date for the given period.
    For 'all': no filter (entire dataset).
    For 'month': start of current calendar month (1st at 00:00:00).
    For 7d/30d/90d: that many days ago from now.
    """
    cutoff_date = None
    if period == 'all':
        return None
    if period == 'month':
        # Current calendar month: from 1st of this month 00:00:00
        now = datetime.now()
        cutoff_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == '7d':
        cutoff_date = datetime.now() - timedelta(days=7)
    elif period == '30d':
        cutoff_date = datetime.now() - timedelta(days=30)
    elif period == '90d':
        cutoff_date = datetime.now() - timedelta(days=90)
    return cutoff_date


def _date_filter_condition(cutoff_date):
    """Return SQLAlchemy filter for registered_at or created_at >= cutoff_date."""
    if not cutoff_date:
        return None
    return or_(
        and_(UserPIICombined.registered_at.isnot(None), UserPIICombined.registered_at >= cutoff_date),
        and_(UserPIICombined.registered_at.is_(None), UserPIICombined.created_at >= cutoff_date)
    )


def _get_previous_period_range(period):
    """Return (prev_start, current_start) for the previous period (for week-on-week / period-on-period).
    Previous period is the same length as current, immediately before it.
    For 'all' there is no previous period.
    """
    if period == 'all':
        return None, None
    now = datetime.now()
    if period == 'month':
        current_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # First day of last month
        if now.month == 1:
            prev_start = now.replace(year=now.year - 1, month=12, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            prev_start = now.replace(month=now.month - 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return prev_start, current_start
    if period == '7d':
        current_start = now - timedelta(days=7)
        prev_start = now - timedelta(days=14)
        return prev_start, current_start
    if period == '30d':
        current_start = now - timedelta(days=30)
        prev_start = now - timedelta(days=60)
        return prev_start, current_start
    if period == '90d':
        current_start = now - timedelta(days=90)
        prev_start = now - timedelta(days=180)
        return prev_start, current_start
    return None, None


def _previous_period_filter(prev_start, current_start):
    """Filter: registered_at (or created_at) >= prev_start AND < current_start."""
    if prev_start is None or current_start is None:
        return None
    return or_(
        and_(
            UserPIICombined.registered_at.isnot(None),
            UserPIICombined.registered_at >= prev_start,
            UserPIICombined.registered_at < current_start
        ),
        and_(
            UserPIICombined.registered_at.is_(None),
            UserPIICombined.created_at >= prev_start,
            UserPIICombined.created_at < current_start
        )
    )


def _fetch_summary_data(period):
    """Internal function to fetch summary data. period: 'all', 'month', '7d', '30d', '90d'."""
    try:
        cutoff_date = _get_period_dates(period)
        date_cond = _date_filter_condition(cutoff_date)
        
        base_query = UserPIICombined.query
        if date_cond is not None:
            base_query = base_query.filter(date_cond)
        
        # Total users
        total_users = base_query.count() or 0
        
        # Unique organizations
        try:
            org_query = db.session.query(func.count(func.distinct(UserPIICombined.organization_name)))
            if date_cond is not None:
                org_query = org_query.filter(date_cond)
            unique_orgs = org_query.scalar() or 0
        except:
            unique_orgs = 0
        
        # Top domain
        top_domain = None
        try:
            domain_query = db.session.query(
                UserPIICombined.domain,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.domain.isnot(None),
                UserPIICombined.domain != ''
            )
            if date_cond is not None:
                domain_query = domain_query.filter(date_cond)
            top_domain_result = domain_query.group_by(
                UserPIICombined.domain
            ).order_by(desc('count')).first()
            
            top_domain = top_domain_result[0] if top_domain_result else None
        except:
            top_domain = None
        
        # Top city
        top_city = None
        try:
            city_query = db.session.query(
                UserPIICombined.city,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.city.isnot(None),
                UserPIICombined.city != ''
            )
            if date_cond is not None:
                city_query = city_query.filter(date_cond)
            top_city_result = city_query.group_by(
                UserPIICombined.city
            ).order_by(desc('count')).first()
            
            top_city = top_city_result[0] if top_city_result else None
        except:
            top_city = None
        
        # Additional stats
        # Total countries
        try:
            unique_countries = db.session.query(func.count(func.distinct(UserPIICombined.country))).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != ''
            ).scalar() or 0
        except:
            unique_countries = 0
        
        # Users with GitHub
        try:
            github_query = UserPIICombined.query.filter(
                UserPIICombined.github_url.isnot(None),
                UserPIICombined.github_url != ''
            )
            if date_cond is not None:
                github_query = github_query.filter(date_cond)
            users_with_github = github_query.count() or 0
        except:
            users_with_github = 0
        
        # Users with LinkedIn
        try:
            linkedin_query = UserPIICombined.query.filter(
                UserPIICombined.linkedin_url.isnot(None),
                UserPIICombined.linkedin_url != ''
            )
            if date_cond is not None:
                linkedin_query = linkedin_query.filter(date_cond)
            users_with_linkedin = linkedin_query.count() or 0
        except:
            users_with_linkedin = 0
        
        # Book of Business registrations (bob_match = True)
        try:
            bob_query = UserPIICombined.query.filter(UserPIICombined.bob_match == True)
            if date_cond is not None:
                bob_query = bob_query.filter(date_cond)
            book_of_business_registrations = bob_query.count() or 0
        except Exception:
            book_of_business_registrations = 0

        # Skill Lab / Skillboost profiles: total, verified, verification rate (all rows in skillboost_profile)
        total_skillboost_profiles = 0
        verified_skillboost_profiles = 0
        skillboost_verification_rate = None
        # Skill Lab credits: allocated, not sent, sent (verified + credit_link_id set)
        skillboost_credits_allocated = 0
        skillboost_credits_not_sent = 0
        skillboost_credits_sent = 0
        try:
            total_skillboost_profiles = SkillboostProfile.query.count() or 0
            verified_skillboost_profiles = SkillboostProfile.query.filter(SkillboostProfile.valid == True).count() or 0
            if total_skillboost_profiles > 0:
                skillboost_verification_rate = round(100.0 * verified_skillboost_profiles / total_skillboost_profiles, 1)
            skillboost_credits_allocated = SkillboostProfile.query.filter(
                SkillboostProfile.valid == True,
                SkillboostProfile.credit_link_id.isnot(None)
            ).count() or 0
            skillboost_credits_not_sent = SkillboostProfile.query.filter(
                SkillboostProfile.valid == True,
                SkillboostProfile.credit_link_id.isnot(None),
                SkillboostProfile.email_sent_at.is_(None)
            ).count() or 0
            skillboost_credits_sent = SkillboostProfile.query.filter(
                SkillboostProfile.valid == True,
                SkillboostProfile.credit_link_id.isnot(None),
                SkillboostProfile.email_sent_at.isnot(None)
            ).count() or 0
        except Exception:
            pass

        # Skill Lab Submission Verification stats
        total_skilllab_submissions = 0
        verified_skilllab_submissions = 0
        skilllab_submission_verification_rate = None
        try:
            total_skilllab_submissions = SkillLabSubmission.query.count() or 0
            verified_skilllab_submissions = SkillLabSubmission.query.filter(SkillLabSubmission.valid == True).count() or 0
            if total_skilllab_submissions > 0:
                skilllab_submission_verification_rate = round(100.0 * verified_skilllab_submissions / total_skilllab_submissions, 1)
        except Exception:
            pass

        # Code Lab Submission Verification stats
        total_codelab_submissions = 0
        verified_codelab_submissions = 0
        codelab_submission_verification_rate = None
        try:
            total_codelab_submissions = CodeLabSubmission.query.count() or 0
            verified_codelab_submissions = CodeLabSubmission.query.filter(CodeLabSubmission.valid == True).count() or 0
            if total_codelab_submissions > 0:
                codelab_submission_verification_rate = round(100.0 * verified_codelab_submissions / total_codelab_submissions, 1)
        except Exception:
            pass

        # Project Submission Verification stats (program target 15k = 5k per track)
        total_project_submissions = 0
        verified_project_submissions = 0
        project_submission_verification_rate = None
        project_submission_program_target = 15000
        project_submission_track_target = 5000
        project_submission_by_track = [
            {'track': 1, 'total': 0, 'verified': 0},
            {'track': 2, 'total': 0, 'verified': 0},
            {'track': 3, 'total': 0, 'verified': 0},
        ]
        try:
            total_project_submissions = ProjectSubmission.query.count() or 0
            verified_project_submissions = ProjectSubmission.query.filter(ProjectSubmission.valid == True).count() or 0
            if total_project_submissions > 0:
                project_submission_verification_rate = round(100.0 * verified_project_submissions / total_project_submissions, 1)
            for i, t in enumerate((1, 2, 3)):
                tot_t = ProjectSubmission.query.filter(ProjectSubmission.track_number == t).count() or 0
                ver_t = ProjectSubmission.query.filter(
                    ProjectSubmission.track_number == t,
                    ProjectSubmission.valid == True,
                ).count() or 0
                project_submission_by_track[i] = {'track': t, 'total': tot_t, 'verified': ver_t}
        except Exception:
            pass
        
        # Top organization
        top_org = None
        try:
            org_query = db.session.query(
                UserPIICombined.organization_name,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.organization_name.isnot(None),
                UserPIICombined.organization_name != ''
            )
            if date_cond is not None:
                org_query = org_query.filter(date_cond)
            top_org_result = org_query.group_by(
                UserPIICombined.organization_name
            ).order_by(desc('count')).first()
            
            top_org = top_org_result[0] if top_org_result else None
        except:
            top_org = None
        
        # Average age (from date_of_birth) - Optimized using SQL
        avg_age = None
        try:
            today = datetime.now().date()
            
            # Use SQL to calculate age instead of loading all records
            # PostgreSQL AGE function returns interval, extract year
            age_query = db.session.query(
                func.avg(
                    func.extract('year', func.age(today, UserPIICombined.date_of_birth))
                )
            ).filter(
                UserPIICombined.date_of_birth.isnot(None)
            )
            if date_cond is not None:
                age_query = age_query.filter(date_cond)
            
            avg_age_result = age_query.scalar()
            if avg_age_result:
                avg_age = int(avg_age_result)
        except Exception as e:
            # Fallback to Python calculation if SQL fails
            try:
                today = datetime.now().date()
                dob_query = UserPIICombined.query.filter(
                    UserPIICombined.date_of_birth.isnot(None)
                )
                if date_cond is not None:
                    dob_query = dob_query.filter(date_cond)
                # Limit to 10000 records for fallback
                users_with_dob = dob_query.limit(10000).all()
                
                if users_with_dob:
                    ages = []
                    for user in users_with_dob:
                        if user.date_of_birth:
                            age = today.year - user.date_of_birth.year - (
                                (today.month, today.day) < (user.date_of_birth.month, user.date_of_birth.day)
                            )
                            ages.append(age)
                    
                    if ages:
                        avg_age = int(sum(ages) / len(ages))
            except:
                avg_age = None
        
        APAC_COUNTRIES = APAC_COUNTRIES_CANONICAL
        # SEA (Southeast Asia)
        SEA_COUNTRIES = [
            'Brunei', 'Cambodia', 'Indonesia', 'Laos', 'Malaysia', 'Myanmar',
            'Philippines', 'Singapore', 'Thailand', 'Timor-Leste', 'Vietnam'
        ]
        # ANZ (Australia & New Zealand)
        ANZ_COUNTRIES = ['Australia', 'New Zealand']
        # Greater China
        GREATER_CHINA_COUNTRIES = [
            'China', 'Hong Kong', 'Taiwan', 'Mongolia'
        ]
        # Korea
        KOREA_COUNTRIES = ['South Korea', 'North Korea']
        # East Asia (union, kept for APAC totals)
        EAST_ASIA_COUNTRIES = GREATER_CHINA_COUNTRIES + KOREA_COUNTRIES + ['Japan']
        
        # Users from APAC except India
        apac_except_india_count = 0
        try:
            apac_region_cond = country_column_matches_any_canonical(
                UserPIICombined.country, APAC_COUNTRIES
            )
            apac_query = base_query.filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                ~country_column_matches_canonical(UserPIICombined.country, 'India'),
                apac_region_cond,
            )
            apac_except_india_count = apac_query.count() or 0
        except Exception as e:
            print(f"Error calculating APAC users: {e}")
            import traceback
            traceback.print_exc()
            apac_except_india_count = 0
        
        # Top state and city from India (with counts)
        top_india_state = None
        top_india_city = None
        top_india_state_count = None
        top_india_city_count = None
        try:
            india_state_query = db.session.query(
                UserPIICombined.state,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                country_column_matches_canonical(UserPIICombined.country, 'India'),
                UserPIICombined.state.isnot(None),
                UserPIICombined.state != ''
            )
            if date_cond is not None:
                india_state_query = india_state_query.filter(date_cond)
            india_state_rows = india_state_query.group_by(
                UserPIICombined.state
            ).order_by(desc('count')).all()
            merged_ist = merge_state_count_rows([(r[0], r[1]) for r in india_state_rows])
            if merged_ist:
                top_india_state = merged_ist[0][0]
                top_india_state_count = merged_ist[0][1]
            
            india_city_query = db.session.query(
                UserPIICombined.city,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                country_column_matches_canonical(UserPIICombined.country, 'India'),
                UserPIICombined.city.isnot(None),
                UserPIICombined.city != ''
            )
            if date_cond is not None:
                india_city_query = india_city_query.filter(date_cond)
            top_india_city_result = india_city_query.group_by(
                UserPIICombined.city
            ).order_by(desc('count')).first()
            if top_india_city_result:
                top_india_city = top_india_city_result[0]
                top_india_city_count = top_india_city_result[1]
        except Exception as e:
            print(f"Error calculating India stats: {e}")
            top_india_state = None
            top_india_city = None
            top_india_state_count = None
            top_india_city_count = None
        
        # Top country from APAC except India (with count)
        top_apac_country = None
        top_apac_country_count = None
        try:
            apac_region_cond = country_column_matches_any_canonical(
                UserPIICombined.country, APAC_COUNTRIES
            )
            apac_country_query = db.session.query(
                UserPIICombined.country,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                ~country_column_matches_canonical(UserPIICombined.country, 'India'),
                apac_region_cond,
            )
            if date_cond is not None:
                apac_country_query = apac_country_query.filter(date_cond)
            apac_rows = apac_country_query.group_by(UserPIICombined.country).all()
            merged_top = merge_country_count_rows([(r[0], r[1]) for r in apac_rows])
            merged_top = [(c, n) for c, n in merged_top if c != 'India']
            if merged_top:
                top_apac_country = merged_top[0][0]
                top_apac_country_count = merged_top[0][1]
        except Exception as e:
            print(f"Error calculating top APAC country: {e}")
            import traceback
            traceback.print_exc()
            top_apac_country = None
            top_apac_country_count = None

        # SEA, ANZ, Greater China, Korea: per-region count and top country
        sea_registrations = 0
        sea_top_country = None
        anz_registrations = 0
        anz_top_country = None
        greater_china_registrations = 0
        greater_china_top_country = None
        korea_registrations = 0
        korea_top_country = None
        try:
            for region_name, countries in [
                ('sea', SEA_COUNTRIES),
                ('anz', ANZ_COUNTRIES),
                ('greater_china', GREATER_CHINA_COUNTRIES),
                ('korea', KOREA_COUNTRIES)
            ]:
                reg_match = country_column_matches_any_canonical(UserPIICombined.country, countries)
                region_query = base_query.filter(
                    UserPIICombined.country.isnot(None),
                    UserPIICombined.country != '',
                    reg_match,
                )
                count = region_query.count() or 0
                top_q = db.session.query(
                    UserPIICombined.country,
                    func.count(UserPIICombined.id).label('count')
                ).filter(
                    UserPIICombined.country.isnot(None),
                    UserPIICombined.country != '',
                    reg_match,
                )
                if date_cond is not None:
                    top_q = top_q.filter(date_cond)
                top_rows = top_q.group_by(UserPIICombined.country).all()
                merged_reg = merge_country_count_rows([(r[0], r[1]) for r in top_rows])
                top_country = merged_reg[0][0] if merged_reg else None
                if region_name == 'sea':
                    sea_registrations = count
                    sea_top_country = top_country
                elif region_name == 'anz':
                    anz_registrations = count
                    anz_top_country = top_country
                elif region_name == 'greater_china':
                    greater_china_registrations = count
                    greater_china_top_country = top_country
                else:
                    korea_registrations = count
                    korea_top_country = top_country
        except Exception as e:
            print(f"Error calculating region stats: {e}")

        # India: count and top state (same period filter)
        india_registrations = 0
        try:
            india_query = base_query.filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                country_column_matches_canonical(UserPIICombined.country, 'India'),
            )
            india_registrations = india_query.count() or 0
        except Exception as e:
            print(f"Error calculating India stats: {e}")

        # Previous period metrics for week-on-week / period-on-period
        prev_total_users = None
        prev_apac_users = None
        prev_avg_age = None
        prev_start, current_start = _get_previous_period_range(period)
        prev_cond = _previous_period_filter(prev_start, current_start) if prev_start and current_start else None
        if prev_cond is not None:
            try:
                prev_total_users = UserPIICombined.query.filter(prev_cond).count() or 0
            except Exception:
                prev_total_users = 0
            try:
                prev_apac_q = UserPIICombined.query.filter(
                    prev_cond,
                    UserPIICombined.country.isnot(None),
                    UserPIICombined.country != '',
                    ~country_column_matches_canonical(UserPIICombined.country, 'India'),
                    country_column_matches_any_canonical(UserPIICombined.country, APAC_COUNTRIES),
                )
                prev_apac_users = prev_apac_q.count() or 0
            except Exception:
                prev_apac_users = 0
            try:
                today = datetime.now().date()
                prev_age_q = db.session.query(
                    func.avg(func.extract('year', func.age(today, UserPIICombined.date_of_birth)))
                ).filter(UserPIICombined.date_of_birth.isnot(None)).filter(prev_cond)
                prev_avg_result = prev_age_q.scalar()
                prev_avg_age = int(prev_avg_result) if prev_avg_result else None
            except Exception:
                prev_avg_age = None

        # Optional MCQ completion by track (total submissions, passed 6+ per track)
        optional_mcq_by_track = []
        try:
            for track_num in (1, 2, 3):
                rows = OptionalMcqResponse.query.filter(OptionalMcqResponse.track_number == track_num).all()
                total = len(rows)
                passed_6 = 0
                for r in rows:
                    auto = get_response_score(r)
                    if auto.get('correct_count', 0) >= 6:
                        passed_6 += 1
                optional_mcq_by_track.append({'track': track_num, 'total': total, 'passed_6': passed_6})
        except Exception:
            optional_mcq_by_track = [{'track': t, 'total': 0, 'passed_6': 0} for t in (1, 2, 3)]

        # Main MCQ (MCQ Verification) by track: total and passed (score >= 6)
        main_mcq_by_track = []
        try:
            for track_num in (1, 2, 3):
                total = MainMcqResponse.query.filter(MainMcqResponse.track_number == track_num).count()
                passed_6 = MainMcqResponse.query.filter(
                    MainMcqResponse.track_number == track_num,
                    MainMcqResponse.score >= 6
                ).count()
                main_mcq_by_track.append({'track': track_num, 'total': total, 'passed_6': passed_6})
        except Exception:
            main_mcq_by_track = [{'track': t, 'total': 0, 'passed_6': 0} for t in (1, 2, 3)]

        # Top 5 winners: 10/10 on all 3 tracks, ordered by completion time (max created_at) ascending
        optional_mcq_top5_winners = []
        try:
            from collections import defaultdict
            by_email = defaultdict(list)
            for r in OptionalMcqResponse.query.all():
                by_email[r.email].append(r)
            winners = []
            for email, rows in by_email.items():
                if len(rows) != 3:
                    continue
                by_track = {r.track_number: r for r in rows}
                if set(by_track.keys()) != {1, 2, 3}:
                    continue
                all_10 = True
                completion_at = None
                for t in (1, 2, 3):
                    r = by_track[t]
                    auto = get_response_score(r)
                    if auto.get('correct_count', 0) != 10:
                        all_10 = False
                        break
                    if r.created_at:
                        completion_at = r.created_at if completion_at is None else max(completion_at, r.created_at)
                if all_10 and completion_at is not None:
                    leader_name = getattr(by_track.get(1), 'leader_name', None) or getattr(rows[0], 'leader_name', None) if rows else None
                    winners.append({'email': email, 'completed_at': completion_at, 'leader_name': leader_name})
            winners.sort(key=lambda x: x['completed_at'])
            for w in winners[:5]:
                pii = UserPIICombined.query.filter_by(email=w['email']).first()
                name = (pii.name if pii and pii.name else w.get('leader_name')) or w['email']
                optional_mcq_top5_winners.append({
                    'name': name,
                    'email': w['email'],
                    'completed_at': w['completed_at'].isoformat() if hasattr(w['completed_at'], 'isoformat') else str(w['completed_at']),
                })
        except Exception:
            optional_mcq_top5_winners = []
        
        return {
            'total_users': total_users,
            'unique_organizations': unique_orgs,
            'unique_countries': unique_countries,
            'top_domain': top_domain or 'N/A',
            'top_city': top_city or 'N/A',
            'top_organization': top_org or 'N/A',
            'users_with_github': users_with_github,
            'users_with_linkedin': users_with_linkedin,
            'average_age': avg_age,
            'apac_except_india_users': apac_except_india_count,
            'top_india_state': top_india_state or 'N/A',
            'top_india_city': top_india_city or 'N/A',
            'top_india_state_count': top_india_state_count,
            'top_india_city_count': top_india_city_count,
            'top_india_location_count': top_india_city_count if top_india_city_count is not None else top_india_state_count,
            'top_apac_country': top_apac_country or 'N/A',
            'top_apac_country_count': top_apac_country_count,
            'sea_registrations': sea_registrations,
            'sea_top_country': sea_top_country or 'N/A',
            'anz_registrations': anz_registrations,
            'anz_top_country': anz_top_country or 'N/A',
            'greater_china_registrations': greater_china_registrations,
            'greater_china_top_country': greater_china_top_country or 'N/A',
            'korea_registrations': korea_registrations,
            'korea_top_country': korea_top_country or 'N/A',
            'india_registrations': india_registrations,
            'book_of_business_registrations': book_of_business_registrations,
            'total_skillboost_profiles': total_skillboost_profiles,
            'verified_skillboost_profiles': verified_skillboost_profiles,
            'skillboost_verification_rate': skillboost_verification_rate,
            'skillboost_credits_allocated': skillboost_credits_allocated,
            'skillboost_credits_not_sent': skillboost_credits_not_sent,
            'skillboost_credits_sent': skillboost_credits_sent,
            'total_skilllab_submissions': total_skilllab_submissions,
            'verified_skilllab_submissions': verified_skilllab_submissions,
            'skilllab_submission_verification_rate': skilllab_submission_verification_rate,
            'total_codelab_submissions': total_codelab_submissions,
            'verified_codelab_submissions': verified_codelab_submissions,
            'codelab_submission_verification_rate': codelab_submission_verification_rate,
            'total_project_submissions': total_project_submissions,
            'verified_project_submissions': verified_project_submissions,
            'project_submission_verification_rate': project_submission_verification_rate,
            'project_submission_program_target': project_submission_program_target,
            'project_submission_track_target': project_submission_track_target,
            'project_submission_by_track': project_submission_by_track,
            'optional_mcq_by_track': optional_mcq_by_track,
            'main_mcq_by_track': main_mcq_by_track,
            'previous_period_total_users': prev_total_users,
            'previous_period_apac_users': prev_apac_users,
            'previous_period_average_age': prev_avg_age
        }
    except Exception as e:
        # Return empty data instead of error
        return {
            'total_users': 0,
            'unique_organizations': 0,
            'top_domain': 'N/A',
            'top_city': 'N/A',
            'average_age': None,
            'apac_except_india_users': 0,
            'top_india_state': 'N/A',
            'top_india_city': 'N/A',
            'top_india_state_count': None,
            'top_india_city_count': None,
            'top_india_location_count': None,
            'top_apac_country': 'N/A',
            'top_apac_country_count': None,
            'sea_registrations': 0,
            'sea_top_country': 'N/A',
            'anz_registrations': 0,
            'anz_top_country': 'N/A',
            'greater_china_registrations': 0,
            'greater_china_top_country': 'N/A',
            'korea_registrations': 0,
            'korea_top_country': 'N/A',
            'india_registrations': 0,
            'book_of_business_registrations': 0,
            'total_skillboost_profiles': 0,
            'verified_skillboost_profiles': 0,
            'skillboost_verification_rate': None,
            'skillboost_credits_allocated': 0,
            'skillboost_credits_not_sent': 0,
            'skillboost_credits_sent': 0,
            'total_skilllab_submissions': 0,
            'verified_skilllab_submissions': 0,
            'skilllab_submission_verification_rate': None,
            'total_codelab_submissions': 0,
            'verified_codelab_submissions': 0,
            'codelab_submission_verification_rate': None,
            'total_project_submissions': 0,
            'verified_project_submissions': 0,
            'project_submission_verification_rate': None,
            'project_submission_program_target': 15000,
            'project_submission_track_target': 5000,
            'project_submission_by_track': [
                {'track': 1, 'total': 0, 'verified': 0},
                {'track': 2, 'total': 0, 'verified': 0},
                {'track': 3, 'total': 0, 'verified': 0},
            ],
            'optional_mcq_by_track': [{'track': t, 'total': 0, 'passed_6': 0} for t in (1, 2, 3)],
            'main_mcq_by_track': [{'track': t, 'total': 0, 'passed_6': 0} for t in (1, 2, 3)],
            'optional_mcq_top5_winners': [],
            'previous_period_total_users': None,
            'previous_period_apac_users': None,
            'previous_period_average_age': None
        }


@bp.route('/widget-stats', methods=['GET'])
@require_page_access('dashboard')
def get_widget_stats():
    """Get lightweight stats for iOS widget"""
    try:
        prefix = getattr(g, 'table_prefix', '')
        today = datetime.now().date()
        active_cutoff = datetime.now() - timedelta(days=30)
        if prefix:
            pii = f"{prefix}user_pii_combined"
            total_users   = _safe_scalar(f"SELECT COUNT(*) FROM {pii}")
            today_signups = _safe_scalar(f"SELECT COUNT(*) FROM {pii} WHERE registered_at::date = :d", {"d": today})
            active_users  = _safe_scalar(f"SELECT COUNT(*) FROM {pii} WHERE registered_at >= :c", {"c": active_cutoff})
        else:
            today_signups = UserPIICombined.query.filter(func.date(UserPIICombined.registered_at) == today).count() or 0
            total_users   = UserPIICombined.query.count() or 0
            active_users  = UserPIICombined.query.filter(UserPIICombined.registered_at >= active_cutoff).count() or 0
        return jsonify({
            'total_users': total_users,
            'today_signups': today_signups,
            'active_users': active_users,
            'last_updated': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'total_users': 0,
            'today_signups': 0,
            'active_users': 0,
            'last_updated': datetime.utcnow().isoformat()
        }), 200


@bp.route('/charts', methods=['GET'])
@require_page_access('dashboard')
def get_charts():
    """Get chart data for dashboard (cached)"""
    from server.utils.cache import cache_result

    @cache_result(ttl=900)
    def _get_charts(period):
        """Internal function to fetch charts (cached 15 min)"""
        return _fetch_charts_data(period)

    try:
        period = request.args.get('period', 'all')
        prefix = getattr(g, 'table_prefix', '')
        if prefix:
            result = _fetch_prefixed_dashboard(prefix, period)
            return jsonify(result['charts']), 200
        result = _get_charts(period)
        return jsonify(result), 200
    except Exception as e:
        # Return empty data instead of error
        return jsonify({
            'gender_distribution': [],
            'registration_source_bifurcation': [{'label': 'Google', 'value': 0}, {'label': 'Outreach', 'value': 0}, {'label': 'Marketing', 'value': 0}, {'label': 'Ads', 'value': 0}, {'label': 'Hack2skill', 'value': 0}, {'label': 'Other', 'value': 0}],
            'top_domains': [],
            'user_segmentation': {'industries': []},
            'top_cities': [],
            'top_cities_outside_india': [],
            'top_states': [],
            'country_distribution': [],
            'top_organizations': [],
            'class_stream_distribution': [],
            'designation_distribution': [],
            'persona_distribution': [],
            'occupation_distribution': [],
            'age_groups': [],
            'registration_trends': [],
            'social_media': [],
            'india_state_registrations': [],
            'apac_country_registrations': []
        }), 200


def _utm_to_registration_source(utm_medium):
    """Map utm_medium (or combined UTM string) to registration source label for bifurcation chart.
    Rules: google/email -> Google; outreach/community/college/partnership -> Outreach;
    h2s/sendy/h2s social/webengage -> Marketing; ad -> Ads; homepage -> Hack2skill; else -> Other.
    """
    if not utm_medium or not str(utm_medium).strip():
        return 'Other'
    u = str(utm_medium).strip().lower()
    if 'google' in u or 'email' in u:
        return 'Google'
    if any(x in u for x in ('outreach', 'community', 'college', 'partnership')):
        return 'Outreach'
    if 'h2s social' in u or 'h2s' in u or 'sendy' in u or 'webengage' in u:
        return 'Marketing'
    if 'ad' in u:
        return 'Ads'
    if 'homepage' in u:
        return 'Hack2skill'
    return 'Other'


def _normalize_occupation(raw_occupation):
    """Map raw occupation values to exactly 4 categories: Professional, Student, Startup, Freelance."""
    if not raw_occupation or not str(raw_occupation).strip():
        return 'Professional'
    u = str(raw_occupation).strip().lower().replace('-', '_').replace(' ', '_')
    if 'student' in u or u in ('college_student', 'school_student', 'college student', 'school student'):
        return 'Student'
    if 'startup' in u:
        return 'Startup'
    if 'freelance' in u or 'freelancer' in u:
        return 'Freelance'
    # professional, PROFESSIONAL, or any other value (e.g. job titles) -> Professional
    return 'Professional'


def _fetch_charts_data(period, summary=None):
    """Internal function to fetch charts data. If summary is provided (e.g. from combined /data), reuse total_users for registration source to avoid extra count query."""
    try:
        cutoff_date = _get_period_dates(period)
        date_cond = _date_filter_condition(cutoff_date)
        
        base_query = UserPIICombined.query
        if date_cond is not None:
            base_query = base_query.filter(date_cond)
        
        # Gender distribution
        gender_distribution = []
        try:
            gender_query = db.session.query(
                UserPIICombined.gender,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.gender.isnot(None),
                UserPIICombined.gender != ''
            )
            if date_cond is not None:
                gender_query = gender_query.filter(date_cond)
            gender_data = gender_query.group_by(
                UserPIICombined.gender
            ).all()
            gender_distribution = [{'label': g[0], 'value': g[1]} for g in gender_data]
        except:
            gender_distribution = []
        
        # Registration source bifurcation: map UTM (contains) -> Google, Outreach, Marketing, Ads, Hack2skill, Other
        registration_source_bifurcation = []
        try:
            utm_query = db.session.query(
                UserPIICombined.utm_medium,
                func.count(UserPIICombined.id).label('count')
            )
            if date_cond is not None:
                utm_query = utm_query.filter(date_cond)
            utm_query = utm_query.group_by(UserPIICombined.utm_medium).all()
            agg = {'Google': 0, 'Outreach': 0, 'Marketing': 0, 'Ads': 0, 'Hack2skill': 0, 'Other': 0}
            for utm_val, cnt in utm_query:
                label = _utm_to_registration_source(utm_val)
                agg[label] = agg.get(label, 0) + (cnt or 0)
            registration_source_bifurcation = [
                {'label': 'Google', 'value': agg['Google']},
                {'label': 'Outreach', 'value': agg['Outreach']},
                {'label': 'Marketing', 'value': agg['Marketing']},
                {'label': 'Ads', 'value': agg['Ads']},
                {'label': 'Hack2skill', 'value': agg['Hack2skill']},
                {'label': 'Other', 'value': agg['Other']}
            ]
        except Exception:
            registration_source_bifurcation = [
                {'label': 'Google', 'value': 0}, {'label': 'Outreach', 'value': 0},
                {'label': 'Marketing', 'value': 0}, {'label': 'Ads', 'value': 0},
                {'label': 'Hack2skill', 'value': 0}, {'label': 'Other', 'value': 0}
            ]
        
        # Top domains
        top_domains_data = []
        try:
            domains_query = db.session.query(
                UserPIICombined.domain,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.domain.isnot(None),
                UserPIICombined.domain != ''
            )
            if date_cond is not None:
                domains_query = domains_query.filter(date_cond)
            all_domains = domains_query.group_by(
                UserPIICombined.domain
            ).order_by(desc('count')).all()
            top_domains_data = [{'label': d[0], 'value': d[1]} for d in all_domains[:10]]
        except:
            top_domains_data = []

        # User segmentation by industry (from pre-computed industry column)
        user_segmentation = {'industries': []}
        try:
            industry_query = db.session.query(
                UserPIICombined.industry,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.industry.isnot(None),
                UserPIICombined.industry != ''
            )
            if date_cond is not None:
                industry_query = industry_query.filter(date_cond)
            industry_rows = industry_query.group_by(
                UserPIICombined.industry
            ).order_by(desc('count')).all()
            industries_list = []
            for ind_name, count in industry_rows:
                if not ind_name or ind_name == 'Other':
                    continue
                # User segmentation chart: display "Information Technology" for Technology
                display_label = 'Information Technology' if ind_name == 'Technology' else ind_name
                industries_list.append({
                    'label': display_label,
                    'value': int(count) if count else 0,
                })
            industries_list.sort(key=lambda x: x['value'], reverse=True)
            user_segmentation = {'industries': industries_list}
        except:
            user_segmentation = {'industries': []}
        
        # Top cities (top 10)
        top_cities_data = []
        try:
            cities_query = db.session.query(
                UserPIICombined.city,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.city.isnot(None),
                UserPIICombined.city != ''
            )
            if date_cond is not None:
                cities_query = cities_query.filter(date_cond)
            top_cities = cities_query.group_by(
                UserPIICombined.city
            ).order_by(desc('count')).limit(10).all()
            top_cities_data = [{'label': c[0], 'value': c[1]} for c in top_cities]
        except:
            top_cities_data = []
        
        # Top cities outside India (top 10), label: "City (Country)"
        top_cities_outside_india_data = []
        try:
            cities_outside_query = db.session.query(
                UserPIICombined.city,
                UserPIICombined.country,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.city.isnot(None),
                UserPIICombined.city != '',
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                ~country_column_matches_canonical(UserPIICombined.country, 'India'),
            )
            if date_cond is not None:
                cities_outside_query = cities_outside_query.filter(date_cond)
            cities_outside = cities_outside_query.group_by(
                UserPIICombined.city,
                UserPIICombined.country
            ).order_by(desc('count')).all()
            _merged_out = defaultdict(int)
            for c in cities_outside:
                city, raw_cty, cnt = c[0], c[1], c[2]
                cty = normalize_country(raw_cty) or (raw_cty or '')
                _merged_out[(city, cty)] += int(cnt or 0)
            _top_out = sorted(_merged_out.items(), key=lambda x: -x[1])[:10]
            top_cities_outside_india_data = [
                {'label': f'{k[0]} ({k[1]})', 'value': v}
                for k, v in _top_out
            ]
        except Exception:
            top_cities_outside_india_data = []
        
        # Top states (top 10)
        top_states_data = []
        try:
            states_query = db.session.query(
                UserPIICombined.state,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.state.isnot(None),
                UserPIICombined.state != ''
            )
            if date_cond is not None:
                states_query = states_query.filter(date_cond)
            top_states = states_query.group_by(
                UserPIICombined.state
            ).order_by(desc('count')).all()
            merged_ts = merge_state_count_rows([(s[0], s[1]) for s in top_states])[:10]
            top_states_data = [{'label': lbl, 'value': val} for lbl, val in merged_ts]
        except:
            top_states_data = []
        
        # Country distribution
        country_distribution = []
        try:
            countries_query = db.session.query(
                UserPIICombined.country,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != ''
            )
            if date_cond is not None:
                countries_query = countries_query.filter(date_cond)
            countries = countries_query.group_by(
                UserPIICombined.country
            ).order_by(desc('count')).all()
            merged_cdist = merge_country_count_rows([(c[0], c[1]) for c in countries])[:10]
            country_distribution = [{'label': lbl, 'value': val} for lbl, val in merged_cdist]
        except:
            country_distribution = []
        
        # Top organizations (top 20) – only PROFESSIONAL, STARTUP, FREELANCE (exclude students); normalize & merge duplicates
        top_organizations_data = []
        try:
            from server.utils.org_normalize import merge_org_counts
            occupation_filter = or_(
                UserPIICombined.occupation.ilike('%professional%'),
                UserPIICombined.occupation.ilike('%startup%'),
                UserPIICombined.occupation.ilike('%freelance%')
            )
            orgs_query = db.session.query(
                UserPIICombined.organization_name,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.organization_name.isnot(None),
                UserPIICombined.organization_name != '',
                occupation_filter
            )
            if date_cond is not None:
                orgs_query = orgs_query.filter(date_cond)
            all_orgs = orgs_query.group_by(
                UserPIICombined.organization_name
            ).order_by(desc('count')).all()
            merged = merge_org_counts([(o[0], o[1]) for o in all_orgs])
            top_organizations_data = merged[:20]
        except Exception:
            top_organizations_data = []
        
        # Class stream distribution
        class_stream_data = []
        try:
            streams_query = db.session.query(
                UserPIICombined.class_stream,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.class_stream.isnot(None),
                UserPIICombined.class_stream != ''
            )
            if date_cond is not None:
                streams_query = streams_query.filter(date_cond)
            streams = streams_query.group_by(
                UserPIICombined.class_stream
            ).order_by(desc('count')).all()
            class_stream_data = [{'label': s[0], 'value': s[1]} for s in streams]
        except:
            class_stream_data = []
        
        # Designation distribution (top 10)
        designation_data = []
        try:
            designation_query = db.session.query(
                UserPIICombined.designation,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.designation.isnot(None),
                UserPIICombined.designation != ''
            )
            if date_cond is not None:
                designation_query = designation_query.filter(date_cond)
            designations = designation_query.group_by(
                UserPIICombined.designation
            ).order_by(desc('count')).limit(10).all()
            designation_data = [{'label': d[0], 'value': d[1]} for d in designations]
        except:
            designation_data = []

        # Persona distribution (designation-based role personas)
        persona_data = []
        try:
            persona_query = db.session.query(
                UserPIICombined.persona,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.persona.isnot(None),
                UserPIICombined.persona != ''
            )
            if date_cond is not None:
                persona_query = persona_query.filter(date_cond)
            personas = persona_query.group_by(
                UserPIICombined.persona
            ).order_by(desc('count')).all()
            persona_data = [{'label': p[0], 'value': p[1]} for p in personas]
        except:
            persona_data = []
        
        # Occupation distribution: normalize to 4 categories (Professional, Student, Startup, Freelance)
        occupation_data = []
        try:
            occupation_query = db.session.query(
                UserPIICombined.occupation,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.occupation.isnot(None),
                UserPIICombined.occupation != ''
            )
            if date_cond is not None:
                occupation_query = occupation_query.filter(date_cond)
            occupations = occupation_query.group_by(UserPIICombined.occupation).all()
            agg = {'Professional': 0, 'Student': 0, 'Startup': 0, 'Freelance': 0}
            for raw_occ, cnt in occupations:
                label = _normalize_occupation(raw_occ)
                agg[label] = agg.get(label, 0) + (cnt or 0)
            occupation_data = [
                {'label': 'Professional', 'value': agg['Professional']},
                {'label': 'Student', 'value': agg['Student']},
                {'label': 'Startup', 'value': agg['Startup']},
                {'label': 'Freelance', 'value': agg['Freelance']}
            ]
        except Exception:
            occupation_data = []
        
        # Age groups distribution - Optimized using SQL CASE statements
        age_groups_data = []
        try:
            today = datetime.now().date()
            
            # Use SQL CASE to calculate age groups directly in database
            age_expr = func.extract('year', func.age(today, UserPIICombined.date_of_birth))
            age_group_expr = case(
                (age_expr.between(18, 25), '18-25'),
                (age_expr.between(26, 35), '26-35'),
                (age_expr.between(36, 45), '36-45'),
                (age_expr.between(46, 55), '46-55'),
                (age_expr > 55, '56+'),
                else_=None
            )
            
            age_query = db.session.query(
                age_group_expr.label('age_group'),
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.date_of_birth.isnot(None),
                age_expr >= 18  # Only count adults
            )
            if date_cond is not None:
                age_query = age_query.filter(date_cond)
            
            age_results = age_query.group_by(age_group_expr).all()
            age_groups_data = [{'label': r[0], 'value': r[1]} for r in age_results if r[0] is not None]
        except Exception as e:
            # Fallback to Python calculation if SQL fails
            try:
                print(f"SQL age calculation failed, using fallback: {e}")
                today = datetime.now().date()
                dob_query = UserPIICombined.query.filter(
                    UserPIICombined.date_of_birth.isnot(None)
                )
                if date_cond is not None:
                    dob_query = dob_query.filter(date_cond)
                # Limit to 10000 records for fallback
                users_with_dob = dob_query.limit(10000).all()
                
                age_ranges = {
                    '18-25': 0,
                    '26-35': 0,
                    '36-45': 0,
                    '46-55': 0,
                    '56+': 0
                }
                
                for user in users_with_dob:
                    if user.date_of_birth:
                        age = today.year - user.date_of_birth.year - (
                            (today.month, today.day) < (user.date_of_birth.month, user.date_of_birth.day)
                        )
                        
                        if 18 <= age <= 25:
                            age_ranges['18-25'] += 1
                        elif 26 <= age <= 35:
                            age_ranges['26-35'] += 1
                        elif 36 <= age <= 45:
                            age_ranges['36-45'] += 1
                        elif 46 <= age <= 55:
                            age_ranges['46-55'] += 1
                        elif age > 55:
                            age_ranges['56+'] += 1
                
                age_groups_data = [{'label': k, 'value': v} for k, v in age_ranges.items() if v > 0]
            except Exception as e2:
                print(f"Error calculating age groups: {e2}")
                age_groups_data = []
        
        # Registration trends (daily) using registered_at column
        registration_trends = []
        try:
            # Start date from period: Jan 15 for 'all', or period cutoff
            if cutoff_date:
                start_date = cutoff_date
            else:
                # For 'all' data: line charts start from Jan 15 (current or previous year)
                now = datetime.now()
                start_date = datetime(now.year, 1, 15)
                if start_date.date() > now.date():
                    start_date = datetime(now.year - 1, 1, 15)
            # Use date_trunc for PostgreSQL compatibility, filter out NULL registered_at
            trends = db.session.query(
                func.date_trunc('day', UserPIICombined.registered_at).label('date'),
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.registered_at.isnot(None),
                UserPIICombined.registered_at >= start_date
            ).group_by(
                func.date_trunc('day', UserPIICombined.registered_at)
            ).order_by('date').all()
            
            # Create a complete date range to fill in missing days with 0
            date_dict = {}
            for t in trends:
                # Convert to date object
                if isinstance(t[0], datetime):
                    date_key = t[0].date()
                else:
                    date_key = t[0]
                date_dict[date_key] = t[1]
            
            complete_trends = []
            current_date = start_date.date()
            today = datetime.now().date()
            
            while current_date <= today:
                count = date_dict.get(current_date, 0)
                complete_trends.append({
                    'label': current_date.strftime('%b %d'),
                    'value': count,
                    'date': current_date.isoformat()
                })
                current_date += timedelta(days=1)
            
            registration_trends = complete_trends
        except Exception as e:
            print(f"Error calculating registration trends: {e}")
            registration_trends = []
        
        # Social media presence
        social_media_data = []
        try:
            github_query = UserPIICombined.query.filter(
                UserPIICombined.github_url.isnot(None),
                UserPIICombined.github_url != ''
            )
            if date_cond is not None:
                github_query = github_query.filter(date_cond)
            github_count = github_query.count() or 0
            
            linkedin_query = UserPIICombined.query.filter(
                UserPIICombined.linkedin_url.isnot(None),
                UserPIICombined.linkedin_url != ''
            )
            if date_cond is not None:
                linkedin_query = linkedin_query.filter(date_cond)
            linkedin_count = linkedin_query.count() or 0
            
            both_query = UserPIICombined.query.filter(
                UserPIICombined.github_url.isnot(None),
                UserPIICombined.github_url != '',
                UserPIICombined.linkedin_url.isnot(None),
                UserPIICombined.linkedin_url != ''
            )
            if date_cond is not None:
                both_query = both_query.filter(date_cond)
            both_count = both_query.count() or 0
            
            # Get total for period
            period_total = base_query.count()
            
            github_only = max(0, github_count - both_count)
            linkedin_only = max(0, linkedin_count - both_count)
            neither = max(0, period_total - github_count - linkedin_count + both_count)
            
            social_media_data = [
                {'label': 'GitHub Only', 'value': github_only},
                {'label': 'LinkedIn Only', 'value': linkedin_only},
                {'label': 'Both', 'value': both_count},
                {'label': 'Neither', 'value': neither}
            ]
            
            # Filter out zero values
            social_media_data = [item for item in social_media_data if item['value'] > 0]
        except:
            social_media_data = []

        # India state-wise registration counts (for heatmap)
        india_state_registrations = []
        try:
            india_state_query = db.session.query(
                UserPIICombined.state,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                country_column_matches_canonical(UserPIICombined.country, 'India'),
                UserPIICombined.state.isnot(None),
                UserPIICombined.state != ''
            )
            if date_cond is not None:
                india_state_query = india_state_query.filter(date_cond)
            india_states = india_state_query.group_by(UserPIICombined.state).order_by(desc('count')).all()
            merged_is = merge_state_count_rows([(s[0], s[1]) for s in india_states])
            india_state_registrations = [{'state': lbl, 'value': val} for lbl, val in merged_is]
        except Exception:
            india_state_registrations = []

        # APAC country-wise registration counts (for heatmap) – outside India only (“Outside Indian Registrations”)
        apac_country_registrations = []
        try:
            apac_map_cond = country_column_matches_any_canonical(
                UserPIICombined.country, APAC_FOR_MAP_EXCL_INDIA
            )
            apac_country_query = db.session.query(
                UserPIICombined.country,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                ~country_column_matches_canonical(UserPIICombined.country, 'India'),
                apac_map_cond,
            )
            if date_cond is not None:
                apac_country_query = apac_country_query.filter(date_cond)
            apac_countries = apac_country_query.group_by(UserPIICombined.country).order_by(desc('count')).all()
            merged_map = merge_country_count_rows([(c[0], c[1]) for c in apac_countries])
            apac_country_registrations = [{'country': lbl, 'value': val} for lbl, val in merged_map]
        except Exception:
            apac_country_registrations = []

        return {
            'gender_distribution': gender_distribution,
            'registration_source_bifurcation': registration_source_bifurcation,
            'top_domains': top_domains_data,
            'user_segmentation': user_segmentation,
            'top_cities': top_cities_data,
            'top_cities_outside_india': top_cities_outside_india_data,
            'top_states': top_states_data,
            'country_distribution': country_distribution,
            'top_organizations': top_organizations_data,
            'class_stream_distribution': class_stream_data,
            'designation_distribution': designation_data,
            'persona_distribution': persona_data,
            'occupation_distribution': occupation_data,
            'age_groups': age_groups_data,
            'registration_trends': registration_trends,
            'social_media': social_media_data,
            'india_state_registrations': india_state_registrations,
            'apac_country_registrations': apac_country_registrations
        }
    except Exception as e:
        # Return empty data instead of error
        return {
            'gender_distribution': [],
            'registration_source_bifurcation': [{'label': 'Google', 'value': 0}, {'label': 'Outreach', 'value': 0}, {'label': 'Marketing', 'value': 0}, {'label': 'Ads', 'value': 0}, {'label': 'Hack2skill', 'value': 0}, {'label': 'Other', 'value': 0}],
            'top_domains': [],
            'user_segmentation': {'industries': []},
            'top_cities': [],
            'top_cities_outside_india': [],
            'top_states': [],
            'country_distribution': [],
            'top_organizations': [],
            'class_stream_distribution': [],
            'designation_distribution': [],
            'persona_distribution': [],
            'occupation_distribution': [],
            'age_groups': [],
            'registration_trends': [],
            'social_media': [],
            'india_state_registrations': [],
            'apac_country_registrations': []
        }
