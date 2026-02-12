"""
Book of Business Registrations page and API.
Lists users whose bob_match is True (organization matched to BOB list).
"""
from flask import Blueprint, request, jsonify
from sqlalchemy import or_, func, desc
from server.models import db, UserPII
from server.utils.auth import get_current_user
from server.utils.permissions import require_page_access
from server.utils.state_normalize import (
    normalize_state,
    get_state_filter_values,
    distinct_canonical_states,
)

bp = Blueprint('book_of_business', __name__)


def _bob_base():
    """Query base for bob_match=True."""
    return UserPII.query.filter(UserPII.bob_match == True)


def _filter_conditions(search=None, country=None, state=None, city=None, organization=None):
    """Return list of filter conditions for BOB base (search, country, state, city, organization)."""
    conditions = []
    if search:
        conditions.append(
            or_(
                UserPII.name.ilike(f'%{search}%'),
                UserPII.email.ilike(f'%{search}%'),
                UserPII.organization_name.ilike(f'%{search}%'),
            )
        )
    if country:
        conditions.append(UserPII.country.ilike(f'%{country}%'))
    if state:
        state_values = get_state_filter_values(state)
        if state_values:
            conditions.append(UserPII.state.in_(state_values))
        else:
            conditions.append(UserPII.state.ilike(f'%{state}%'))
    if city:
        conditions.append(UserPII.city.ilike(f'%{city}%'))
    if organization:
        conditions.append(UserPII.organization_name.ilike(f'%{organization}%'))
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
        country = request.args.get('country', '').strip()
        state = request.args.get('state', '').strip()
        city = request.args.get('city', '').strip()
        organization = request.args.get('organization', '').strip()
        filter_conds = _filter_conditions(search=search or None, country=country or None, state=state or None, city=city or None, organization=organization or None)

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
                UserPII.state,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.bob_match == True,
                UserPII.country.isnot(None),
                UserPII.country != '',
                UserPII.country.ilike('%India%'),
                UserPII.state.isnot(None),
                UserPII.state != ''
            )
            india_state_q = _apply_filters(india_state_q)
            state_row = india_state_q.group_by(UserPII.state).order_by(desc('count')).first()
            if state_row:
                top_india_state = state_row[0]
                top_india_state_count = state_row[1]
            india_city_q = db.session.query(
                UserPII.city,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.bob_match == True,
                UserPII.country.isnot(None),
                UserPII.country != '',
                UserPII.country.ilike('%India%'),
                UserPII.city.isnot(None),
                UserPII.city != ''
            )
            india_city_q = _apply_filters(india_city_q)
            city_row = india_city_q.group_by(UserPII.city).order_by(desc('count')).first()
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
                UserPII.country,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.bob_match == True,
                UserPII.country.isnot(None),
                UserPII.country != '',
                ~UserPII.country.ilike('%India%')
            )
            apac_country_q = _apply_filters(apac_country_q)
            country_row = apac_country_q.group_by(UserPII.country).order_by(desc('count')).first()
            if country_row:
                top_apac_country = country_row[0]
                top_apac_country_count = country_row[1]
            apac_city_q = db.session.query(
                UserPII.city,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.bob_match == True,
                UserPII.country.isnot(None),
                UserPII.country != '',
                ~UserPII.country.ilike('%India%'),
                UserPII.city.isnot(None),
                UserPII.city != ''
            )
            apac_city_q = _apply_filters(apac_city_q)
            city_row = apac_city_q.group_by(UserPII.city).order_by(desc('count')).first()
            if city_row:
                top_apac_city = city_row[0]
                top_apac_city_count = city_row[1]
        except Exception:
            pass

        top_organization = None
        top_organization_count = None
        try:
            org_q = db.session.query(
                UserPII.organization_name,
                func.count(UserPII.id).label('count')
            ).filter(
                UserPII.bob_match == True,
                UserPII.organization_name.isnot(None),
                UserPII.organization_name != ''
            )
            org_q = _apply_filters(org_q)
            org_row = org_q.group_by(UserPII.organization_name).order_by(desc('count')).first()
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
        country = request.args.get('country', '').strip()
        state = request.args.get('state', '').strip()
        city = request.args.get('city', '').strip()
        organization = request.args.get('organization', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)

        query = UserPII.query.filter(UserPII.bob_match == True)

        if search:
            query = query.filter(
                or_(
                    UserPII.name.ilike(f'%{search}%'),
                    UserPII.email.ilike(f'%{search}%'),
                    UserPII.organization_name.ilike(f'%{search}%'),
                )
            )
        if country:
            query = query.filter(UserPII.country.ilike(f'%{country}%'))
        if state:
            state_values = get_state_filter_values(state)
            if state_values:
                query = query.filter(UserPII.state.in_(state_values))
            else:
                query = query.filter(UserPII.state.ilike(f'%{state}%'))
        if city:
            query = query.filter(UserPII.city.ilike(f'%{city}%'))
        if organization:
            query = query.filter(UserPII.organization_name.ilike(f'%{organization}%'))

        query = query.order_by(UserPII.name.asc().nullslast(), UserPII.email.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        rows = pagination.items

        return jsonify({
            'rows': [
                {
                    'name': r.name or '',
                    'country': r.country or '',
                    'state': normalize_state(r.state) if r.state else '',
                    'city': r.city or '',
                    'organization': r.organization_name or '',
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


@bp.route('/filters', methods=['GET'])
@require_page_access('book_of_business')
def get_filter_options():
    """
    Return distinct country, state, city for bob_match=True (for filter dropdowns).
    """
    try:
        base = UserPII.query.filter(UserPII.bob_match == True)
        countries = [r[0] for r in base.with_entities(UserPII.country).distinct().filter(
            UserPII.country.isnot(None), UserPII.country != ''
        ).order_by(UserPII.country).all() if r[0]]
        raw_states = [r[0] for r in base.with_entities(UserPII.state).distinct().filter(
            UserPII.state.isnot(None), UserPII.state != ''
        ).order_by(UserPII.state).all() if r[0]]
        states = distinct_canonical_states(raw_states)
        cities = [r[0] for r in base.with_entities(UserPII.city).distinct().filter(
            UserPII.city.isnot(None), UserPII.city != ''
        ).order_by(UserPII.city).all() if r[0]]
        organizations = [r[0] for r in base.with_entities(UserPII.organization_name).distinct().filter(
            UserPII.organization_name.isnot(None), UserPII.organization_name != ''
        ).order_by(UserPII.organization_name).all() if r[0]]
        return jsonify({
            'countries': countries,
            'states': states,
            'cities': cities,
            'organizations': organizations,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
