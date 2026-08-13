"""Sheet-detection registry tests (Action Center imports)."""
from server.utils.excel_parser import SHEET_DETECTORS, _match_detector


def _missing_critical_for_workbook(sheet_names, cohort_id):
    matched = set()
    for name in sheet_names:
        det = _match_detector(name, cohort_id=cohort_id)
        if det is None:
            continue
        det_key = (det.module, det.track, det.lab)
        if det_key in matched:
            continue
        matched.add(det_key)

    missing = []
    for det in SHEET_DETECTORS:
        if not det.is_critical_for_cohort(cohort_id):
            continue
        det_key = (det.module, det.track, det.lab)
        if det_key in matched:
            continue
        missing.append(det.label)
    return missing


def test_cohort2_partial_export_does_not_require_cohort1_modules():
    """Cohort 2 partial Action Center exports should not flag Cohort 1 MCQ/lab sheets."""
    names = [
        "1.Share your Google Skills Pub",
        "2.Professional Track 1 Codelab",
        "3.Student Track Codelab Buildi",
        "4.Codelab Credits Request Form",
        "5.Challenge 2 System design th",
        "6.Professional Track 2 Codelab",
    ]
    missing = _missing_critical_for_workbook(names, cohort_id=2)
    assert "Main MCQ Track 1" not in missing
    assert "Optional MCQ Track 1" not in missing
    assert "Lab Completion 1 Track 1" not in missing
    assert "Project Submission Track 1" not in missing
    assert len(missing) == 2
    assert "Professional Track 3 Codelab" in missing
    assert "Cohort 2 Optional MCQ" in missing


def test_student_track_detector_allows_no_space_in_tab_name():
    det = _match_detector("3.StudentTrack Codelab Buildi", cohort_id=2)
    assert det is not None
    assert det.label == "Student Track Codelab Building"
    assert det.track is None  # track_number=3 assigned at import, not on detector


def test_codelab_upload_file_column_maps_to_screenshot():
    from server.utils.excel_parser import _map_submission_columns, _codelab_default_problem_statement, _codelab_sheet_track_number

    mapping = _map_submission_columns(["Leader Email", "Upload File", "Team Name"])
    assert "Upload File" in mapping
    assert mapping["Upload File"] == "upload_screenshot"
    assert _codelab_sheet_track_number("3.Student Track Codelab Buildi", None) == 3
    assert _codelab_default_problem_statement("2.Professional Track 1 Codelab", 1) == "Professional Track 1 Codelab"
    assert _codelab_default_problem_statement("3.Student Track Codelab Buildi", 3) == "Student Track Codelab"
