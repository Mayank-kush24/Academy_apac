"""
Skill Lab credits page and API (Skill Lab / Skillboost profiles list)
"""
import csv
import io
import json
from datetime import datetime
from flask import Blueprint, g, request, jsonify, Response, stream_with_context
from sqlalchemy import func
from sqlalchemy.orm import aliased
from server.models import db, SkillboostProfile, UserPIICombined, CreditLink
from server.utils.auth import get_current_user
from server.utils.cohort_participant_models import participant_model
from server.utils.permissions import require_page_access
from server.utils.audit import set_audit_session_vars
from server.utils.import_file_archive import archive_upload, ImportArchiveError

bp = Blueprint('skilllab', __name__)


def _distinct_email_credit_counts(SB):
    """Count how many distinct emails hold each credit_link_id (one credit per person)."""
    return (
        db.session.query(
            SB.credit_link_id,
            func.count(func.distinct(SB.email)).label('cnt'),
        )
        .filter(SB.credit_link_id.isnot(None))
        .group_by(SB.credit_link_id)
        .all()
    )


def _pending_allocation_profiles(SB):
    """
    One profile row per email: prefer rows that already have a peer allocated/sent,
    else newest by updated_at. Same ordering as credits list dedupe.
    """
    allocated_emails = {
        r[0]
        for r in db.session.query(SB.email)
        .filter(SB.valid == True, SB.credit_link_id.isnot(None))
        .distinct()
        .all()
    }
    rows = (
        SB.query.filter(SB.valid == True, SB.credit_link_id.is_(None))
        .order_by(
            SB.email,
            SB.email_sent_at.is_(None).asc(),
            SB.credit_link_id.is_(None).asc(),
            SB.updated_at.desc(),
        )
        .all()
    )
    chosen_by_email = {}
    for p in rows:
        if p.email in allocated_emails:
            continue
        if p.email not in chosen_by_email:
            chosen_by_email[p.email] = p
    return list(chosen_by_email.values())


def run_credit_allocation():
    """
    Allocate credit links to verified skillboost_profiles that don't have one.
    Uses links in display_order; each link gets up to max_allocations (e.g. 3000).
    At most one allocation per distinct email (PK is email+profile link; imports can
    create multiple rows when the public profile URL changes).
    Returns dict: allocated (int), skipped_no_capacity (int).
    """
    CL = participant_model(CreditLink)
    SB = participant_model(SkillboostProfile)
    links = CL.query.order_by(CL.display_order).all()
    if not links:
        return {'allocated': 0, 'skipped_no_capacity': 0}
    counts_rows = _distinct_email_credit_counts(SB)
    link_counts = {lid: int(c) for lid, c in counts_rows}
    allocated = 0
    skipped = 0
    pending = sorted(
        _pending_allocation_profiles(SB),
        key=lambda p: (p.created_at or datetime.utcnow(), p.email or ''),
    )
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
    CL = participant_model(CreditLink)
    SB = participant_model(SkillboostProfile)
    links = CL.query.order_by(CL.display_order).all()
    if not links:
        yield f"data: {json.dumps({'done': True, 'allocated': 0, 'skipped_no_capacity': 0, 'current': 0, 'total': 0})}\n\n"
        return
    counts_rows = _distinct_email_credit_counts(SB)
    link_counts = {lid: int(c) for lid, c in counts_rows}
    allocated = 0
    skipped = 0
    pending = sorted(
        _pending_allocation_profiles(SB),
        key=lambda p: (p.created_at or datetime.utcnow(), p.email or ''),
    )
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


def _credits_ranked_subquery():
    """
    Row-number verified profiles per email for credits UI.
    Prefer rows already marked sent, then any allocated credit, then newest updated_at.
    (Table PK is email + profile link; Action Center re-imports can add multiple links per email.)
    """
    SB = participant_model(SkillboostProfile)
    rn = func.row_number().over(
        partition_by=SB.email,
        order_by=(
            SB.email_sent_at.is_(None).asc(),
            SB.credit_link_id.is_(None).asc(),
            SB.updated_at.desc(),
        ),
    ).label('sb_rn')
    return (
        db.session.query(SB, rn)
        .filter(SB.valid == True)
        .subquery('sb_credits_ranked')
    )


def _credits_canonical_stats():
    """
    Aggregate counts on the same canonical row per email as the list / CSV export
    (row_number partition in _credits_ranked_subquery). Avoids counting duplicate
    profile-link rows where the canonical row is already sent but another row is not.
    """
    SB = participant_model(SkillboostProfile)
    ranked = _credits_ranked_subquery()
    SB_row = aliased(SB, ranked)
    base = (
        db.session.query(SB_row)
        .select_from(SB_row)
        .filter(ranked.c.sb_rn == 1)
    )
    return {
        'total_verified': base.count(),
        'total_allocated': base.filter(SB_row.credit_link_id.isnot(None)).count(),
        'total_not_sent': base.filter(
            SB_row.credit_link_id.isnot(None),
            SB_row.email_sent_at.is_(None),
        ).count(),
        'total_sent': base.filter(
            SB_row.credit_link_id.isnot(None),
            SB_row.email_sent_at.isnot(None),
        ).count(),
    }


def _credits_query(search=None, sent_filter=None):
    """Build the verified credits query with optional search and sent filter.
    One row per distinct email (canonical profile row for credits).
    sent_filter: None (all), 'sent' (email_sent_at IS NOT NULL), 'not_sent' (allocated but email_sent_at IS NULL).
    """
    SB = participant_model(SkillboostProfile)
    PII = participant_model(UserPIICombined)
    CL = participant_model(CreditLink)
    ranked = _credits_ranked_subquery()
    SB_row = aliased(SB, ranked)
    query = (
        db.session.query(SB_row, PII.name, CL)
        .select_from(SB_row)
        .outerjoin(PII, SB_row.email == PII.email)
        .outerjoin(CL, SB_row.credit_link_id == CL.id)
        .filter(ranked.c.sb_rn == 1)
        .order_by(SB_row.created_at.desc())
    )
    if search:
        query = query.filter(SB_row.email.ilike(f'%{search}%'))
    if sent_filter == 'sent':
        query = query.filter(SB_row.email_sent_at.isnot(None))
    elif sent_filter == 'not_sent':
        query = query.filter(
            SB_row.credit_link_id.isnot(None),
            SB_row.email_sent_at.is_(None)
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

        stats = _credits_canonical_stats()
        total_verified = stats['total_verified']
        total_allocated = stats['total_allocated']
        total_not_sent = stats['total_not_sent']
        total_sent = stats['total_sent']

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
        CL = participant_model(CreditLink)
        SB = participant_model(SkillboostProfile)
        if request.method == 'GET':
            links = CL.query.order_by(CL.display_order).all()
            counts = _distinct_email_credit_counts(SB)
            count_by_id = {lid: int(c) for lid, c in counts}
            items = []
            for link in links:
                d = link.to_dict()
                d['current_allocations'] = count_by_id.get(link.id, 0)
                # Legacy: Cohort 1 UI historically showed 3000 when DB stored 2000/2500.
                if getattr(g, "cohort_id", None) == 1 and d.get('max_allocations') in (2000, 2500):
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
        CL.query.delete()
        db.session.commit()
        for i, item in enumerate(links_data):
            link_url = (item.get('link_url') or '').strip() or None
            display_order = int(item.get('display_order', i + 1))
            max_allocations = int(item.get('max_allocations', 3000))
            link = CL(
                link_url=link_url,
                display_order=display_order,
                max_allocations=max(1, min(max_allocations, 100000))
            )
            db.session.add(link)
        db.session.commit()
        links = CL.query.order_by(CL.display_order).all()
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
        rows = _credits_query(search=None, sent_filter='not_sent').all()
        rows.sort(key=lambda row: (
            (row[2].display_order or 0) if row[2] else 999,
            row[0].created_at.timestamp() if getattr(row[0], 'created_at', None) else 0,
        ))

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
                    try:
                        archive_path = archive_upload(file, kind="skilllab_mark_sent")
                    except ImportArchiveError as e:
                        return jsonify({'error': str(e)}), 503
                    df = pd.read_csv(archive_path)
                elif file.filename.lower().endswith(('.xlsx', '.xls')):
                    try:
                        archive_path = archive_upload(file, kind="skilllab_mark_sent")
                    except ImportArchiveError as e:
                        return jsonify({'error': str(e)}), 503
                    df = pd.read_excel(archive_path)
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

        SB = participant_model(SkillboostProfile)
        set_audit_session_vars()
        now = datetime.utcnow()
        updated = db.session.query(SB).filter(
            SB.email.in_(emails),
            SB.credit_link_id.isnot(None)
        ).update(
            {SB.email_sent_at: now},
            synchronize_session=False
        )
        db.session.commit()
        demoted = 0
        try:
            from server.utils.skillboost_profile_reconcile import reconcile_skillboost_for_emails

            demoted = reconcile_skillboost_for_emails(emails)
        except Exception:
            try:
                from flask import current_app

                current_app.logger.warning(
                    'skillboost_profile reconcile after mark-sent failed',
                    exc_info=True,
                )
            except Exception:
                pass
        return jsonify({'updated': updated, 'demoted_duplicate_rows': demoted}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/credits/reconcile-duplicates', methods=['POST'])
@require_page_access('skill_lab_credits')
def credits_reconcile_duplicates():
    """
    One-off: enforce one canonical Skillboost row per email for credits
    (dispatch winner + trim >2 valid-without-sent). Safe to run multiple times.
    """
    try:
        from server.utils.skillboost_profile_reconcile import (
            reconcile_skillboost_emails_with_multiple_rows,
        )

        set_audit_session_vars()
        demoted = reconcile_skillboost_emails_with_multiple_rows()
        return jsonify({
            'demoted_duplicate_rows': demoted,
            'message': 'Reconciled emails that had more than one profile row.',
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
