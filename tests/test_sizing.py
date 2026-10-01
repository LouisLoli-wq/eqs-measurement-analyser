"""The recommender ranks; it never decides."""

import pandas as pd

from src import sizing


def _detail(sizes, direct_share, load_share):
    idx = ["Consumption kWh/year", "PV max kWh/year", "PV direct kWh/year",
           "PV direct share %", "PV maximum share %"]
    data = {}
    for i, s in enumerate(sizes):
        data["%s kWp" % s] = [100000, 40000, 30000,
                              direct_share[i], load_share[i]]
    return pd.DataFrame(data, index=idx)


def test_thresholds_are_unapproved_by_default():
    assert sizing.THRESHOLDS_APPROVED is False


def test_every_size_is_assessed():
    detail = _detail([10, 20, 30], [95, 90, 60], [20, 40, 80])
    result = sizing.assess(detail, [10, 20, 30])
    assert len(result.assessments) == 3
    assert all(a.reasons for a in result.assessments)


def test_largest_size_inside_both_thresholds_is_preferred():
    detail = _detail([10, 20, 30], [95, 90, 60], [20, 40, 80])
    result = sizing.assess(detail, [10, 20, 30])
    assert result.preferred_kwp == 20


def test_falls_back_to_best_direct_use_when_none_qualify():
    detail = _detail([10, 20], [70, 50], [90, 95])
    result = sizing.assess(detail, [10, 20])
    assert result.preferred_kwp == 10


def test_measured_and_assumed_values_are_kept_apart():
    detail = _detail([10], [95], [20])
    result = sizing.assess(detail, [10], eta_pv=0.82, offset=0.1)
    assert "Annual consumption [kWh]" in result.measured_inputs
    assert result.user_assumptions["System efficiency EtaPV"] == 0.82
    assert "EtaPV" not in " ".join(result.measured_inputs)


def test_placeholder_caveat_is_always_present():
    result = sizing.assess(_detail([10], [95], [20]), [10])
    assert any("placeholder" in c for c in result.caveats)
    assert any("Roof area" in c for c in result.caveats)


def test_headline_never_claims_approval():
    result = sizing.assess(_detail([10], [95], [20]), [10])
    line = sizing.headline(result)
    assert "requires engineering review" in line
    assert "preliminary" in line.lower()


def test_empty_yield_table_is_handled():
    result = sizing.assess(pd.DataFrame(), [10, 20])
    assert result.assessments == []
    assert result.preferred_kwp is None
    assert result.caveats


def test_validation_caveats_are_carried_through():
    class FakeReport:
        span_days = 3.0
        overall_coverage = 0.2
        unmeasured_windows = ["Peak"]
    result = sizing.assess(_detail([10], [95], [20]), [10],
                           validation=FakeReport())
    joined = " ".join(result.caveats)
    assert "20%" in joined
    assert "Peak" in joined
    assert "3.0 days" in joined
