"""Unit tests for H2S UTS client helpers and module classification."""
from datetime import datetime, timedelta, timezone

from server.utils.h2s_uts_client import (
    REGISTRATION_PAGE_SIZE,
    H2SUtsError,
    extract_modules,
    extract_records,
    module_id_of,
    module_name_of,
)
from server.utils.h2s_uts_sync import (
    _classify_module,
    _flatten_row,
    fetch_reachable_registrations,
    find_earliest_safe_registration_start,
    is_uts_objectid_convert_error,
    objectid_convert_bad_value,
    parse_uts_iso,
    uts_iso,
)


def test_extract_records_list():
    rows = extract_records([{"email": "a@b.com"}, {"email": "c@d.com"}])
    assert len(rows) == 2


def test_extract_records_nested():
    rows = extract_records({"data": {"rows": [{"email": "a@b.com"}]}})
    assert len(rows) == 1
    assert rows[0]["email"] == "a@b.com"


def test_extract_records_tabular_uts():
    """Hack2Skill UTS returns { data: [[headers], [row], ...] }."""
    payload = {
        "success": True,
        "data": [
            ["Timestamp", "Full Name", "Email", "Country"],
            ["2026-01-01T00:00:00.000Z", "Ada", "ada@x.com", "India"],
            ["2026-01-02T00:00:00.000Z", "Bob", "bob@x.com", "India"],
        ],
    }
    rows = extract_records(payload)
    assert len(rows) == 2
    assert rows[0]["Email"] == "ada@x.com"
    assert rows[0]["Full Name"] == "Ada"
    assert rows[1]["Country"] == "India"


def test_extract_modules():
    mods = extract_modules({"modules": [{"id": "m1", "name": "Skill Lab Submission"}]})
    assert len(mods) == 1
    assert module_id_of(mods[0]) == "m1"
    assert "Skill Lab" in module_name_of(mods[0])


def test_extract_modules_from_data_with_id():
    mods = extract_modules({
        "success": True,
        "data": [{"_id": "abc", "title": "Ideathon Phase"}],
    })
    assert len(mods) == 1
    assert module_id_of(mods[0]) == "abc"
    assert module_name_of(mods[0]) == "Ideathon Phase"


def test_classify_modules():
    assert _classify_module("Google Skills Lab Submission")[0] == "skilllab_submission"
    assert _classify_module("Code Lab Submission Track 2") == ("codelab_submission", 2)
    assert _classify_module("MCQ Optional Track 4") == ("optional_mcq", 4)
    assert _classify_module("Share your Google Skills Boost profile")[0] == "skillboost_profile"
    assert _classify_module("MCQ Track 1")[0] == "skip"
    assert _classify_module("Project Submission Track 1")[0] == "skip"


def test_flatten_row_formdata():
    flat = _flatten_row({
        "email": "x@y.com",
        "formData": {"Leader Email": "x@y.com", "Team Name": "T1"},
    })
    assert flat["email"] == "x@y.com"
    assert flat["Leader Email"] == "x@y.com"
    assert flat["Team Name"] == "T1"


_FTII_ERR = (
    "UTS API HTTP 500 for /api/v1/event/apac-genaiacademy-c3/uts: "
    '{"message":"Executor error during getMore :: caused by :: '
    "Failed to parse objectId 'FTII' in $convert with no onError value: "
    'Invalid string length for parsing to OID, expected 24 but found 4","success":false}'
)


class _FakePoisonedUts:
    """Fails any fetch whose start is None or earlier than the first safe instant."""

    def __init__(self, first_safe):
        self.first_safe = first_safe

    def fetch_registrations(self, start=None):
        if start is None or parse_uts_iso(start) < self.first_safe:
            raise H2SUtsError(_FTII_ERR, status_code=500, body=_FTII_ERR)
        return {"data": []}


def test_objectid_convert_error_detection():
    err = H2SUtsError(_FTII_ERR, status_code=500)
    assert is_uts_objectid_convert_error(err)
    assert objectid_convert_bad_value(err) == "FTII"
    assert not is_uts_objectid_convert_error(H2SUtsError("gateway timeout"))
    assert objectid_convert_bad_value(H2SUtsError("gateway timeout")) is None


def test_find_earliest_safe_registration_start():
    first_safe = datetime(2026, 8, 14, 7, 29, 1, tzinfo=timezone.utc)
    client = _FakePoisonedUts(first_safe)
    lo = datetime(2026, 8, 13, 23, 47, 0, tzinfo=timezone.utc)
    hi = datetime(2026, 8, 16, 0, 0, 0, tzinfo=timezone.utc)
    found = find_earliest_safe_registration_start(client, lo, hi)
    assert uts_iso(found) == uts_iso(first_safe)


def test_find_earliest_safe_start_when_lo_already_works():
    first_safe = datetime(2026, 8, 14, 7, 29, 1, tzinfo=timezone.utc)
    client = _FakePoisonedUts(first_safe)
    found = find_earliest_safe_registration_start(client, first_safe, first_safe)
    assert found == first_safe


_IST = timedelta(hours=5, minutes=30)
_SPACING = timedelta(seconds=60)


class _SlidingUts:
    """
    Models the UTS registrations endpoint.

    Serves ``total`` rows ending at roughly now, capped at REGISTRATION_PAGE_SIZE, where
    the cap is a window anchored at ``start``. ``start`` filters on UTC while the row
    ``Timestamp`` is rendered in IST, as upstream does. A window that spans the row index
    in ``poison`` fails, so early anchors succeed and later ones do not.
    """

    def __init__(self, total, poison=None):
        self.total = total
        self.poison = poison
        self.starts = []
        self.epoch = datetime.now(timezone.utc) - total * _SPACING

    def _utc_of(self, i):
        return self.epoch + i * _SPACING

    def _row(self, i):
        return {"Email": f"u{i}@x.com", "Timestamp": uts_iso(self._utc_of(i) + _IST)}

    def _index_for(self, start):
        if start is None:
            return 0
        delta = (parse_uts_iso(start) - self.epoch).total_seconds()
        idx = -(-delta // _SPACING.total_seconds())  # first row at or after `start`
        return int(max(0, min(idx, self.total)))

    def fetch_registrations(self, start=None):
        self.starts.append(start)
        lo = self._index_for(start)
        hi = min(lo + REGISTRATION_PAGE_SIZE, self.total)
        if self.poison is not None and lo <= self.poison < hi:
            raise H2SUtsError(_FTII_ERR, status_code=500, body=_FTII_ERR)
        return {"data": [self._row(i) for i in range(lo, hi)]}


def test_fetch_reachable_registrations_slides_past_the_cap():
    client = _SlidingUts(REGISTRATION_PAGE_SIZE + 1234)
    records, gaps = fetch_reachable_registrations(client, None)
    assert len(records) == REGISTRATION_PAGE_SIZE + 1234
    assert gaps == []


def test_fetch_reachable_registrations_stops_when_start_is_ignored():
    class _IgnoresStart(_SlidingUts):
        def fetch_registrations(self, start=None):
            self.starts.append(start)
            return {"data": [self._row(i) for i in range(REGISTRATION_PAGE_SIZE)]}

    client = _IgnoresStart(REGISTRATION_PAGE_SIZE * 3)
    records, gaps = fetch_reachable_registrations(client, None)
    assert len(records) == REGISTRATION_PAGE_SIZE
    assert gaps == []
    assert len(client.starts) == 2


def test_fetch_reachable_registrations_squeezes_up_to_poisoned_row():
    """Everything is recovered except the poisoned row itself."""
    total = REGISTRATION_PAGE_SIZE + 9000
    poison = REGISTRATION_PAGE_SIZE + 6000
    client = _SlidingUts(total, poison=poison)

    records, gaps = fetch_reachable_registrations(client, None)
    got = {r["Email"] for r in records}

    assert f"u{poison}@x.com" not in got
    assert got == {f"u{i}@x.com" for i in range(total)} - {f"u{poison}@x.com"}
    assert len(gaps) == 1
    assert gaps[0]["bad"] == "FTII"


def test_fetch_reachable_registrations_caches_discovered_boundaries():
    total = REGISTRATION_PAGE_SIZE + 9000
    poison = REGISTRATION_PAGE_SIZE + 6000
    hints = {}

    first = _SlidingUts(total, poison=poison)
    records, _ = fetch_reachable_registrations(first, None, hints=hints)
    assert "safe_start" in hints and "window_start" in hints

    second = _SlidingUts(total, poison=poison)
    cached, gaps = fetch_reachable_registrations(second, None, hints=dict(hints))
    assert {r["Email"] for r in cached} == {r["Email"] for r in records}
    assert len(gaps) == 1
    # Reusing the cached boundaries avoids re-running both searches.
    assert len(second.starts) < len(first.starts)


def test_fetch_reachable_registrations_deduplicates_overlapping_windows():
    client = _SlidingUts(REGISTRATION_PAGE_SIZE + 10)
    records, _ = fetch_reachable_registrations(client, None)
    assert len(records) == len({r["Email"] for r in records})

