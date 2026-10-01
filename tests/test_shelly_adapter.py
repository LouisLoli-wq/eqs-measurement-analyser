"""Shelly adapter: the Wh-to-W conversion above all."""

import io

import numpy as np
import pandas as pd
import pytest

from src.adapters import shelly
from src.plots import shelly_plots
from conftest import make_shelly_csv


def test_identity():
    assert shelly.NAME == "shelly"
    assert shelly.DELIMITER == ","
    assert shelly.N_FIGURES == 32
    assert "frequency" in shelly.NOT_MEASURED


def test_power_is_energy_times_sixty_over_the_rate(shelly_df):
    """The meter reports Wh per interval. Watts must land between the
    meter's own min and max active power for the same interval."""
    power = shelly.total_power_watts(shelly_df, 1)
    lo = sum(shelly_df["%s_min_act_power" % p] for p in "abc")
    hi = sum(shelly_df["%s_max_act_power" % p] for p in "abc")
    inside = ((power >= lo * 0.9) & (power <= hi * 1.1))
    assert inside.mean() > 0.99


def test_conversion_scales_with_the_sample_rate():
    five = pd.read_csv(io.BytesIO(make_shelly_csv(days=1, rate_min=5)),
                       sep=",")
    power = shelly.total_power_watts(five, 5)
    hi = sum(five["%s_max_act_power" % p] for p in "abc")
    assert (power <= hi * 1.1).mean() > 0.99, \
        "a bare x60 would overstate a 5-minute file by five times"


def test_sample_rate_is_read_from_epoch_seconds():
    five = pd.read_csv(io.BytesIO(make_shelly_csv(days=1, rate_min=5)),
                       sep=",")
    assert shelly.sample_rate_minutes(five) == 5


def test_suggestions_are_in_watts(shelly_df):
    s = shelly.suggest_limits(shelly_df)
    assert s["Yformat"] == 1e-3
    assert s["Ymax"] >= shelly.total_power_watts(shelly_df, 1).max()
    assert s["Amax"] >= sum(shelly_df["%s_max_aprt_power" % p]
                            for p in "abc").max()
    assert s["Imax"] >= shelly_df["a_max_current"].max()


def test_suggestions_survive_an_empty_frame():
    empty = pd.DataFrame(columns=list(shelly.REQUIRED_COLUMNS))
    shelly.suggest_limits(empty)


def test_legacy_x60_is_switchable():
    shelly_plots.configure(RateMin=5)
    shelly_plots.set_legacy_x60(True)
    assert shelly_plots._WH_TO_W() == 60
    shelly_plots.set_legacy_x60(False)
    assert shelly_plots._WH_TO_W() == pytest.approx(12.0)
    shelly_plots.configure(RateMin=1)
    assert shelly_plots._WH_TO_W() == pytest.approx(60.0)


def test_configure_rejects_econ_only_settings():
    with pytest.raises(KeyError):
        shelly_plots.configure(THDmax=40)


def test_step_list_matches_the_defined_functions():
    for name, _ in shelly_plots.STEPS:
        assert callable(getattr(shelly_plots, name)), name
    assert len(shelly_plots.STEPS) == 32
