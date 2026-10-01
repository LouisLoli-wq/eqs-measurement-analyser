"""
Econ adapter -- three-phase power-quality logger.

Files are semicolon separated, written in the Windows "ansi" codepage, with a
`Time` column in DD/MM/YYYY HH:MM:SS. Power, reactive power, power factor,
THD and frequency are all measured directly; nothing is derived from energy.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..file_detection import ECON_REQUIRED
from ..plots import econ_plots

NAME = "econ"
LABEL = "Econ power-quality logger"
DELIMITER = ";"
REQUIRED_COLUMNS = ECON_REQUIRED
N_FIGURES = 43
NOT_MEASURED = ()

#: Everything drawn on the shared power axis, so one limit fits them all.
_POWER_COLUMNS = ("Pactive total avg [kW]", "L1 Pactive avg [kW]",
                  "L2 Pactive avg [kW]", "L3 Pactive avg [kW]")


def plots_module():
    return econ_plots


def describe_power() -> str:
    return ("Total active power is the logger's own "
            "'Pactive total avg [kW]' column. Total apparent power is "
            "sqrt(P^2 + Q^2); per-phase apparent power is P / PF.")


def _nice(value, divisions=10):
    """Round a value up to a readable axis maximum, with a readable step."""
    if not np.isfinite(value) or value <= 0:
        return 10, 1
    magnitude = 10 ** math.floor(math.log10(value))
    top = magnitude * 10
    # a finely graded ladder, so the axis sits just above the data rather than
    # at the next power of ten -- an axis with half its height unused makes a
    # load profile look flat
    for mult in (1, 1.2, 1.5, 1.8, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8, 9, 10,
                 12, 15, 18, 20):
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


#: Status code the logger writes while it is powered but not measuring.
IDLE_CODE = 256


def measuring_mask(df: pd.DataFrame) -> pd.Series:
    """True where the logger was actually measuring.

    The Econ keeps writing a row every interval when it is idle: status Code
    256, and every voltage, current and power zero. Those rows are real rows
    with real timestamps, so a gap check based on timestamps alone sees a
    complete file. Preference order:

      1. the Code column, where 0 means measuring
      2. failing that, any phase voltage above zero
    """
    code = _col(df, "Code")
    if code is not None and code.notna().any():
        return code.fillna(IDLE_CODE) == 0

    volts = [s for s in (_col(df, "%s Urms avg [V]" % ln)
                         for ln in ("L1", "L2", "L3")) if s is not None]
    if volts:
        combined = pd.concat(volts, axis=1).fillna(0)
        return (combined > 0).any(axis=1)
    return pd.Series(True, index=df.index)


def describe_idle() -> str:
    return ("The Econ writes a row every interval even when it is not "
            "measuring, with status Code 256 and every value zero.")


def implausible_values(df: pd.DataFrame) -> dict:
    """Values that are inside the file but outside physical sense.

    Reported, never corrected. Voltage THD above 100% and power factor above
    1 both show up in real exports, usually in the moments around the supply
    cutting in or out.
    """
    found = {}
    live = measuring_mask(df)
    for ln in ("L1", "L2", "L3"):
        thd = _col(df, "%s U THD avg [%%]" % ln)
        if thd is not None:
            n = int((thd[live] > 100).sum())
            if n:
                found["%s U THD avg [%%] above 100%%" % ln] = n
        pf = _col(df, "%s PF avg [-]" % ln)
        if pf is not None:
            n = int((pf[live] > 1.0).sum())
            if n:
                found["%s PF avg [-] above 1" % ln] = n
    return found


def suggest_limits(df: pd.DataFrame) -> dict:
    """Axis limits and sample rate proposed from the file's own values.

    Only rows where the logger was measuring are considered. Idle rows are
    all zeros and would drag every lower bound to zero.
    """
    out = {}
    live = measuring_mask(df)
    if live.any():
        df = df[live]

    # power and apparent power share one axis
    peaks = [s.max() for s in (_col(df, c) for c in _POWER_COLUMNS)
             if s is not None]
    p, q = _col(df, "Pactive total avg [kW]"), _col(df, "Qreactive total avg [kvar]")
    if p is not None and q is not None:
        peaks.append(float(np.sqrt(p ** 2 + q ** 2).max()))
    for ln in ("L1", "L2", "L3"):
        i_max = _col(df, "%s Irms max [A]" % ln)
        u_max = _col(df, "%s Urms max [V]" % ln)
        if i_max is not None and u_max is not None:
            peaks.append(float((i_max * u_max / 1000).max()))
    peaks = [x for x in peaks if x is not None and np.isfinite(x)]
    if peaks:
        top, step = _nice(max(peaks) * 1.05)
        out.update(Ymin=0, Ymax=int(top), Ydist=int(max(step, 1)))

    # current
    currents = [s.max() for s in
                (_col(df, "%s %s" % (ln, sfx))
                 for ln in ("L1", "L2", "L3")
                 for sfx in ("Irms avg [A]", "Irms max [A]"))
                if s is not None]
    currents = [x for x in currents if np.isfinite(x)]
    if currents:
        top, step = _nice(max(currents) * 1.05)
        out.update(Imax=int(top), Idist=int(max(step, 1)),
                   Imin=-int(max(round(top * 0.05), 1)))

    # voltage, ignoring outage samples so a blackout does not stretch the axis
    volts = [s for s in (_col(df, "%s %s" % (ln, sfx))
                         for ln in ("L1", "L2", "L3")
                         for sfx in ("Urms min [V]", "Urms avg [V]",
                                     "Urms max [V]"))
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

    # voltage THD
    # Voltage THD above 100% is not a real reading; it shows up in the moments
    # around the supply cutting in or out. Those rows are reported by
    # implausible_values() and left in the data, but they must not set the
    # axis, or 13 bad rows scale the chart to 2500% and flatten everything.
    thd_series = [s for s in (_col(df, "%s U THD avg [%%]" % ln)
                              for ln in ("L1", "L2", "L3"))
                  if s is not None and s.notna().any()]
    thd = []
    for s in thd_series:
        sane = s[(s >= 0) & (s <= 100)]
        if len(sane):
            # the sane maximum, not a quantile: THD on these sites is bimodal,
            # sitting near 2% with a thin tail into the tens around supply
            # transients, and a quantile would clip that tail off the chart
            thd.append(sane.max())
    thd = [x for x in thd if np.isfinite(x)]
    if thd:
        top, step = _nice(max(max(thd) * 1.05, 5), 5)
        out.update(THDmin=0, THDmax=int(top), THDdist=int(max(step, 1)))

    # frequency, centred on whichever nominal the site runs at
    f = _col(df, "Frequency [Hz]")
    if f is not None and f.notna().any():
        med = f[f > 0].median() if (f > 0).any() else 50
        centre = 50 if abs(med - 50) <= abs(med - 60) else 60
        out.update(Fmin=centre - 10, Fmax=centre + 10, Fdist=2)

    # sample rate, straight off the timestamps
    if "Time" in df.columns:
        t = pd.to_datetime(df["Time"], dayfirst=True, errors="coerce").dropna()
        if len(t) > 2:
            step_min = t.sort_values().diff().dropna() \
                        .dt.total_seconds().median() / 60.0
            if np.isfinite(step_min) and step_min >= 1:
                out["RateMin"] = int(round(step_min))

    out["Yformat"] = 1.0        # Econ power columns are already kW

    # Peak measured demand, in kW. Used only to put sensible starting numbers
    # in the system-size boxes; it is not a sizing rule and nothing in the
    # analysis depends on it.
    total = _col(df, "Pactive total avg [kW]")
    if total is not None and total.notna().any():
        out["peak_kw"] = float(total.max())
    return out
