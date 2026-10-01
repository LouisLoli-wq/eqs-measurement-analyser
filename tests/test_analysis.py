"""End-to-end runs of both device paths, plus session hygiene."""

import os

import pandas as pd
import pytest

from src import analysis, config as C, reporting


def _run(device, measurement, irradiation, **overrides):
    conf = C.AnalysisConfig(device=device, customer="Test Customer",
                            location="Test Site")
    for k, v in C.DEVICE_DEFAULTS[device].items():
        if hasattr(conf, k):
            setattr(conf, k, v)
    _, suggestions, _ = analysis.suggest_settings(measurement, "m.csv", device)
    for k, v in suggestions.items():
        if hasattr(conf, k):
            setattr(conf, k, v)
    for k, v in overrides.items():
        setattr(conf, k, v)
    session = analysis.Session()
    try:
        return analysis.run(conf, measurement, "m.csv", irradiation, "i.csv",
                            session=session), session
    finally:
        pass


@pytest.mark.slow
def test_econ_runs_end_to_end(econ_bytes, irradiation_bytes):
    result, session = _run("econ", econ_bytes, irradiation_bytes,
                           PPV=[20, 30, 40])
    try:
        assert result.ok, result.errors
        assert len(result.figures) == 43
        assert result.energy_summary is not None
        assert list(result.energy_summary.columns) == \
            ["Off-Peak", "Shoulder", "Peak", "Total"]
        assert result.sizing is not None
        assert len(result.sizing.assessments) == 3
        # the SunnyDesign export the notebook writes
        assert any("SunnyDesign" in f for f in result.data_files)
    finally:
        session.close()


@pytest.mark.slow
def test_shelly_runs_end_to_end(shelly_bytes, irradiation_bytes):
    result, session = _run("shelly", shelly_bytes, irradiation_bytes,
                           PPV=[10, 15, 20])
    try:
        assert result.ok, result.errors
        assert len(result.figures) == 31   # 32 minus the SMA export, as the
        assert result.pv_yield is not None  # Shelly notebook leaves it out
        assert len(result.sizing.assessments) == 3
    finally:
        session.close()


@pytest.mark.slow
def test_unmeasured_window_is_labelled_not_zeroed(shelly_bytes,
                                                  irradiation_bytes):
    """The whole point: a window with no data must not read as 0 kWh."""
    import io
    df = pd.read_csv(io.BytesIO(shelly_bytes))
    ts = pd.to_datetime(df["timestamp"], unit="s")
    working_hours = df[(ts.dt.hour >= 8) & (ts.dt.hour < 17)]
    trimmed = working_hours.to_csv(index=False).encode("utf-8")

    result, session = _run("shelly", trimmed, irradiation_bytes,
                           PPV=[10], RateMin=1)
    try:
        assert "Peak" in result.validation.unmeasured_windows
        # the original number is preserved untouched ...
        assert result.energy_summary.at["kWh/day", "Peak"] == 0
        # ... and the annotated copy says what that zero means
        assert result.energy_summary_annotated.at["kWh/day", "Peak"] \
            == "not measured"
    finally:
        session.close()


def test_missing_columns_stop_the_run(shelly_bytes, irradiation_bytes):
    import io
    df = pd.read_csv(io.BytesIO(shelly_bytes)).drop(columns=["a_avg_voltage"])
    result, session = _run("shelly", df.to_csv(index=False).encode(),
                           irradiation_bytes)
    try:
        assert not result.ok
        assert any("missing" in title.lower() for title, _ in result.errors)
        assert result.figures == []
    finally:
        session.close()


def test_date_range_excludes_rows_without_touching_the_file(shelly_bytes,
                                                           irradiation_bytes):
    import io
    from datetime import timedelta
    df = pd.read_csv(io.BytesIO(shelly_bytes))
    ts = pd.to_datetime(df["timestamp"], unit="s")
    first_day = ts.min().date()
    result, session = _run("shelly", shelly_bytes, irradiation_bytes,
                           PPV=[10], date_from=first_day, date_to=first_day)
    try:
        assert result.validation.span_days < 1.05
        assert any("outside the selected date range" in i.title
                   for i in result.validation.issues)
    finally:
        session.close()


def test_sessions_are_isolated_and_removable():
    a, b = analysis.Session(), analysis.Session()
    assert a.path != b.path
    assert os.path.isdir(a.outputs) and os.path.isdir(b.outputs)
    a.close()
    assert not os.path.exists(a.path)
    assert os.path.exists(b.path)
    b.close()


def test_sweep_removes_only_stale_folders(tmp_path):
    fresh = analysis.Session(root=str(tmp_path))
    stale = analysis.Session(root=str(tmp_path))
    old = os.stat(stale.path).st_mtime - \
        (analysis.Session.STALE_AFTER_HOURS + 1) * 3600
    os.utime(stale.path, (old, old))
    removed = analysis.Session.sweep_stale(root=str(tmp_path))
    assert removed == 1
    assert os.path.exists(fresh.path)
    assert not os.path.exists(stale.path)
    fresh.close()


@pytest.mark.slow
def test_reports_build(shelly_bytes, irradiation_bytes):
    result, session = _run("shelly", shelly_bytes, irradiation_bytes,
                           PPV=[10, 15])
    try:
        zip_bytes = reporting.build_zip(result)
        xlsx = reporting.build_xlsx(result)
        pdf = reporting.build_pdf(result, max_figures=3)
        assert zip_bytes[:2] == b"PK"
        assert xlsx[:2] == b"PK"
        assert pdf[:4] == b"%PDF"
        import zipfile, io as _io
        names = zipfile.ZipFile(_io.BytesIO(zip_bytes)).namelist()
        assert "analysis_settings.txt" in names
        assert len(names) == len(result.figures) + len(result.data_files) + 1
    finally:
        session.close()


@pytest.mark.slow
def test_workbook_upload_runs_end_to_end(econ_workbook_bytes,
                                         irradiation_bytes):
    """An Econ export saved as .xlsx must analyse exactly like the CSV."""
    result, session = _run("econ", econ_workbook_bytes, irradiation_bytes,
                           PPV=[20, 30])
    try:
        assert result.ok, result.errors
        assert len(result.figures) == 43
        assert result.validation.n_rows == 2880      # 2 days at 1 minute
    finally:
        session.close()


@pytest.mark.slow
def test_workbook_and_csv_give_identical_summaries(econ_bytes,
                                                   econ_workbook_bytes,
                                                   irradiation_bytes):
    from_csv, s1 = _run("econ", econ_bytes, irradiation_bytes, PPV=[20])
    from_xlsx, s2 = _run("econ", econ_workbook_bytes, irradiation_bytes,
                         PPV=[20])
    try:
        pd.testing.assert_frame_equal(from_csv.energy_summary,
                                      from_xlsx.energy_summary)
        pd.testing.assert_frame_equal(from_csv.pv_detail, from_xlsx.pv_detail)
    finally:
        s1.close()
        s2.close()


@pytest.mark.slow
def test_idle_rows_are_analysed_but_reported(econ_idle_bytes,
                                             irradiation_bytes):
    """The calculation is untouched; only the presentation is qualified."""
    result, session = _run("econ", econ_idle_bytes, irradiation_bytes,
                           PPV=[20])
    try:
        assert result.ok, result.errors
        # every row, idle ones included, reached the analysis
        assert result.validation.n_rows == 2880
        assert result.validation.n_idle_rows > 0
        # the untouched figure is still there, as a number ...
        import numbers
        assert isinstance(result.energy_summary.at["kWh/day", "Peak"],
                          (numbers.Number,))
        # ... and the annotated copy says what it means
        assert result.energy_summary_annotated.at["kWh/day", "Peak"] \
            == "not measured"
    finally:
        session.close()
