"""Cohort config helpers used by the dashboard Registration Trend chart."""
from datetime import date

from server.cohort_config import get_registration_trend_start


def test_cohort3_trend_starts_mid_july():
    assert get_registration_trend_start("cohort_3_") == date(2026, 7, 15)


def test_cohort1_and_2_trend_start_is_jan_15():
    today = date(2026, 8, 26)
    assert get_registration_trend_start("", today=today) == date(2026, 1, 15)
    assert get_registration_trend_start("cohort_2_", today=today) == date(2026, 1, 15)


def test_jan_15_rolls_to_previous_year_before_that_date():
    assert get_registration_trend_start("", today=date(2026, 1, 1)) == date(2025, 1, 15)
