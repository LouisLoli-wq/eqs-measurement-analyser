"""
Shared fixtures.

Every fixture here is synthetic. No customer measurement file is stored in
this repository, so the tests build their own from the column specification in
src/file_detection.py. That keeps the suite runnable on a clean checkout and
keeps customer data out of version control.
"""

from __future__ import annotations

import io
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


# ---------------------------------------------------------------------------
# synthetic measurement files
# ---------------------------------------------------------------------------

def _load_shape(minutes, peak, night=0.15):
    """A plausible daily load: low at night, a broad daytime plateau."""
    out = []
    for m in range(minutes):
        hour = (m // 60) % 24
        # rises from 06:00, plateaus 09:00-17:00, falls away by 20:00
        if 6 <= hour < 9:
            factor = night + (1 - night) * (hour - 6 + 1) / 4
        elif 9 <= hour < 17:
            factor = 1.0
        elif 17 <= hour < 20:
            factor = night + (1 - night) * (20 - hour) / 4
        else:
            factor = night
        wobble = 1 + 0.05 * math.sin(m / 37.0)
        out.append(peak * factor * wobble)
    return np.array(out)


def make_econ_csv(days=2, rate_min=1, peak_kw=40.0, start="01/04/2026",
                  gap_hours=0) -> bytes:
    """A synthetic Econ export with every column the analysis requires."""
    minutes = int(days * 1440 / rate_min)
    times = pd.date_range("%s 00:00:00" % pd.to_datetime(start, dayfirst=True)
                          .strftime("%Y-%m-%d"),
                          periods=minutes, freq="%dmin" % rate_min)
    p_total = _load_shape(minutes, peak_kw)
    per_phase = p_total / 3.0
    pf = np.clip(0.92 + 0.03 * np.sin(np.arange(minutes) / 91.0), 0.5, 0.99)

    data = {
        "Time": [t.strftime("%d/%m/%Y %H:%M:%S") for t in times],
        "Frequency [Hz]": np.round(50 + 0.05 * np.sin(np.arange(minutes) / 53.0), 3),
        "Pactive total avg [kW]": np.round(p_total, 3),
        "Qreactive total avg [kvar]": np.round(p_total * 0.35, 3),
    }
    for i, ln in enumerate(("L1", "L2", "L3")):
        volts = 235 + 2 * np.sin((np.arange(minutes) + i * 40) / 67.0)
        amps = per_phase * 1000 / volts
        data["%s Urms avg [V]" % ln] = np.round(volts, 1)
        data["%s Urms max [V]" % ln] = np.round(volts + 1.2, 1)
        data["%s Irms avg [A]" % ln] = np.round(amps, 2)
        data["%s Irms max [A]" % ln] = np.round(amps * 1.08, 2)
        data["%s Pactive avg [kW]" % ln] = np.round(per_phase, 3)
        data["%s U THD avg [%%]" % ln] = np.round(1.2 + 0.4 * np.cos(
            np.arange(minutes) / 71.0), 2)
        data["%s PF avg [-]" % ln] = np.round(pf, 2)

    df = pd.DataFrame(data)
    if gap_hours:
        # punch a hole in the middle, as a logger going offline would
        n = int(gap_hours * 60 / rate_min)
        start_i = max((len(df) - n) // 2, 0)
        df = pd.concat([df.iloc[:start_i], df.iloc[start_i + n:]])
    return df.to_csv(index=False, sep=";").encode("cp1252")


def make_shelly_csv(days=2, rate_min=1, peak_w=9000.0,
                    start_epoch=1786474680, gap_hours=0) -> bytes:
    """A synthetic Shelly export with every column the analysis requires."""
    minutes = int(days * 1440 / rate_min)
    stamps = start_epoch + np.arange(minutes) * rate_min * 60
    p_total = _load_shape(minutes, peak_w)
    per_phase_w = p_total / 3.0
    # the meter reports Wh accumulated over one interval, not watts
    per_phase_wh = per_phase_w * rate_min / 60.0

    data = {"timestamp": stamps}
    for i, ph in enumerate(("a", "b", "c")):
        volts = 232 + 1.5 * np.sin((np.arange(minutes) + i * 30) / 61.0)
        amps = per_phase_w / volts
        data["%s_total_act_energy" % ph] = np.round(per_phase_wh, 4)
        data["%s_max_act_power" % ph] = np.round(per_phase_w * 1.03, 1)
        data["%s_min_act_power" % ph] = np.round(per_phase_w * 0.96, 1)
        data["%s_max_aprt_power" % ph] = np.round(per_phase_w * 1.12, 1)
        data["%s_avg_voltage" % ph] = np.round(volts, 3)
        data["%s_max_voltage" % ph] = np.round(volts + 0.3, 3)
        data["%s_min_voltage" % ph] = np.round(volts - 0.3, 3)
        data["%s_avg_current" % ph] = np.round(amps, 3)
        data["%s_max_current" % ph] = np.round(amps * 1.06, 3)
        data["%s_min_current" % ph] = np.round(amps * 0.94, 3)

    df = pd.DataFrame(data)
    if gap_hours:
        n = int(gap_hours * 60 / rate_min)
        start_i = max((len(df) - n) // 2, 0)
        df = pd.concat([df.iloc[:start_i], df.iloc[start_i + n:]])
    return df.to_csv(index=False).encode("utf-8")


def make_econ_csv_with_idle(days=2, idle_share=0.8, **kw) -> bytes:
    """An Econ export where most rows are the logger's idle placeholder.

    The real Econ writes a row every interval whether or not it is measuring:
    status Code 256 and every value zero. The file therefore has no timestamp
    gaps at all while holding almost no measurements.
    """
    raw = make_econ_csv(days=days, **kw)
    df = pd.read_csv(io.BytesIO(raw), sep=";", encoding="cp1252")
    df["Code"] = 0

    # keep readings only in the middle of the day, idle everywhere else
    hour = pd.to_datetime(df["Time"], dayfirst=True).dt.hour
    keep_from = 12 - int(12 * (1 - idle_share))
    live = (hour >= keep_from) & (hour < 12 + int(12 * (1 - idle_share)))

    numeric = [c for c in df.columns if c != "Time"]
    df.loc[~live, numeric] = 0
    df.loc[~live, "Code"] = 256
    return df.to_csv(index=False, sep=";").encode("cp1252")


def make_workbook(csv_bytes: bytes, single_column=True) -> bytes:
    """Wrap a delimited export in an .xlsx, the way Excel does.

    With single_column=True this reproduces what happens when Excel opens a
    semicolon-separated file on a machine whose list separator is a comma: the
    whole row lands in one cell and nothing is split.
    """
    text = csv_bytes.decode("cp1252", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    buffer = io.BytesIO()
    if single_column:
        frame = pd.DataFrame({0: lines})
        frame.to_excel(buffer, index=False, header=False, sheet_name="in")
    else:
        rows = [ln.split(";") for ln in lines]
        pd.DataFrame(rows[1:], columns=rows[0]).to_excel(
            buffer, index=False, sheet_name="in")
    return buffer.getvalue()


def make_irradiation_csv() -> bytes:
    """An hourly irradiation profile in the shape the analysis expects."""
    rows = ["Time,G [W/m²]"]
    profile = [0, 0, 0, 0, 0, 0, 0, 32, 215, 448, 659, 806, 833,
               688, 528, 406, 321, 191, 67, 0, 0, 0, 0, 0]
    for hour, value in enumerate(profile):
        rows.append("%02d:00,%d" % (hour, value))
    rows.append("23:59,0")
    return ("\n".join(rows) + "\n").encode("cp1252")


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def econ_bytes():
    return make_econ_csv()


@pytest.fixture
def shelly_bytes():
    return make_shelly_csv()


@pytest.fixture
def irradiation_bytes():
    return make_irradiation_csv()


@pytest.fixture
def econ_idle_bytes():
    return make_econ_csv_with_idle()


@pytest.fixture
def econ_workbook_bytes(econ_bytes):
    return make_workbook(econ_bytes, single_column=True)


@pytest.fixture
def econ_df(econ_bytes):
    return pd.read_csv(io.BytesIO(econ_bytes), sep=";", encoding="cp1252")


@pytest.fixture
def shelly_df(shelly_bytes):
    return pd.read_csv(io.BytesIO(shelly_bytes), sep=",", encoding="utf-8")
