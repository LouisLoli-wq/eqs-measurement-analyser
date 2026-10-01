"""
Shelly adapter -- three-phase energy meter.

Files are comma separated UTF-8 with a Unix-epoch `timestamp` column. The
meter reports energy, not power: `*_total_act_energy` is the watt-hours
accumulated during one sample interval, so power in watts is that value times
60 / RateMin. Verified against the meter's own `*_min_act_power` and
`*_max_act_power` columns on a real export -- the derived value falls inside
that envelope on every row.

The meter measures no reactive power, no THD and no frequency, so those
figures do not exist for Shelly. It does report apparent power directly, which
is why the Shelly apparent-power charts show a maximum rather than an average.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..file_detection import SHELLY_REQUIRED
from ..plots import shelly_plots

NAME = "shelly"
LABEL = "Shelly energy meter"
DELIMITER = ","
REQUIRED_COLUMNS = SHELLY_REQUIRED
N_FIGURES = 32
NOT_MEASURED = ("reactive power", "voltage THD", "frequency")

_PHASES = ("a", "b", "c")


def plots_module():
    return shelly_plots


def describe_power() -> str:
    return ("Total active power is derived: the three phases' "
            "*_total_act_energy columns (Wh per sample interval) are summed "
            "and multiplied by 60 / RateMin to give watts. Apparent power is "
            "the sum of the three *_max_aprt_power columns. Power factor is "
            "max_act_power / max_aprt_power per phase.")


def _nice(value, divisions=10):
    if not np.isfinite(value) or value <= 0:
        return 10, 1
    magnitude = 10 ** math.floor(math.log10(value))
    top = magnitude * 10
    for mult in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 15, 20):
        if mult * magnitude >= value:
            top = mult * magnitude
            break
    step = top / divisions
    smag = 10 ** math.floor(math.log10(step)) if step > 0 else 1
    for mult in (1, 2, 2.5, 5, 10):
        if mult * smag >= step:
            step = mult * smag
            break
    return top, step


def _col(df, name):
    return pd.to_numeric(df[name], errors="coerce") if name in df else None


def sample_rate_minutes(df: pd.DataFrame) -> int:
    """Sample interval read off the epoch timestamps, in whole minutes."""
    t = pd.to_numeric(df["timestamp"], errors="coerce").dropna()
    if len(t) < 3:
        return 1
    step = t.sort_values().diff().dropna().median() / 60.0
    return int(round(step)) if np.isfinite(step) and step >= 1 else 1


def total_power_watts(df: pd.DataFrame, rate_min: int | None = None) -> pd.Series:
    """Total active power in W, by the adapter's documented conversion.

    Provided so validation and sizing can see the same quantity the plotting
    code sees, without duplicating the formula.
    """
    rate = rate_min or sample_rate_minutes(df)
    energy = sum(_col(df, "%s_total_act_energy" % p).fillna(0)
                 for p in _PHASES)
    return energy * (60.0 / float(rate))


def measuring_mask(df: pd.DataFrame) -> pd.Series:
    """True where the meter was measuring.

    The Shelly has no status column and simply stops writing rows when it is
    offline, so an idle row does not arise the way it does on the Econ. Rows
    with every phase voltage at zero are still treated as not measuring, since
    that is a dead supply rather than a reading of nothing.
    """
    volts = [s for s in (_col(df, "%s_avg_voltage" % p) for p in _PHASES)
             if s is not None]
    if not volts:
        return pd.Series(True, index=df.index)
    combined = pd.concat(volts, axis=1).fillna(0)
    return (combined > 0).any(axis=1)


def describe_idle() -> str:
    return ("The Shelly stops writing rows when it is offline, so missing "
            "measurements show up as gaps in the timestamps.")


def implausible_values(df: pd.DataFrame) -> dict:
    """Power factor above 1, which the derived ratio can produce."""
    found = {}
    live = measuring_mask(df)
    for p in _PHASES:
        act, aprt = _col(df, "%s_max_act_power" % p), _col(df, "%s_max_aprt_power" % p)
        if act is None or aprt is None:
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            pf = act / aprt
        n = int((pf[live] > 1.0).sum())
        if n:
            found["phase %s power factor above 1" % p] = n
    return found


def suggest_limits(df: pd.DataFrame) -> dict:
    """Axis limits and sample rate proposed from the file's own values."""
    out = {}
    rate = sample_rate_minutes(df)
    live = measuring_mask(df)
    if live.any():
        df = df[live]
    out["RateMin"] = rate
    out["Yformat"] = 1e-3        # Shelly power is in W; ticks are shown in kW

    # power axis, in watts
    power = total_power_watts(df, rate)
    if len(power) and np.isfinite(power.max()) and power.max() > 0:
        top, step = _nice(float(power.max()) * 1.1)
        out.update(Ymin=0, Ymax=int(top), Ydist=int(max(step, 1)))

    # apparent power axis, the sum of the three per-phase maxima
    aprt = [s for s in (_col(df, "%s_max_aprt_power" % p) for p in _PHASES)
            if s is not None]
    if aprt:
        total = sum(s.fillna(0) for s in aprt)
        if np.isfinite(total.max()) and total.max() > 0:
            top, step = _nice(float(total.max()) * 1.1)
            out.update(Amax=int(top), Adist=int(max(step, 1)))

    # current
    currents = [s.max() for s in
                (_col(df, "%s_%s" % (p, sfx))
                 for p in _PHASES for sfx in ("avg_current", "max_current"))
                if s is not None]
    currents = [x for x in currents if np.isfinite(x)]
    if currents:
        top, step = _nice(max(currents) * 1.1)
        out.update(Imax=int(top), Idist=int(max(step, 1)),
                   Imin=-int(max(round(top * 0.05), 1)))

    # voltage, ignoring outage samples
    volts = [s for s in (_col(df, "%s_%s" % (p, sfx))
                         for p in _PHASES
                         for sfx in ("min_voltage", "avg_voltage",
                                     "max_voltage"))
             if s is not None]
    if volts:
        allv = pd.concat(volts).dropna()
        live = allv[allv > 0]
        if len(live):
            live = live[live > 0.5 * live.median()]
        if len(live):
            lo = int(math.floor(live.quantile(0.002) / 20.0) * 20)
            hi = int(math.ceil(live.quantile(0.998) / 20.0) * 20)
            if hi - lo < 60:
                mid = (hi + lo) / 2
                lo, hi = int(mid - 30), int(mid + 30)
            out.update(Umin=lo, Umax=hi, Udist=20)

    return out
