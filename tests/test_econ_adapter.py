"""Econ adapter: column spec, axis suggestions, and the graph-4.1 correction."""

import pandas as pd
import pytest

from src.adapters import econ
from src.plots import econ_plots


def test_identity():
    assert econ.NAME == "econ"
    assert econ.DELIMITER == ";"
    assert econ.N_FIGURES == 43
    assert econ.NOT_MEASURED == ()


def test_required_columns_cover_every_phase():
    for ln in ("L1", "L2", "L3"):
        for col in ("Urms avg [V]", "Irms max [A]", "PF avg [-]",
                    "U THD avg [%]"):
            assert "%s %s" % (ln, col) in econ.REQUIRED_COLUMNS
    assert "Qreactive total avg [kvar]" in econ.REQUIRED_COLUMNS


def test_suggestions_bracket_the_data(econ_df):
    s = econ.suggest_limits(econ_df)
    assert s["Yformat"] == 1.0
    assert s["RateMin"] == 1
    # the power axis must clear the largest thing drawn on it
    peak = econ_df["Pactive total avg [kW]"].max()
    assert s["Ymax"] >= peak
    assert s["Ydist"] > 0
    # voltage bracket sits around the real values
    assert s["Umin"] <= econ_df["L1 Urms avg [V]"].min()
    assert s["Umax"] >= econ_df["L1 Urms avg [V]"].max()
    assert s["Imax"] >= econ_df["L1 Irms max [A]"].max()


def test_suggestions_survive_an_empty_frame():
    empty = pd.DataFrame(columns=list(econ.REQUIRED_COLUMNS))
    econ.suggest_limits(empty)          # must not raise


def test_sample_rate_is_read_from_the_timestamps():
    from conftest import make_econ_csv
    import io
    df = pd.read_csv(io.BytesIO(make_econ_csv(days=1, rate_min=5)),
                     sep=";", encoding="cp1252")
    assert econ.suggest_limits(df)["RateMin"] == 5


def test_outage_samples_do_not_stretch_the_voltage_axis(econ_df):
    blackout = econ_df.copy()
    for ln in ("L1", "L2", "L3"):
        blackout.loc[blackout.index[:60], "%s Urms avg [V]" % ln] = 0.0
    s = econ.suggest_limits(blackout)
    assert s["Umin"] > 100, "a blackout must not drag the axis down to zero"


def test_configure_rejects_unknown_settings():
    with pytest.raises(KeyError):
        econ_plots.configure(NotASetting=1)


def test_configure_keeps_rate_and_outdir_consistent(tmp_path):
    econ_plots.configure(RateMin=5, OUTDIR=str(tmp_path / "out"))
    assert econ_plots.rate == "5Min"
    assert econ_plots.OUTDIR.endswith(("/", "\\"))
    econ_plots.configure(RateMin=1)


def test_pf_typo_correction_is_switchable():
    """Graph 4.1 divided L3 by L2's power factor; 4.2 and 4.3 did not."""
    econ_plots.set_legacy_pf_typo(True)
    assert econ_plots._L3_PF_COLUMN == "L2 PF avg [-]"
    econ_plots.set_legacy_pf_typo(False)
    assert econ_plots._L3_PF_COLUMN == "L3 PF avg [-]"


def test_step_list_matches_the_defined_functions():
    for name, _ in econ_plots.STEPS:
        assert callable(getattr(econ_plots, name)), name
    assert len(econ_plots.STEPS) == 44        # 43 figures plus the data read


# ---------------------------------------------------------------------------
# Idle rows and implausible readings
#
# The Econ writes a row every interval whether or not it is measuring, so a
# file can be gap-free and still hold almost no measurements.
# ---------------------------------------------------------------------------

def test_idle_rows_are_excluded_from_measuring(econ_idle_bytes):
    import io
    df = pd.read_csv(io.BytesIO(econ_idle_bytes), sep=";", encoding="cp1252")
    mask = econ.measuring_mask(df)
    assert mask.sum() < len(df) * 0.5
    assert (df.loc[~mask, "Code"] == econ.IDLE_CODE).all()
    # and every idle row really is all zeros
    assert (df.loc[~mask, "Pactive total avg [kW]"] == 0).all()


def test_measuring_mask_falls_back_to_voltage_without_a_code_column(econ_df):
    stripped = econ_df.drop(columns=["Code"], errors="ignore")
    stripped.loc[stripped.index[:100], ["L1 Urms avg [V]", "L2 Urms avg [V]",
                                        "L3 Urms avg [V]"]] = 0.0
    mask = econ.measuring_mask(stripped)
    assert mask.sum() == len(stripped) - 100


def test_measuring_mask_defaults_to_true_when_nothing_identifies_idle():
    frame = pd.DataFrame({"Pactive total avg [kW]": [1.0, 2.0, 3.0]})
    assert econ.measuring_mask(frame).all()


def test_idle_rows_do_not_drag_the_voltage_axis_to_zero(econ_idle_bytes):
    import io
    df = pd.read_csv(io.BytesIO(econ_idle_bytes), sep=";", encoding="cp1252")
    s = econ.suggest_limits(df)
    assert s["Umin"] > 100, "zeros from idle rows must be ignored"


def test_implausible_thd_is_reported_not_corrected(econ_df):
    dirty = econ_df.copy()
    dirty.loc[dirty.index[:7], "L1 U THD avg [%]"] = 2387.2
    found = econ.implausible_values(dirty)
    assert found["L1 U THD avg [%] above 100%"] == 7
    # the value is still in the frame; nothing was clipped or dropped
    assert dirty["L1 U THD avg [%]"].max() == pytest.approx(2387.2)


def test_implausible_thd_does_not_set_the_axis(econ_df):
    dirty = econ_df.copy()
    dirty.loc[dirty.index[:7], "L1 U THD avg [%]"] = 2387.2
    assert econ.suggest_limits(dirty)["THDmax"] <= 120


def test_power_factor_above_one_is_reported(econ_df):
    dirty = econ_df.copy()
    dirty.loc[dirty.index[:4], "L2 PF avg [-]"] = 1.4
    assert econ.implausible_values(dirty)["L2 PF avg [-] above 1"] == 4


def test_clean_file_reports_nothing_implausible(econ_df):
    assert econ.implausible_values(econ_df) == {}
