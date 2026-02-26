"""
Skill Lab credits page and API (Skill Lab / Skillboost profiles list)
"""
import csv
import io
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, Response, stream_with_context
from server.models import db, SkillboostProfile, UserPII, CreditLink
from server.utils.auth import get_current_user
from server.utils.permissions import require_page_access
from server.utils.audit import set_audit_session_vars

bp = Blueprint('skilllab', __name__)


def run_credit_allocation():
    """
    Allocate credit links to verified skillboost_profiles that don't have one.
    Uses links in display_order; each link gets up to max_allocations (e.g. 3000).
    Returns dict: allocated (int), skipped_no_capacity (int).
    """
    links = CreditLink.query.order_by(CreditLink.display_order).all()
    if not links:
        return {'allocated': 0, 'skipped_no_capacity': 0}
    # Current allocation count per link id
    from sqlalchemy import func as sql_func
    counts = db.session.query(
        SkillboostProfile.credit_link_id,
        sql_func.count(SkillboostProfile.email).label('cnt')
    ).filter(
        SkillboostProfile.credit_link_id.isnot(None)
    ).group_by(SkillboostProfile.credit_link_id).all()
    link_counts = {lid: c for lid, c in counts}
    allocated = 0
    skipped = 0
    # Verified, unallocated profiles, stable order
    pending = SkillboostProfile.query.filter(
        SkillboostProfile.valid == True,
        SkillboostProfile.credit_link_id.is_(None)
    ).order_by(SkillboostProfile.created_at, SkillboostProfile.email).all()
    for profile in pending:
        chosen = None
        for i, link in enumerate(links):
            n = link_counts.get(link.id, 0)
            if n >= link.max_allocations:
                continue
            # Use this link only if every previous link (in display_order) is full
            all_previous_full = all(
                link_counts.get(links[j].id, 0) >= links[j].max_allocations
                for j in range(i)
            )
            if all_previous_full:
                chosen = link
                break
        if chosen:
            profile.credit_link_id = chosen.id
            link_counts[chosen.id] = link_counts.get(chosen.id, 0) + 1
            allocated += 1
            try:
                set_audit_session_vars()
                db.session.commit()
            except Exception:
                db.session.rollback()
                allocated -= 1
        else:
            skipped += 1
    return {'allocated': allocated, 'skipped_no_capacity': skipped}


def run_credit_allocation_stream():
    """
    Generator that runs allocation and yields SSE progress events.
    Yields: current, total, allocated, skipped_no_capacity; final event has done=True.
    """
    links = CreditLink.query.order_by(CreditLink.display_order).all()
    if not links:
        yield f"data: {json.dumps({'done': True, 'allocated': 0, 'skipped_no_capacity': 0, 'current': 0, 'total': 0})}\n\n"
        return
    from sqlalchemy import func as sql_func
    counts = db.session.query(
        SkillboostProfile.credit_link_id,
        sql_func.count(SkillboostProfile.email).label('cnt')
    ).filter(
        SkillboostProfile.credit_link_id.isnot(None)
    ).group_by(SkillboostProfile.credit_link_id).all()
    link_counts = {lid: c for lid, c in counts}
    allocated = 0
    skipped = 0
    pending = SkillboostProfile.query.filter(
        SkillboostProfile.valid == True,
        SkillboostProfile.credit_link_id.is_(None)
    ).order_by(SkillboostProfile.created_at, SkillboostProfile.email).all()
    total = len(pending)
    if total == 0:
        yield f"data: {json.dumps({'done': True, 'allocated': 0, 'skipped_no_capacity': 0, 'current': 0, 'total': 0})}\n\n"
        return
    current = 0
    for profile in pending:
        chosen = None
        for i, link in enumerate(links):
            n = link_counts.get(link.id, 0)
            if n >= link.max_allocations:
                continue
            all_previous_full = all(
                link_counts.get(links[j].id, 0) >= links[j].max_allocations
                for j in range(i)
            )
            if all_previous_full:
                chosen = link
                break
        if chosen:
            profile.credit_link_id = chosen.id
            link_counts[chosen.id] = link_counts.get(chosen.id, 0) + 1
            allocated += 1
            try:
                set_audit_session_vars()
                db.session.commit()
            except Exception:
                db.session.rollback()
                allocated -= 1
        else:
            skipped += 1
        current += 1
        yield f"data: {json.dumps({'current': current, 'total': total, 'allocated': allocated, 'skipped_no_capacity': skipped})}\n\n"
    yield f"data: {json.dumps({'done': True, 'allocated': allocated, 'skipped_no_capacity': skipped, 'current': current, 'total': total})}\n\n"


def _credits_query(search=None, sent_filter=None):
    """Build the verified credits query with optional search and sent filter.
    sent_filter: None (all), 'sent' (email_sent_at IS NOT NULL), 'not_sent' (allocated but email_sent_at IS NULL).
    """
    query = (
        db.session.query(SkillboostProfile, UserPII.name, CreditLink)
        .outerjoin(UserPII, SkillboostProfile.email == UserPII.email)
        .outerjoin(CreditLink, SkillboostProfile.credit_link_id == CreditLink.id)
        .filter(SkillboostProfile.valid == True)
        .order_by(SkillboostProfile.created_at.desc())
    )
    if search:
        query = query.filter(SkillboostProfile.email.ilike(f'%{search}%'))
    if sent_filter == 'sent':
        query = query.filter(SkillboostProfile.email_sent_at.isnot(None))
    elif sent_filter == 'not_sent':
        query = query.filter(
            SkillboostProfile.credit_link_id.isnot(None),
            SkillboostProfile.email_sent_at.is_(None)
        )
    return query


@bp.route('/credits', methods=['GET'])
@require_page_access('skill_lab_credits')
def get_skilllab_credits():
    """List Skill Lab / Skillboost profiles with pagination and optional search."""
    try:
        search = request.args.get('search', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)

        sent_filter = request.args.get('sent', '').strip() or None  # 'sent' | 'not_sent'
        query = _credits_query(search=search or None, sent_filter=sent_filter)
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        items = []
        for profile, name, link in pagination.items:
            d = profile.to_dict()
            d['name'] = name
            d['link_url'] = link.link_url if link else None
            d['link_display_order'] = link.display_order if link else None
            items.append(d)

        total_verified = SkillboostProfile.query.filter(SkillboostProfile.valid == True).count()
        total_allocated = SkillboostProfile.query.filter(
            SkillboostProfile.valid == True,
            SkillboostProfile.credit_link_id.isnot(None)
        ).count()
        total_not_sent = SkillboostProfile.query.filter(
            SkillboostProfile.valid == True,
            SkillboostProfile.credit_link_id.isnot(None),
            SkillboostProfile.email_sent_at.is_(None)
        ).count()
        total_sent = SkillboostProfile.query.filter(
            SkillboostProfile.valid == True,
            SkillboostProfile.credit_link_id.isnot(None),
            SkillboostProfile.email_sent_at.isnot(None)
        ).count()

        return jsonify({
            'credits': items,
            'total_verified': total_verified,
            'total_allocated': total_allocated,
            'total_not_sent': total_not_sent,
            'total_sent': total_sent,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev,
            }
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/credit-links', methods=['GET', 'POST'])
@require_page_access('skill_lab_credits')
def credit_links():
    """GET: list all credit links with current allocation count. POST: replace with up to 5 links (body: { links: [...] })."""
    try:
        if request.method == 'GET':
            from sqlalchemy import func
            links = CreditLink.query.order_by(CreditLink.display_order).all()
            counts = db.session.query(
                SkillboostProfile.credit_link_id,
                func.count(SkillboostProfile.email).label('cnt')
            ).filter(SkillboostProfile.credit_link_id.isnot(None)).group_by(SkillboostProfile.credit_link_id).all()
            count_by_id = {lid: c for lid, c in counts}
            items = []
            for link in links:
                d = link.to_dict()
                d['current_allocations'] = count_by_id.get(link.id, 0)
                # Show 3000 in UI when DB has legacy 2000 or 2500 (max raised to 3000)
                if d.get('max_allocations') in (2000, 2500):
                    d['max_allocations'] = 3000
                items.append(d)
            return jsonify({'credit_links': items}), 200
        # POST
        data = request.get_json()
        if not data or not isinstance(data, dict):
            return jsonify({'error': 'JSON body with "links" array required'}), 400
        links_data = data.get('links', [])
        if not isinstance(links_data, list):
            return jsonify({'error': '"links" must be an array'}), 400
        links_data = links_data[:5]
        set_audit_session_vars()
        CreditLink.query.delete()
        db.session.commit()
        for i, item in enumerate(links_data):
            link_url = (item.get('link_url') or '').strip() or None
            display_order = int(item.get('display_order', i + 1))
            max_allocations = int(item.get('max_allocations', 3000))
            link = CreditLink(
                link_url=link_url,
                display_order=display_order,
                max_allocations=max(1, min(max_allocations, 100000))
            )
            db.session.add(link)
        db.session.commit()
        links = CreditLink.query.order_by(CreditLink.display_order).all()
        return jsonify({'credit_links': [l.to_dict() for l in links]}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/allocate', methods=['POST'])
@require_page_access('skill_lab_credits')
def allocate_credits():
    """Run allocation for verified profiles without a credit link. Returns allocated and skipped counts.
    If ?stream=1, streams SSE progress events instead of JSON."""
    if request.args.get('stream') == '1':
        try:
            return Response(
                stream_with_context(run_credit_allocation_stream()),
                mimetype='text/event-stream',
                headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'},
            )
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    try:
        result = run_credit_allocation()
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/credits/export', methods=['GET'])
@require_page_access('skill_lab_credits')
def export_skilllab_credits():
    """Export verified Skill Lab credits as CSV; respects search filter."""
    try:
        search = request.args.get('search', '').strip() or None
        query = _credits_query(search=search)
        rows = query.all()

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['Name', 'Email', 'Profile link', 'Allocated link', 'Email sent', 'Status', 'Remarks', 'Updated'])
        for profile, name, link in rows:
            status = 'Verified' if profile.valid else ('Failed' if profile.remarks else 'Pending')
            link_label = ('Link %s' % link.display_order) if link else ''
            if link and link.link_url:
                link_label = link_label + ' ' + (link.link_url[:80] + '...' if len(link.link_url or '') > 80 else (link.link_url or ''))
            writer.writerow([
                (name or '').strip(),
                profile.email or '',
                profile.google_cloud_skills_boost_profile_link or '',
                link_label.strip(),
                profile.email_sent_at.isoformat() if profile.email_sent_at else '',
                status,
                (profile.remarks or '').strip(),
                profile.updated_at.isoformat() if profile.updated_at else '',
            ])
        csv_content = buf.getvalue()
        buf.close()

        filename = 'skill-lab-credits-' + datetime.utcnow().strftime('%Y-%m-%d') + '.csv'
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename="' + filename + '"'},
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/credits/export-not-sent', methods=['GET'])
@require_page_access('skill_lab_credits')
def export_not_sent():
    """Export verified, allocated credits that have not been marked as sent (for Sendy)."""
    try:
        query = (
            db.session.query(SkillboostProfile, UserPII.name, CreditLink)
            .outerjoin(UserPII, SkillboostProfile.email == UserPII.email)
            .outerjoin(CreditLink, SkillboostProfile.credit_link_id == CreditLink.id)
            .filter(SkillboostProfile.valid == True)
            .filter(SkillboostProfile.credit_link_id.isnot(None))
            .filter(SkillboostProfile.email_sent_at.is_(None))
            .order_by(CreditLink.display_order, SkillboostProfile.created_at)
        )
        rows = query.all()

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['Name', 'Email', 'Allocated link (URL)', 'Link #'])
        for profile, name, link in rows:
            link_url = (link.link_url or '').strip() if link else ''
            link_num = link.display_order if link else ''
            writer.writerow([
                (name or '').strip(),
                profile.email or '',
                link_url,
                link_num,
            ])
        csv_content = buf.getvalue()
        buf.close()

        filename = 'skill-lab-credits-not-sent-' + datetime.utcnow().strftime('%Y-%m-%d') + '.csv'
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename="' + filename + '"'},
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/credits/mark-sent', methods=['POST'])
@require_page_access('skill_lab_credits')
def mark_sent():
    """Mark credits as sent by uploading a list of emails (file or JSON)."""
    try:
        emails = set()
        if request.content_type and 'application/json' in request.content_type:
            data = request.get_json() or {}
            for e in (data.get('emails') or data.get('email_list') or []):
                if isinstance(e, str) and e.strip():
                    emails.add(e.strip().lower())
        elif request.files:
            file = request.files.get('file') or request.files.get('emails')
            if not file or not file.filename:
                return jsonify({'error': 'No file uploaded'}), 400
            import pandas as pd
            try:
                if file.filename.lower().endswith('.csv'):
                    df = pd.read_csv(file)
                elif file.filename.lower().endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(file)
                else:
                    # Plain text, one email per line
                    lines = file.read().decode('utf-8', errors='ignore').splitlines()
                    for line in lines:
                        e = line.strip()
                        if e and '@' in e:
                            emails.add(e.lower())
                    file.seek(0)
                    df = pd.DataFrame()
                if not df.empty:
                    for col in ['email', 'Email', 'EMAIL']:
                        if col in df.columns:
                            for v in df[col].dropna().astype(str).str.strip():
                                if v and '@' in v:
                                    emails.add(v.lower())
                            break
            except Exception as e:
                return jsonify({'error': 'Could not parse file: ' + str(e)}), 400
        else:
            return jsonify({'error': 'Upload a CSV/Excel file or send JSON { "emails": [...] }'}), 400

        if not emails:
            return jsonify({'updated': 0, 'message': 'No valid emails found'}), 200

        set_audit_session_vars()
        now = datetime.utcnow()
        updated = db.session.query(SkillboostProfile).filter(
            SkillboostProfile.email.in_(emails),
            SkillboostProfile.credit_link_id.isnot(None)
        ).update(
            {SkillboostProfile.email_sent_at: now},
            synchronize_session=False
        )
        db.session.commit()
        return jsonify({'updated': updated}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
