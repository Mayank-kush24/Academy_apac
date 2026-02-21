"""
Automatic activity logging for database changes.
Registers SQLAlchemy event listeners to log create/update/delete on tracked models.
Uses the same session's connection so logs are written in the same transaction.
"""
from datetime import datetime, date
from uuid import uuid4, UUID
from sqlalchemy import event, insert
from sqlalchemy.orm import inspect as sa_inspect, object_session


def _serialize_value(value):
    """Make a value JSON-serializable."""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return value


def _model_to_snapshot(obj):
    """Convert a model instance to a JSON-serializable snapshot (exclude sensitive fields)."""
    if obj is None:
        return None
    skip = {'password_hash'}  # never log passwords
    try:
        d = {}
        for col in obj.__table__.columns:
            if col.name in skip:
                continue
            val = getattr(obj, col.name, None)
            d[col.name] = _serialize_value(val)
        return d
    except Exception:
        return None


def _get_entity_info(mapper, instance):
    """Return (entity_type, entity_id) for a model instance."""
    entity_type = mapper.class_.__tablename__
    pk = getattr(instance, mapper.primary_key[0].key, None)
    entity_id = str(pk) if pk is not None else None
    return entity_type, entity_id


def _get_actor_user_id():
    """Get current app user id if in request context."""
    try:
        from flask import has_request_context
        if has_request_context():
            from server.utils.auth import get_current_user
            user = get_current_user()
            return user.id if user else None
    except Exception:
        pass
    return None


def _write_log(connection_or_session, action, entity_type, entity_id, changes=None, snapshot_before=None, snapshot_after=None, summary=None):
    """Insert an activity log row in the same transaction (connection or session)."""
    if entity_type == 'activity_logs':
        return
    try:
        from server.models import ActivityLog
        actor_id = _get_actor_user_id()
        table = ActivityLog.__table__
        stmt = insert(table).values(
            id=uuid4(),
            created_at=datetime.utcnow(),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id or '',
            actor_user_id=actor_id,
            changes=changes,
            snapshot_before=snapshot_before,
            snapshot_after=snapshot_after,
            summary=(summary[:500] if (summary and len(summary) > 500) else summary),
        )
        connection_or_session.execute(stmt)
    except Exception as e:
        import traceback
        traceback.print_exc()


def _after_insert(mapper, connection, target):
    """Log after a record is inserted."""
    session = object_session(target)
    if session is None:
        return
    entity_type, entity_id = _get_entity_info(mapper, target)
    snapshot = _model_to_snapshot(target)
    summary = f"Record created in {entity_type}"
    _write_log(
        session,
        action='create',
        entity_type=entity_type,
        entity_id=entity_id,
        snapshot_after=snapshot,
        summary=summary,
    )


def _after_update(mapper, connection, target):
    """Log after a record is updated. Capture changed fields and old/new values."""
    session = object_session(target)
    if session is None:
        return
    entity_type, entity_id = _get_entity_info(mapper, target)
    skip = {'password_hash', 'updated_at'}
    insp = sa_inspect(target)
    changes = []
    snapshot_before = {}
    for attr in insp.attrs:
        if not attr.history.has_changes():
            continue
        key = attr.key
        if key in skip:
            continue
        hist = attr.history
        old_val = hist.deleted[0] if hist.deleted else None
        new_val = hist.added[0] if hist.added else getattr(target, key, None)
        changes.append({
            'field': key,
            'old_value': _serialize_value(old_val),
            'new_value': _serialize_value(new_val),
        })
        snapshot_before[key] = _serialize_value(old_val)
    if not changes:
        return
    snapshot_after = _model_to_snapshot(target)
    summary = f"Record updated in {entity_type}: {', '.join(c['field'] for c in changes)}"
    _write_log(
        session,
        action='update',
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
        snapshot_before=snapshot_before if snapshot_before else None,
        snapshot_after=snapshot_after,
        summary=summary,
    )


def _after_delete(mapper, connection, target):
    """Log after a record is deleted. Use connection (object may be detached)."""
    entity_type, entity_id = _get_entity_info(mapper, target)
    snapshot = _model_to_snapshot(target)
    summary = f"Record deleted from {entity_type}"
    _write_log(
        connection,
        action='delete',
        entity_type=entity_type,
        entity_id=entity_id,
        snapshot_before=snapshot,
        summary=summary,
    )


def register_activity_listeners():
    """Register SQLAlchemy event listeners for UserPII, User, SkillLabSubmission, OptionalMcqVerification, OptionalMcqResponse (ActivityLog is skipped)."""
    from server.models import UserPII, User, SkillLabSubmission, OptionalMcqVerification, OptionalMcqResponse
    for model in (UserPII, User, SkillLabSubmission, OptionalMcqVerification, OptionalMcqResponse):
        event.listen(model, 'after_insert', _after_insert)
        event.listen(model, 'after_update', _after_update)
        event.listen(model, 'after_delete', _after_delete)
