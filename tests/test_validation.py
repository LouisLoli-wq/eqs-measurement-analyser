"""Validation reports what is wrong and changes nothing."""

import io

import pandas as pd
import pytest

from src import config as cfg, validation as V
from conftest import make_econ_csv, make_shelly_csv


def _df(data, sep, enc):
    return pd.read_csv(io.BytesIO(data), sep=sep, encoding=enc)


def test_clean_econ_file_passes(econ_df):
    rep = V.validate(econ_df, "econ", rate_min=1)
    assert rep.can_proceed
    assert rep.overall_coverage > 0.99
    assert rep.n_duplicate_timestamps == 0
    assert not rep.unmeasured_windows


def test_clean_shelly_file_passes(shelly_df):
    rep = V.validate(shelly_df, "shelly", rate_min=1)
    assert rep.can_proceed
    assert rep.overall_coverage > 0.99
    assert rep.span_days == pytest.approx(2, abs=0.01)


def test_missing_required_column_is_an_error(econ_df):
    trimmed = econ_df.drop(columns=["L2 Irms max [A]"])
    rep = V.validate(trimmed, "econ", rate_min=1)
    assert not rep.can_proceed
    assert any("L2 Irms max [A]" in i.detail for i in rep.errors)


def test_missing_time_column_stops_early(shelly_df):
    rep = V.validate(shelly_df.drop(columns=["timestamp"]), "shelly")
    assert not rep.can_proceed


def test_empty_frame_is_an_error():
    rep = V.validate(pd.DataFrame({"timestamp": []}), "shelly")
    assert not rep.can_proceed


def test_gaps_are_detected_and_measured():
    data = make_shelly_csv(days=3, gap_hours=8)
    df = _df(data, ",", "utf-8")
    rep = V.validate(df, "shelly", rate_min=1)
    assert rep.gaps, "an 8-hour hole should be reported"
    assert max(g[2] for g in rep.gaps) == pytest.approx(8, abs=0.1)
    assert rep.overall_coverage < 1.0


def test_low_coverage_raises_a_warning():
    data = make_shelly_csv(days=4, gap_hours=48)
    df = _df(data, ",", "utf-8")
    rep = V.validate(df, "shelly", rate_min=1)
    assert rep.overall_coverage < cfg.MIN_OVERALL_COVERAGE
    assert any("was recorded" in i.title for i in rep.warnings)


def test_unmeasured_window_is_named():
    """A file holding only working hours must not report a Peak figure."""
    data = make_shelly_csv(days=3)
    df = _df(data, ",", "utf-8")
    ts = pd.to_datetime(df["timestamp"], unit="s")
    df = df[(ts.dt.hour >= 8) & (ts.dt.hour < 17)]
    rep = V.validate(df, "shelly", rate_min=1)
    assert "Peak" in rep.unmeasured_windows
    assert "Off-Peak" in rep.unmeasured_windows
    assert "Shoulder" not in rep.unmeasured_windows


def test_duplicate_timestamps_are_counted(shelly_df):
    doubled = pd.concat([shelly_df, shelly_df.head(20)])
    rep = V.validate(doubled, "shelly", rate_min=1)
    assert rep.n_duplicate_timestamps == 20
    assert any("duplicate" in i.title.lower() for i in rep.warnings)


def test_unparseable_timestamps_are_counted(econ_df):
    broken = econ_df.copy()
    broken.loc[broken.index[:5], "Time"] = "not a date"
    rep = V.validate(broken, "econ", rate_min=1)
    assert rep.n_unparseable_timestamps == 5


def test_mostly_unparseable_timestamps_block(econ_df):
    broken = econ_df.copy()
    broken["Time"] = "rubbish"
    rep = V.validate(broken, "econ", rate_min=1)
    assert not rep.can_proceed


def test_non_numeric_measurements_are_reported(shelly_df):
    dirty = shelly_df.copy()
    dirty["a_avg_voltage"] = dirty["a_avg_voltage"].astype(object)
    dirty.loc[dirty.index[:3], "a_avg_voltage"] = "n/a"
    rep = V.validate(dirty, "shelly", rate_min=1)
    assert rep.non_numeric.get("a_avg_voltage") == 3
    assert any("Non-numeric" in i.title for i in rep.warnings)


def test_validation_never_modifies_the_frame(shelly_df):
    before = shelly_df.copy(deep=True)
    V.validate(shelly_df, "shelly", rate_min=1)
    pd.testing.assert_frame_equal(shelly_df, before)


def test_short_period_is_flagged():
    data = make_shelly_csv(days=3)
    df = _df(data, ",", "utf-8")
    rep = V.validate(df, "shelly", rate_min=1)
    assert any("Measurement period" in i.title for i in rep.issues)


def test_coverage_tables_have_a_row_per_hour(shelly_df):
    rep = V.validate(shelly_df, "shelly", rate_min=1)
    assert len(V.coverage_frame(rep)) == 24
    assert len(V.day_frame(rep)) == len(rep.day_coverage)


# ---------------------------------------------------------------------------
# Rows that exist but hold no measurement
# ---------------------------------------------------------------------------

def test_idle_rows_lower_coverage_and_raise_a_warning():
    from conftest import make_econ_csv_with_idle
    df = _df(make_econ_csv_with_idle(days=3, idle_share=0.8), ";", "cp1252")
    rep = V.validate(df, "econ", rate_min=1)
    # the file has no timestamp gaps at all ...
    ts = pd.to_datetime(df["Time"], dayfirst=True)
    assert ts.diff().dropna().dt.total_seconds().max() == 60
    # ... but most of it holds no measurement, and that must be said
    assert rep.n_idle_rows > 0
    assert rep.idle_share > 0.5
    assert rep.overall_coverage < 0.5
    assert any("hold no measurement" in i.title for i in rep.warnings)


def test_idle_rows_make_the_night_windows_unmeasured():
    from conftest import make_econ_csv_with_idle
    df = _df(make_econ_csv_with_idle(days=3, idle_share=0.8), ";", "cp1252")
    rep = V.validate(df, "econ", rate_min=1)
    assert "Off-Peak" in rep.unmeasured_windows
    assert "Peak" in rep.unmeasured_windows


def test_a_file_of_nothing_but_idle_rows_is_an_error():
    from conftest import make_econ_csv
    df = _df(make_econ_csv(days=1), ";", "cp1252")
    df["Code"] = 256
    rep = V.validate(df, "econ", rate_min=1)
    assert not rep.can_proceed
    assert any("No usable measurements" in i.title for i in rep.errors)


def test_implausible_values_reach_the_report(econ_df):
    dirty = econ_df.copy()
    dirty.loc[dirty.index[:9], "L3 U THD avg [%]"] = 500.0
    rep = V.validate(dirty, "econ", rate_min=1)
    assert rep.implausible
    assert any("implausible" in i.title.lower() for i in rep.warnings)


def test_shelly_without_a_status_column_is_unaffected(shelly_df):
    rep = V.validate(shelly_df, "shelly", rate_min=1)
    assert rep.n_idle_rows == 0
    assert rep.overall_coverage > 0.99
