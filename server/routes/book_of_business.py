"""
Book of Business Registrations page and API.
Lists users whose bob_match is True (organization matched to BOB list).
"""
import csv
import io
import re
from datetime import date
from flask import Blueprint, request, jsonify, Response
from sqlalchemy import or_, func, desc
from server.models import db, UserPIICombined
from server.utils.cohort_participant_models import participant_model
from server.utils.auth import get_current_user
from server.utils.permissions import require_page_access
from server.utils.industry_map import get_industry
from server.utils.state_normalize import (
    normalize_state,
    get_state_filter_values,
    distinct_canonical_states,
    merge_state_count_rows,
)
from server.utils.country_normalize import (
    country_filter_or_conditions,
    distinct_canonical_countries,
    country_column_matches_canonical,
    merge_country_count_rows,
    normalize_country,
)

bp = Blueprint('book_of_business', __name__)

_PAREN_RE = re.compile(r'\s*\(.*?\)\s*$')

def _clean_designation(designation, occupation):
    """Return cleaned designation: 'Student' when occupation contains student,
    otherwise strip trailing parenthesized numbers."""
    occ = (occupation or '').strip().lower()
    if 'student' in occ:
        return 'Student'
    raw = (designation or '').strip()
    return _PAREN_RE.sub('', raw).strip() if raw else ''


def _PII():
    """Return the cohort-appropriate UserPIICombined model."""
    return participant_model(UserPIICombined)


def _bob_base():
    """Query base for bob_match=True (cohort-specific)."""
    PII = _PII()
    return PII.query.filter(PII.bob_match == True)


def _filter_conditions(search=None, countries=None, states=None, cities=None, organizations=None, designations=None, industries=None):
    """Return list of filter conditions for BOB base. Accepts lists for multi-select filters."""
    PII = _PII()
    conditions = []
    if search:
        conditions.append(
            or_(
                PII.name.ilike(f'%{search}%'),
                PII.email.ilike(f'%{search}%'),
                PII.organization_name.ilike(f'%{search}%'),
            )
        )
    if countries:
        cf = country_filter_or_conditions(PII.country, countries)
        if cf is not None:
            conditions.append(cf)
    if states:
        all_state_values = []
        for state in states:
            state_values = get_state_filter_values(state)
            if state_values:
                all_state_values.extend(state_values)
            else:
                all_state_values.append(state)
        if all_state_values:
            conditions.append(PII.state.in_(all_state_values))
    if cities:
        conditions.append(or_(*[PII.city.ilike(f'%{c}%') for c in cities]))
    if organizations:
        from server.utils.org_normalize import get_org_filter_conditions
        org_cond = get_org_filter_conditions(PII.organization_name, organizations)
        if org_cond is not None:
            conditions.append(org_cond)
    if designations:
        conditions.append(or_(*[PII.designation.ilike(f'%{d}%') for d in designations]))
    if industries:
        conditions.append(or_(*[PII.industry.ilike(f'%{i}%') for i in industries]))
    return conditions


@bp.route('/stats', methods=['GET'])
@require_page_access('book_of_business')
def get_stats():
    """
    Return stats for BOB-matched users, optionally filtered by search, country, state, city.
    Query params: search, country, state, city (same as /list).
    """
    try:
        search = request.args.get('search', '').strip()
        countries = [x.strip() for x in request.args.getlist('country') if x and x.strip()]
        states = [x.strip() for x in request.args.getlist('state') if x and x.strip()]
        cities = [x.strip() for x in request.args.getlist('city') if x and x.strip()]
        organizations = [x.strip() for x in request.args.getlist('organization') if x and x.strip()]
        designations = [x.strip() for x in request.args.getlist('designation') if x and x.strip()]
        industries = [x.strip() for x in request.args.getlist('industry') if x and x.strip()]
        filter_conds = _filter_conditions(
            search=search or None, countries=countries or None, states=states or None,
            cities=cities or None, organizations=organizations or None,
            designations=designations or None, industries=industries or None
        )

        PII = _PII()
        base = _bob_base()
        for c in filter_conds:
            base = base.filter(c)
        total_bob_match = base.count() or 0

        def _apply_filters(q):
            for c in filter_conds:
                q = q.filter(c)
            return q

        top_india_state = None
        top_india_state_count = None
        top_india_city = None
        top_india_city_count = None
        try:
            india_state_q = db.session.query(
                PII.state,
                func.count(PII.id).label('count')
            ).filter(
                PII.bob_match == True,
                PII.country.isnot(None),
                PII.country != '',
                country_column_matches_canonical(PII.country, 'India'),
                PII.state.isnot(None),
                PII.state != ''
            )
            india_state_q = _apply_filters(india_state_q)
            ist_rows = india_state_q.group_by(PII.state).order_by(desc('count')).all()
            merged_ist = merge_state_count_rows([(r[0], r[1]) for r in ist_rows])
            if merged_ist:
                top_india_state = merged_ist[0][0]
                top_india_state_count = merged_ist[0][1]
            india_city_q = db.session.query(
                PII.city,
                func.count(PII.id).label('count')
            ).filter(
                PII.bob_match == True,
                PII.country.isnot(None),
                PII.country != '',
                country_column_matches_canonical(PII.country, 'India'),
                PII.city.isnot(None),
                PII.city != ''
            )
            india_city_q = _apply_filters(india_city_q)
            city_row = india_city_q.group_by(PII.city).order_by(desc('count')).first()
            if city_row:
                top_india_city = city_row[0]
                top_india_city_count = city_row[1]
        except Exception:
            pass

        top_apac_country = None
        top_apac_country_count = None
        top_apac_city = None
        top_apac_city_count = None
        try:
            apac_country_q = db.session.query(
                PII.country,
                func.count(PII.id).label('count')
            ).filter(
                PII.bob_match == True,
                PII.country.isnot(None),
                PII.country != '',
                ~country_column_matches_canonical(PII.country, 'India'),
            )
            apac_country_q = _apply_filters(apac_country_q)
            apac_rows = apac_country_q.group_by(PII.country).all()
            merged_c = merge_country_count_rows([(r[0], r[1]) for r in apac_rows])
            merged_c = [(c, n) for c, n in merged_c if c != 'India']
            if merged_c:
                top_apac_country, top_apac_country_count = merged_c[0][0], merged_c[0][1]
            apac_city_q = db.session.query(
                PII.city,
                func.count(PII.id).label('count')
            ).filter(
                PII.bob_match == True,
                PII.country.isnot(None),
                PII.country != '',
                ~country_column_matches_canonical(PII.country, 'India'),
                PII.city.isnot(None),
                PII.city != ''
            )
            apac_city_q = _apply_filters(apac_city_q)
            city_row = apac_city_q.group_by(PII.city).order_by(desc('count')).first()
            if city_row:
                top_apac_city = city_row[0]
                top_apac_city_count = city_row[1]
        except Exception:
            pass

        top_organization = None
        top_organization_count = None
        try:
            org_q = db.session.query(
                PII.organization_name,
                func.count(PII.id).label('count')
            ).filter(
                PII.bob_match == True,
                PII.organization_name.isnot(None),
                PII.organization_name != ''
            )
            org_q = _apply_filters(org_q)
            org_row = org_q.group_by(PII.organization_name).order_by(desc('count')).first()
            if org_row and org_row[0]:
                top_organization = org_row[0]
                top_organization_count = org_row[1]
        except Exception:
            pass

        return jsonify({
            'total_bob_match': total_bob_match,
            'top_india_state': normalize_state(top_india_state) if top_india_state else top_india_state,
            'top_india_state_count': top_india_state_count,
            'top_india_city': top_india_city,
            'top_india_city_count': top_india_city_count,
            'top_apac_country': top_apac_country,
            'top_apac_country_count': top_apac_country_count,
            'top_apac_city': top_apac_city,
            'top_apac_city_count': top_apac_city_count,
            'top_organization': top_organization,
            'top_organization_count': top_organization_count,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/list', methods=['GET'])
@require_page_access('book_of_business')
def list_registrations():
    """
    List Book of Business registrations (bob_match = True).
    Query: search, country, state, city, page, per_page.
    Returns: rows (name, country, state, city, organization), total, page, per_page.
    """
    try:
        search = request.args.get('search', '').strip()
        countries = [x.strip() for x in request.args.getlist('country') if x and x.strip()]
        states = [x.strip() for x in request.args.getlist('state') if x and x.strip()]
        cities = [x.strip() for x in request.args.getlist('city') if x and x.strip()]
        organizations = [x.strip() for x in request.args.getlist('organization') if x and x.strip()]
        designations = [x.strip() for x in request.args.getlist('designation') if x and x.strip()]
        industries = [x.strip() for x in request.args.getlist('industry') if x and x.strip()]
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)

        filter_conds = _filter_conditions(
            search=search or None, countries=countries or None, states=states or None,
            cities=cities or None, organizations=organizations or None,
            designations=designations or None, industries=industries or None
        )
        PII = _PII()
        query = PII.query.filter(PII.bob_match == True)
        for c in filter_conds:
            query = query.filter(c)

        query = query.order_by(PII.name.asc().nullslast(), PII.email.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        rows = pagination.items

        return jsonify({
            'rows': [
                {
                    'name': r.name or '',
                    'country': normalize_country(r.country) or r.country or '',
                    'state': normalize_state(r.state) if r.state else '',
                    'city': r.city or '',
                    'organization': r.organization_name or '',
                    'designation': _clean_designation(r.designation, r.occupation),
                    'industry': r.industry or '',
                    'occupation': r.occupation or '',
                }
                for r in rows
            ],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/download', methods=['GET'])
@require_page_access('book_of_business')
def download_csv():
    """Download BOB registrations as CSV. Accepts same filter params as /list."""
    try:
        search = request.args.get('search', '').strip()
        countries = [x.strip() for x in request.args.getlist('country') if x and x.strip()]
        states = [x.strip() for x in request.args.getlist('state') if x and x.strip()]
        cities = [x.strip() for x in request.args.getlist('city') if x and x.strip()]
        organizations = [x.strip() for x in request.args.getlist('organization') if x and x.strip()]
        designations = [x.strip() for x in request.args.getlist('designation') if x and x.strip()]
        industries = [x.strip() for x in request.args.getlist('industry') if x and x.strip()]

        filter_conds = _filter_conditions(
            search=search or None, countries=countries or None, states=states or None,
            cities=cities or None, organizations=organizations or None,
            designations=designations or None, industries=industries or None
        )
        PII = _PII()
        query = _bob_base()
        for c in filter_conds:
            query = query.filter(c)
        query = query.order_by(PII.name.asc().nullslast(), PII.email.asc())

        si = io.StringIO()
        writer = csv.writer(si)
        writer.writerow(['Name', 'Country', 'State', 'City', 'Organization', 'Designation', 'Industry'])
        for r in query.all():
            writer.writerow([
                r.name or '', normalize_country(r.country) or r.country or '',
                normalize_state(r.state) if r.state else '',
                r.city or '', r.organization_name or '',
                _clean_designation(r.designation, r.occupation),
                r.industry or '',
            ])

        output = si.getvalue()
        filename = f'book_of_business_{date.today().isoformat()}.csv'
        return Response(
            output, mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/filters', methods=['GET'])
@require_page_access('book_of_business')
def get_filter_options():
    """
    Return distinct country, state, city for bob_match=True (for filter dropdowns).
    """
    try:
        PII = _PII()
        base = PII.query.filter(PII.bob_match == True)
        raw_cty = [r[0] for r in base.with_entities(PII.country).distinct().filter(
            PII.country.isnot(None), PII.country != ''
        ).order_by(PII.country).all() if r[0]]
        countries = distinct_canonical_countries(raw_cty)
        raw_states = [r[0] for r in base.with_entities(PII.state).distinct().filter(
            PII.state.isnot(None), PII.state != ''
        ).order_by(PII.state).all() if r[0]]
        states = distinct_canonical_states(raw_states)
        cities = [r[0] for r in base.with_entities(PII.city).distinct().filter(
            PII.city.isnot(None), PII.city != ''
        ).order_by(PII.city).all() if r[0]]
        from server.utils.org_normalize import normalize_org_list
        raw_orgs = [r[0] for r in base.with_entities(PII.organization_name).distinct().filter(
            PII.organization_name.isnot(None), PII.organization_name != ''
        ).order_by(PII.organization_name).all() if r[0]]
        organizations = normalize_org_list(raw_orgs)
        raw_designations = [r[0] for r in base.with_entities(PII.designation).distinct().filter(
            PII.designation.isnot(None), PII.designation != ''
        ).order_by(PII.designation).all() if r[0]]
        import re as _re
        seen_desig = {}
        for d in raw_designations:
            cleaned = _re.sub(r'\s*\(.*?\)\s*$', '', d).strip()
            if cleaned and cleaned.lower() not in seen_desig:
                seen_desig[cleaned.lower()] = cleaned
        designations = sorted(seen_desig.values(), key=str.lower)
        industries = [r[0] for r in base.with_entities(PII.industry).distinct().filter(
            PII.industry.isnot(None), PII.industry != ''
        ).order_by(PII.industry).all() if r[0]]
        return jsonify({
            'countries': countries,
            'states': states,
            'cities': cities,
            'organizations': organizations,
            'designations': designations,
            'industries': industries,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
