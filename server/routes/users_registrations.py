"""
Users (Registrations) page and API.
Lists all users from user_pii with same stats, filters and columns as Book of Business.
"""
import csv
import io
from datetime import date
from flask import Blueprint, request, jsonify, Response
from sqlalchemy import or_, func, desc
from server.models import db, UserPIICombined
from server.utils.permissions import require_page_access
from server.utils.state_normalize import (
    normalize_state,
    get_state_filter_values,
    distinct_canonical_states,
)

bp = Blueprint('users_registrations', __name__)


def _users_base():
    """Query base for all users (user_pii)."""
    return UserPIICombined.query


def _filter_conditions(search=None, countries=None, states=None, cities=None, organizations=None):
    """Return list of filter conditions. Accepts lists for multi-select filters."""
    conditions = []
    if search:
        conditions.append(
            or_(
                UserPIICombined.name.ilike(f'%{search}%'),
                UserPIICombined.email.ilike(f'%{search}%'),
                UserPIICombined.organization_name.ilike(f'%{search}%'),
            )
        )
    if countries:
        conditions.append(or_(*[UserPIICombined.country.ilike(f'%{c}%') for c in countries]))
    if states:
        all_state_values = []
        for state in states:
            state_values = get_state_filter_values(state)
            if state_values:
                all_state_values.extend(state_values)
            else:
                all_state_values.append(state)
        if all_state_values:
            conditions.append(UserPIICombined.state.in_(all_state_values))
    if cities:
        conditions.append(or_(*[UserPIICombined.city.ilike(f'%{c}%') for c in cities]))
    if organizations:
        conditions.append(or_(*[UserPIICombined.organization_name.ilike(f'%{o}%') for o in organizations]))
    return conditions


@bp.route('/stats', methods=['GET'])
@require_page_access('users_registrations')
def get_stats():
    """
    Return stats for all users, optionally filtered by search, country, state, city, organization.
    Query params: search, country, state, city, organization (same as /list).
    """
    try:
        search = request.args.get('search', '').strip()
        countries = [x.strip() for x in request.args.getlist('country') if x and x.strip()]
        states = [x.strip() for x in request.args.getlist('state') if x and x.strip()]
        cities = [x.strip() for x in request.args.getlist('city') if x and x.strip()]
        organizations = [x.strip() for x in request.args.getlist('organization') if x and x.strip()]
        filter_conds = _filter_conditions(
            search=search or None, countries=countries or None, states=states or None,
            cities=cities or None, organizations=organizations or None
        )

        base = _users_base()
        for c in filter_conds:
            base = base.filter(c)
        total_users = base.count() or 0

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
                UserPIICombined.state,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                UserPIICombined.country.ilike('%India%'),
                UserPIICombined.state.isnot(None),
                UserPIICombined.state != ''
            )
            india_state_q = _apply_filters(india_state_q)
            state_row = india_state_q.group_by(UserPIICombined.state).order_by(desc('count')).first()
            if state_row:
                top_india_state = state_row[0]
                top_india_state_count = state_row[1]
            india_city_q = db.session.query(
                UserPIICombined.city,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                UserPIICombined.country.ilike('%India%'),
                UserPIICombined.city.isnot(None),
                UserPIICombined.city != ''
            )
            india_city_q = _apply_filters(india_city_q)
            city_row = india_city_q.group_by(UserPIICombined.city).order_by(desc('count')).first()
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
                UserPIICombined.country,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                ~UserPIICombined.country.ilike('%India%')
            )
            apac_country_q = _apply_filters(apac_country_q)
            country_row = apac_country_q.group_by(UserPIICombined.country).order_by(desc('count')).first()
            if country_row:
                top_apac_country = country_row[0]
                top_apac_country_count = country_row[1]
            apac_city_q = db.session.query(
                UserPIICombined.city,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.country.isnot(None),
                UserPIICombined.country != '',
                ~UserPIICombined.country.ilike('%India%'),
                UserPIICombined.city.isnot(None),
                UserPIICombined.city != ''
            )
            apac_city_q = _apply_filters(apac_city_q)
            city_row = apac_city_q.group_by(UserPIICombined.city).order_by(desc('count')).first()
            if city_row:
                top_apac_city = city_row[0]
                top_apac_city_count = city_row[1]
        except Exception:
            pass

        top_organization = None
        top_organization_count = None
        try:
            org_q = db.session.query(
                UserPIICombined.organization_name,
                func.count(UserPIICombined.id).label('count')
            ).filter(
                UserPIICombined.organization_name.isnot(None),
                UserPIICombined.organization_name != ''
            )
            org_q = _apply_filters(org_q)
            org_row = org_q.group_by(UserPIICombined.organization_name).order_by(desc('count')).first()
            if org_row and org_row[0]:
                top_organization = org_row[0]
                top_organization_count = org_row[1]
        except Exception:
            pass

        return jsonify({
            'total_users': total_users,
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
@require_page_access('users_registrations')
def list_registrations():
    """
    List all user registrations (user_pii).
    Query: search, country, state, city, organization, page, per_page.
    Returns: rows (name, country, state, city, organization), total, page, per_page.
    """
    try:
        search = request.args.get('search', '').strip()
        countries = [x.strip() for x in request.args.getlist('country') if x and x.strip()]
        states = [x.strip() for x in request.args.getlist('state') if x and x.strip()]
        cities = [x.strip() for x in request.args.getlist('city') if x and x.strip()]
        organizations = [x.strip() for x in request.args.getlist('organization') if x and x.strip()]
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)

        filter_conds = _filter_conditions(
            search=search or None, countries=countries or None, states=states or None,
            cities=cities or None, organizations=organizations or None
        )
        query = _users_base()
        for c in filter_conds:
            query = query.filter(c)

        query = query.order_by(UserPIICombined.name.asc().nullslast(), UserPIICombined.email.asc())
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


@bp.route('/download', methods=['GET'])
@require_page_access('users_registrations')
def download_csv():
    """Download user registrations as CSV. Accepts same filter params as /list."""
    try:
        search = request.args.get('search', '').strip()
        countries = [x.strip() for x in request.args.getlist('country') if x and x.strip()]
        states = [x.strip() for x in request.args.getlist('state') if x and x.strip()]
        cities = [x.strip() for x in request.args.getlist('city') if x and x.strip()]
        organizations = [x.strip() for x in request.args.getlist('organization') if x and x.strip()]

        filter_conds = _filter_conditions(
            search=search or None, countries=countries or None, states=states or None,
            cities=cities or None, organizations=organizations or None
        )
        query = _users_base()
        for c in filter_conds:
            query = query.filter(c)
        query = query.order_by(UserPIICombined.name.asc().nullslast(), UserPIICombined.email.asc())

        si = io.StringIO()
        writer = csv.writer(si)
        writer.writerow(['Name', 'Country', 'State', 'City', 'Organization'])
        for r in query.all():
            writer.writerow([
                r.name or '', r.country or '',
                normalize_state(r.state) if r.state else '',
                r.city or '', r.organization_name or '',
            ])

        output = si.getvalue()
        filename = f'users_registrations_{date.today().isoformat()}.csv'
        return Response(
            output, mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/filters', methods=['GET'])
@require_page_access('users_registrations')
def get_filter_options():
    """Return distinct country, state, city, organization for all user_pii (for filter dropdowns)."""
    try:
        base = _users_base()
        countries = [r[0] for r in base.with_entities(UserPIICombined.country).distinct().filter(
            UserPIICombined.country.isnot(None), UserPIICombined.country != ''
        ).order_by(UserPIICombined.country).all() if r[0]]
        raw_states = [r[0] for r in base.with_entities(UserPIICombined.state).distinct().filter(
            UserPIICombined.state.isnot(None), UserPIICombined.state != ''
        ).order_by(UserPIICombined.state).all() if r[0]]
        states = distinct_canonical_states(raw_states)
        cities = [r[0] for r in base.with_entities(UserPIICombined.city).distinct().filter(
            UserPIICombined.city.isnot(None), UserPIICombined.city != ''
        ).order_by(UserPIICombined.city).all() if r[0]]
        organizations = [r[0] for r in base.with_entities(UserPIICombined.organization_name).distinct().filter(
            UserPIICombined.organization_name.isnot(None), UserPIICombined.organization_name != ''
        ).order_by(UserPIICombined.organization_name).all() if r[0]]
        return jsonify({
            'countries': countries,
            'states': states,
            'cities': cities,
            'organizations': organizations,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
