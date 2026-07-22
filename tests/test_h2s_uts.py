"""Unit tests for H2S UTS client helpers and module classification."""
from server.utils.h2s_uts_client import extract_modules, extract_records, module_id_of, module_name_of
from server.utils.h2s_uts_sync import _classify_module, _flatten_row


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
