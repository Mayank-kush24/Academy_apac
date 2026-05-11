"""
Map declarative participant models to cohort-prefixed physical tables (public.cohort_2_user_pii, …).

Uses SQLAlchemy reflection so FK metadata matches the database. Cohort 1 (empty prefix)
returns the original model class unchanged.

Import workers that run in a background thread must call apply_cohort_globals() inside
app.app_context() so participant_model() sees the correct prefix.
"""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple, Type, TypeVar

from flask import g, has_app_context, has_request_context
from sqlalchemy import Table, inspect as sa_inspect

from server.models import db

T = TypeVar("T")

# (base model __name__, physical table name) -> reflected model class
_MODEL_CACHE: dict[tuple[str, str], type] = {}

_PREFIX_RE = re.compile(r"^cohort_[0-9]+_$")


def snapshot_cohort_globals() -> Tuple[str, Optional[int]]:
    """Capture g.table_prefix and g.cohort_id for use in worker threads."""
    if not has_request_context():
        return "", None
    prefix = getattr(g, "table_prefix", None)
    prefix = (prefix or "") if prefix is not None else ""
    cid = getattr(g, "cohort_id", None)
    return prefix, cid if isinstance(cid, int) else None


def apply_cohort_globals(table_prefix: str, cohort_id: Optional[int]) -> None:
    """Restore cohort context on flask.g (call inside app.app_context in workers)."""
    g.table_prefix = table_prefix or ""
    if cohort_id is not None:
        g.cohort_id = cohort_id


def _active_prefix() -> str:
    # Use app context so background import threads see g.table_prefix after apply_cohort_globals().
    if not has_app_context():
        return ""
    p = getattr(g, "table_prefix", None)
    if p is None:
        return ""
    s = str(p)
    if s and not _PREFIX_RE.match(s):
        return ""
    return s


def participant_model(base_cls: Type[T]) -> Type[T]:
    """
    Return an ORM class for the same columns as base_cls, bound to the cohort table.

    - Prefix \"\": base_cls (e.g. user_pii).
    - Prefix \"cohort_2_\": reflected cohort_2_user_pii, etc.
    """
    prefix = _active_prefix()
    if not prefix:
        return base_cls

    tname = f"{prefix}{base_cls.__tablename__}"
    key = (base_cls.__name__, tname)
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]

    insp = sa_inspect(db.engine)
    public_tables = set(insp.get_table_names(schema="public"))
    public_views = set(insp.get_view_names(schema="public"))
    if tname not in public_tables and tname not in public_views:
        raise RuntimeError(
            f"Participant table or view '{tname}' does not exist. Run the cohort migration "
            f"(e.g. server/migrations/create_cohort2_tables.py) before using this cohort."
        )

    tbl = Table(tname, db.metadata, autoload_with=db.engine, extend_existing=True)
    cls_name = f"_Dyn{base_cls.__name__}_{prefix.rstrip('_').title().replace('_', '')}"
    cls_attrs: dict = {"__table__": tbl, "__module__": __name__}
    # Views (e.g. *_user_pii_combined) often reflect without PK metadata; SQLAlchemy still needs one.
    if not tbl.primary_key or len(tbl.primary_key) == 0:
        if "id" in tbl.c:
            cls_attrs["__mapper_args__"] = {"primary_key": [tbl.c.id]}
        else:
            raise RuntimeError(
                f"Reflected cohort relation '{tname}' has no primary key metadata and no 'id' column; "
                f"cannot map ORM model {base_cls.__name__}."
            )
    # Copy instance methods from base_cls (e.g. to_dict) so reflected rows behave identically.
    for _attr in ("to_dict", "to_brief_dict", "to_summary_dict"):
        if hasattr(base_cls, _attr):
            cls_attrs[_attr] = getattr(base_cls, _attr)
    Dyn = type(cls_name, (db.Model,), cls_attrs)
    _MODEL_CACHE[key] = Dyn
    return Dyn
