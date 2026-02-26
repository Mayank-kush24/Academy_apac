"""
Audit / master_logs API (admin only)
"""
from flask import Blueprint, request, jsonify
from sqlalchemy import text
from server.models import db
from server.utils.auth import get_current_user
from server.utils.permissions import require_role
from server.utils.date_format import format_datetime_utc

bp = Blueprint('audit', __name__)


@bp.route('/master_logs', methods=['GET'])
@require_role('admin')
def get_master_logs():
    """
    Return recent rows from master_logs (admin only).
    Query params: limit (default 50), table_name, changed_by, operation_type.
    """
    limit = min(int(request.args.get('limit', 50)), 500)
    table_name = request.args.get('table_name')
    changed_by = request.args.get('changed_by')
    operation_type = request.args.get('operation_type')
    try:
        q = """
            SELECT log_id, table_name, operation_type, record_identifier,
                   old_values, new_values, changed_by, timestamp, additional_info
            FROM master_logs
            WHERE 1=1
        """
        params = {"limit": limit}
        if table_name:
            q += " AND table_name = :table_name"
            params["table_name"] = table_name
        if changed_by:
            q += " AND changed_by = :changed_by"
            params["changed_by"] = changed_by
        if operation_type:
            q += " AND operation_type = :operation_type"
            params["operation_type"] = operation_type
        q += " ORDER BY log_id DESC LIMIT :limit"
        result = db.session.execute(text(q), params)
        rows = result.fetchall()
        keys = list(result.keys()) if rows else []
        logs = [dict(zip(keys, row)) for row in rows]
        for log in logs:
            if log.get("timestamp"):
                log["timestamp"] = format_datetime_utc(log["timestamp"])
        return jsonify({"logs": logs}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
