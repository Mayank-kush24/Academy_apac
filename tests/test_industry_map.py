"""Industry rollup used by the Cohort 2/3 User Segmentation chart."""
from server.utils.industry_map import (
    accumulate_industry_buckets,
    canonical_industry,
    industry_buckets_to_chart,
    industry_chart_label,
)


def test_domain_names_roll_up_to_industry():
    assert canonical_industry('Information Technology') == 'Technology'
    assert canonical_industry('Software development') == 'Technology'
    assert canonical_industry('Artificial Intelligence') == 'Data & AI'
    assert canonical_industry('Data Analytics') == 'Data & AI'
    assert canonical_industry('Marketing & Advertising') == 'Business & Commerce'
    assert canonical_industry('E-Commerce') == 'Business & Commerce'
    assert canonical_industry('Education & Skill Development') == 'Education & Research'


def test_already_canonical_industry_is_unchanged():
    assert canonical_industry('Technology') == 'Technology'
    assert canonical_industry('Data & AI') == 'Data & AI'


def test_other_and_blank_are_dropped():
    assert canonical_industry('Other') == ''
    assert canonical_industry('other') == ''
    assert canonical_industry('') == ''
    assert canonical_industry(None) == ''


def test_technology_display_label():
    assert industry_chart_label('Technology') == 'Information Technology'
    assert industry_chart_label('Data & AI') == 'Data & AI'


def test_segmentation_chart_rolls_domains_into_industries():
    buckets = {}
    accumulate_industry_buckets(buckets, 'Information Technology', 'Information Technology', 2000)
    accumulate_industry_buckets(buckets, 'Software development', 'Software development', 1500)
    accumulate_industry_buckets(buckets, None, 'Artificial Intelligence', 750)
    accumulate_industry_buckets(buckets, 'Other', 'Other', 480)
    accumulate_industry_buckets(buckets, 'Marketing & Advertising', 'Marketing & Advertising', 550)

    chart = industry_buckets_to_chart(buckets)
    labels = [row['label'] for row in chart]
    by_label = {row['label']: row for row in chart}

    assert 'Other' not in labels
    assert by_label['Information Technology']['value'] == 3500
    assert by_label['Data & AI']['value'] == 750
    assert by_label['Business & Commerce']['value'] == 550
    domain_labels = {d['label'] for d in by_label['Information Technology']['domains']}
    assert domain_labels == {'Information Technology', 'Software development'}
