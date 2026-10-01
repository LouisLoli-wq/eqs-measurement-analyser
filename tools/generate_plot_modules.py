#!/usr/bin/env python3
"""
Regenerate src/plots/econ_plots.py and src/plots/shelly_plots.py from the
original analysis notebooks.

Why this exists
---------------
The plotting code in this project is NOT a rewrite. Every figure function is
the code from Louis's original notebooks, copied verbatim. This script does the
copying, so that when the notebooks change the modules can be regenerated
rather than hand-edited, and so the exact set of changes applied on the way is
written down in one place instead of being lost in a diff.

Only four kinds of change are applied:

  1. Configuration.  The notebooks' "Manual Input" cell becomes module-level
     variables set through configure(). No behaviour change.
  2. Library compatibility.  A handful of calls that current pandas and
     matplotlib reject (DatetimeIndex.week, tick_params(labelbottom='off'),
     strict datetime format strings, implicit numeric_only). Same results,
     current libraries.
  3. Parameterised axis limits.  Limits that were hard-coded inside the plot
     functions become named settings, so the app can size them from the data.
     Defaults equal the original literals.
  4. Two approved corrections, each behind a flag in src/config.py and each
     documented in TECHNICAL_NOTES.md.

Usage
-----
    python tools/generate_plot_modules.py \
        --econ   "Econ code with Max apparent & Max current.ipynb" \
        --shelly "Shelly code.ipynb"

The notebooks are not stored in this repository (they contain customer names
and local paths). Point the script at wherever you keep them; your originals
are only ever read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "src" / "plots"


# ---------------------------------------------------------------------------
# patches
# ---------------------------------------------------------------------------

#: Applied to both devices. (old, new, required)
COMMON_PATCHES = [
    # --- pandas >= 1.1 removed DatetimeIndex.week -------------------------
    (".index.week.astype(str)", ".index.isocalendar().week.astype(str)", True),
    ("dfPweek['Week']=dfPweek.index.week",
     "dfPweek['Week']=dfPweek.index.isocalendar().week", False),

    # --- pandas >= 2.0 needs numeric_only on mixed frames -----------------
    ("df = df.resample(rate).mean()",
     "df = df.resample(rate).mean(numeric_only=True)", True),
    ("dfP = dfP.resample(rate).mean()",
     "dfP = dfP.resample(rate).mean(numeric_only=True)", True),
    ("dfSimDay = dfSimDay.groupby(dfSim['Time']).mean()",
     "dfSimDay = dfSimDay.groupby(dfSim['Time']).mean(numeric_only=True)", True),
    ("dfPweekSMA = dfPweek.resample('10Min').mean()",
     "dfPweekSMA = dfPweek.resample('10Min').mean(numeric_only=True)", False),

    # --- pandas >= 2.0 is strict about format strings; these synthetic
    #     '1900-01-..' stamps are built by string concatenation and did not
    #     match the format the notebook passed --------------------------------
    ("pd.to_datetime(dfPday['DtTime'], format='%Y/%m/%d %H:%M:%S')",
     "_to_datetime_flex(dfPday['DtTime'])", True),
    ("pd.to_datetime(dfPweek['WeekDateTime'], format='%Y/%m/%d %H:%M:%S')",
     "_to_datetime_flex(dfPweek['WeekDateTime'])", False),
    ("pd.to_datetime(dfSim['Time'], format='%Y-%m-%d %H:%M')",
     "_to_datetime_flex(dfSim['Time'])", True),
    ("pd.to_datetime(dfRad['Time'], format='%Y-%m-%d %H:%M')",
     "_to_datetime_flex(dfRad['Time'])", True),

    # --- irradiation file: no Windows-only 'ansi' codec -------------------
    ("dfRad = pd.read_table(PathRadiation, sep=',', encoding ='ansi')",
     "dfRad = _read_radiation_table(PathRadiation)", True),

    # --- matplotlib >= 3.3: tick_params takes bools, not 'on'/'off' -------
    ("tick_params(labelbottom='off',labeltop='on')",
     "tick_params(labelbottom=False,labeltop=True)", False),

    # --- output folder becomes configurable -------------------------------
    ("fig.savefig('Graphs/'", "fig.savefig(OUTDIR", True),
]

#: Econ only.
ECON_PATCHES = [
    ("df = pd.read_table(PathMeasurement, sep=';', encoding ='ansi')",
     "df = _read_measurement_table(PathMeasurement, sep=';')", True),
    ("df['Time'] = pd.to_datetime(df['Time'], format='%d/%m/%Y %H:%M:%S')",
     "df['Time'] = _to_datetime_dayfirst(df['Time'])", True),
    ("dfPweekSMA['mean'].to_csv(customer+' measurement, SunnyDesign.csv', index=False)",
     "dfPweekSMA['mean'].to_csv(OUTDIR + customer + ' measurement, SunnyDesign.csv', index=False)",
     True),

    # axis limits that were literals inside the plot functions
    ("ax.set_ylim(150, 300)", "ax.set_ylim(Umin, Umax)", True),
    ("plt.MultipleLocator(20)", "plt.MultipleLocator(Udist)", True),
    ("ax.set_ylim(-5, 100)", "ax.set_ylim(Imin, Imax)", True),
    ("plt.MultipleLocator(10)", "plt.MultipleLocator(Idist)", True),
    ("ax.set_ylim(0, 40)", "ax.set_ylim(THDmin, THDmax)", True),
    ("plt.MultipleLocator(8)", "plt.MultipleLocator(THDdist)", True),
    ("ax.set_ylim(0.0, 1.1)", "ax.set_ylim(PFmin, PFmax)", True),
    ("plt.MultipleLocator(0.1)", "plt.MultipleLocator(PFdist)", True),
    ("ax.set_ylim(40, 60)", "ax.set_ylim(Fmin, Fmax)", True),
    ("ax.set_ylim(40,60)", "ax.set_ylim(Fmin, Fmax)", False),
    ("plt.MultipleLocator(2)", "plt.MultipleLocator(Fdist)", True),

    # CORRECTION 1 -- see TECHNICAL_NOTES.md "Defect 1".
    # Graph 4.1 divided L3 active power by L2's power factor. Graphs 4.2 and
    # 4.3 use L3 correctly, so 4.1 was the outlier. Reverting is a matter of
    # setting PRESERVE_LEGACY_PF_TYPO = True in src/config.py.
    ("ax.plot(df['L3 Pactive avg [kW]']/df['L2 PF avg [-]'], '-', linewidth =0.5, color=colorA[2], label = \"Phase L3\")",
     "ax.plot(df['L3 Pactive avg [kW]']/df[_L3_PF_COLUMN], '-', linewidth =0.5, color=colorA[2], label = \"Phase L3\")",
     True),
]

#: Shelly only.
SHELLY_PATCHES = [
    ("df = pd.read_table(PathMeasurement, sep=',', encoding ='utf-8')",
     "df = _read_measurement_table(PathMeasurement, sep=',')", True),

    # CORRECTION 2 -- see TECHNICAL_NOTES.md "Defect 3".
    # total_act_energy is Wh accumulated over one sample interval, so the
    # conversion to watts is 60 / RateMin, not a bare 60. Identical at the
    # 1-minute rate every file seen so far uses.
    ("df['Pp'] = (df['a_total_act_energy'] + df['b_total_act_energy'] + df['c_total_act_energy']) * 60",
     "df['Pp'] = (df['a_total_act_energy'] + df['b_total_act_energy'] + df['c_total_act_energy']) * _WH_TO_W()",
     True),
    ("dfPL = df[['a_total_act_energy', 'b_total_act_energy', 'c_total_act_energy']].copy() * 60",
     "dfPL = df[['a_total_act_energy', 'b_total_act_energy', 'c_total_act_energy']].copy() * _WH_TO_W()",
     True),

    # axis limits that were literals inside the plot functions
    ("ax.set_ylim(150, 300)", "ax.set_ylim(Umin, Umax)", True),
    ("plt.MultipleLocator(20)", "plt.MultipleLocator(Udist)", True),
    ("ax.set_ylim(-5, 50)", "ax.set_ylim(Imin, Imax)", True),
    ("ax.set_ylim(0, 50)", "ax.set_ylim(0, Imax)", True),
    ("plt.MultipleLocator(10)", "plt.MultipleLocator(Idist)", True),
    ("ax.set_ylim(0.0, 1.1)", "ax.set_ylim(PFmin, PFmax)", True),
    ("plt.MultipleLocator(0.1)", "plt.MultipleLocator(PFdist)", True),
    ("ax.set_ylim(Ymin, 50000)", "ax.set_ylim(Ymin, Amax)", True),
    ("ax.set_ylim(Ymin,50000)", "ax.set_ylim(Ymin, Amax)", False),
    ("ax.set_ylim(Ymin, 20000)", "ax.set_ylim(Ymin, Ymax)", True),
    ("plt.MultipleLocator(5000)", "plt.MultipleLocator(Adist)", True),
    ("plt.MultipleLocator(10000)", "plt.MultipleLocator(Adist)", False),
]


# ---------------------------------------------------------------------------
# the generated module's header
# ---------------------------------------------------------------------------

HEADER_TEMPLATE = '''"""
{title}
{underline}

GENERATED FILE -- do not edit by hand.

Produced by tools/generate_plot_modules.py from "{source}".
Every plotting function below is that notebook's own code. See the generator
and TECHNICAL_NOTES.md for the complete list of changes applied.

Regenerate with:
    python tools/generate_plot_modules.py --{device} "<path to the notebook>"
"""

from __future__ import annotations

import glob
import math
import os
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")                       # headless: no display required
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# matplotlib renamed the bundled seaborn styles in 3.6
for _style in ("seaborn-v0_8-whitegrid", "seaborn-whitegrid", "default"):
    try:
        plt.style.use(_style)
        break
    except Exception:
        continue


# ===========================================================================
# CONFIGURATION
#
# Everything here was the notebook's "Manual Input" cell. Set it through
# configure(); never by editing this file.
# ===========================================================================

customer = "Customer"
PathMeasurement = ""
PathRadiation = ""
OUTDIR = "outputs" + os.sep              # must end with a path separator

{axis_defaults}

Yformat = {yformat}                      # 1 -> P in kW, 1e-3 -> P in W
RateMin = 1                              # sample interval of the data, minutes
rate = "1Min"

PPV = {ppv}                              # simulated PV system sizes [kWp]
EtaPV = 0.8                              # total efficiency, PV rated to AC out
Offset = 0                               # min offset generation vs consumption
deltatime = 0                            # measurement time offset, hours

colorP = ['cornflowerblue', 'blue', 'navy']
colorU = ['tomato', 'darkorange', 'tan']
colorPF = ['paleturquoise', 'darkturquoise', 'darkcyan']
colorF = ['wheat', 'burlywood', 'peru']
colorA = ['y', 'yellowgreen', 'olive']
colorI = ['rebeccapurple', 'green', 'steelblue']
colorTHD = ['gold', 'orangered', 'olive']

{extra_config}

_SETTINGS = set("""
{settings}
""".split())


def configure(**kwargs):
    """Set any configuration value above. Unknown names raise KeyError."""
    g = globals()
    for key, value in kwargs.items():
        if key not in _SETTINGS:
            raise KeyError("unknown setting %r for {device} (valid: %s)"
                           % (key, ", ".join(sorted(_SETTINGS))))
        g[key] = value
    g["rate"] = str(int(g["RateMin"])) + "Min"
    out = str(g["OUTDIR"])
    if not out.endswith(("/", "\\\\", os.sep)):
        out += os.sep
    g["OUTDIR"] = out
    os.makedirs(out, exist_ok=True)
    return current_config()


def current_config():
    """The configuration actually in force, for the audit trail in reports."""
    g = globals()
    return {{k: g[k] for k in sorted(_SETTINGS)}}


# ===========================================================================
# INPUT HELPERS
# ===========================================================================

_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def _read_measurement_table(path, sep):
    """Read a measurement export, trying the encodings these loggers use.

    The notebooks hard-coded 'ansi' (Econ) and 'utf-8' (Shelly); 'ansi' is a
    Windows-only alias and fails everywhere else. Nothing about the parsed
    values changes.
    """
    last = None
    for enc in _ENCODINGS:
        try:
            return pd.read_csv(path, sep=sep, encoding=enc, engine="python")
        except UnicodeDecodeError as exc:
            last = exc
    raise last


def _read_radiation_table(path):
    """Read the irradiation file and normalise the irradiance column name, so
    it does not matter how the superscript in 'W/m2' was encoded."""
    last = None
    dfr = None
    for enc in _ENCODINGS:
        try:
            dfr = pd.read_csv(path, sep=",", encoding=enc, engine="python")
            break
        except UnicodeDecodeError as exc:
            last = exc
    if dfr is None:
        raise last
    dfr.columns = [str(c).strip() for c in dfr.columns]
    dfr = dfr.rename(columns={{dfr.columns[0]: "Time"}})
    for col in dfr.columns:
        if col != "Time" and col.upper().startswith("G"):
            dfr = dfr.rename(columns={{col: "G [W/m\\u00b2]"}})
            break
    return dfr


def _to_datetime_dayfirst(series):
    """Parse Econ timestamps. The notebook's exact format first, then the
    other layouts these exports use."""
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
                "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S"):
        try:
            return pd.to_datetime(series, format=fmt)
        except (ValueError, TypeError):
            continue
    return pd.to_datetime(series, dayfirst=True)


def _to_datetime_flex(series):
    """Parse the synthetic '1900-01-..' stamps the notebook builds by string
    concatenation. Older pandas accepted a loosely matching format string;
    current pandas does not."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return pd.to_datetime(series, format=fmt)
        except (ValueError, TypeError):
            continue
    return pd.to_datetime(series, format="mixed")


# The notebooks called IPython's display() after every figure and table.
# Figures are written to disk instead; tables are collected per step so the
# app can show them.
TABLES = {{}}
_current_step = ["(setup)"]


def display(obj):
    if isinstance(obj, plt.Figure):
        return
    if isinstance(obj, (pd.DataFrame, pd.Series)):
        frame = obj.to_frame() if isinstance(obj, pd.Series) else obj.copy()
        TABLES.setdefault(_current_step[0], []).append(frame)


# ===========================================================================
# RUN
# ===========================================================================

#: (function name, human label) in the order the notebook ran them.
STEPS = [
{steps}
]


def run_all(progress=None, stop_on_error=False):
    """Run every step in the notebook's order.

    progress: optional callable(index, total, label), called before each step.
    Returns {{"files": [...], "tables": {{step: [frame, ...]}},
              "errors": [(label, message)]}}.
    """
    TABLES.clear()
    os.makedirs(OUTDIR, exist_ok=True)

    errors = []
    total = len(STEPS)
    for i, (fname, label) in enumerate(STEPS):
        if progress is not None:
            progress(i, total, label)
        _current_step[0] = label
        try:
            globals()[fname]()
        except Exception as exc:                      # noqa: BLE001
            plt.close("all")
            errors.append((label, "%s: %s" % (type(exc).__name__, exc)))
            if stop_on_error:
                break
    if progress is not None:
        progress(total, total, "Done")

    files = sorted(glob.glob(os.path.join(OUTDIR, "*.png")))
    files += sorted(glob.glob(os.path.join(OUTDIR, "*.csv")))
    return {{"files": files, "tables": dict(TABLES), "errors": errors}}


# ===========================================================================
# DATA HOLDERS -- populated by the functions below, as in the notebook
# ===========================================================================

df = pd.DataFrame()
dfP = pd.DataFrame()
dfPday = pd.DataFrame()
dfPL = pd.DataFrame()
dfU = pd.DataFrame()
dfI = pd.DataFrame()
dfTHD = pd.DataFrame()
dfRad = pd.DataFrame()
dfGen = pd.DataFrame()
dfSim = pd.DataFrame()
dfEd = pd.DataFrame()
dfPVd = pd.DataFrame()
EPVmax = pd.DataFrame()
EPVmaxP = pd.DataFrame()
dfAPmax = pd.DataFrame()
dfImax = pd.DataFrame()

{pp_line}


# ===========================================================================
# PLOTTING FUNCTIONS -- the notebook's code, unchanged
# ===========================================================================

'''

ECON_AXIS_DEFAULTS = """# Power / apparent power axis [kW or kVA]
Ymax, Ymin, Ydist = 500, 0, 50
# Voltage axis [V]
Umin, Umax, Udist = 150, 300, 20
# Current axis [A]
Imin, Imax, Idist = -5, 100, 10
# Voltage THD axis [%]
THDmin, THDmax, THDdist = 0, 40, 8
# Power factor axis [-]
PFmin, PFmax, PFdist = 0.0, 1.1, 0.1
# Frequency axis [Hz]
Fmin, Fmax, Fdist = 40, 60, 2"""

SHELLY_AXIS_DEFAULTS = """# Power axis [W, displayed via Yformat]
Ymax, Ymin, Ydist = 10000, 0, 1000
# Apparent power axis [VA]
Amax, Adist = 50000, 5000
# Voltage axis [V]
Umin, Umax, Udist = 150, 300, 20
# Current axis [A]
Imin, Imax, Idist = -5, 50, 10
# Power factor axis [-]
PFmin, PFmax, PFdist = 0.0, 1.1, 0.1"""

ECON_EXTRA = '''# Correction 1 (see TECHNICAL_NOTES.md). Set PRESERVE_LEGACY_PF_TYPO to
# reproduce the original graph 4.1, which divided L3 by L2's power factor.
PRESERVE_LEGACY_PF_TYPO = False
_L3_PF_COLUMN = "L3 PF avg [-]"


def set_legacy_pf_typo(enabled):
    """Choose which power-factor column graph 4.1 divides L3 by."""
    global PRESERVE_LEGACY_PF_TYPO, _L3_PF_COLUMN
    PRESERVE_LEGACY_PF_TYPO = bool(enabled)
    _L3_PF_COLUMN = "L2 PF avg [-]" if enabled else "L3 PF avg [-]"'''

SHELLY_EXTRA = '''# Correction 2 (see TECHNICAL_NOTES.md). total_act_energy is Wh accumulated
# over one sample interval, so watts = Wh * 60 / RateMin. The notebook used a
# bare 60, which is only right at a 1-minute rate.
PRESERVE_LEGACY_X60 = False


def set_legacy_x60(enabled):
    """Choose between the literal x60 and the rate-derived conversion."""
    global PRESERVE_LEGACY_X60
    PRESERVE_LEGACY_X60 = bool(enabled)


def _WH_TO_W():
    """Wh-per-interval to W."""
    if PRESERVE_LEGACY_X60:
        return 60
    return 60.0 / float(RateMin)'''

ECON_SETTINGS = (
    "customer PathMeasurement PathRadiation OUTDIR "
    "Ymax Ymin Ydist Umin Umax Udist Imin Imax Idist "
    "THDmin THDmax THDdist PFmin PFmax PFdist Fmin Fmax Fdist "
    "Yformat RateMin PPV EtaPV Offset deltatime "
    "colorP colorU colorPF colorF colorA colorI colorTHD"
)

SHELLY_SETTINGS = (
    "customer PathMeasurement PathRadiation OUTDIR "
    "Ymax Ymin Ydist Amax Adist Umin Umax Udist Imin Imax Idist "
    "PFmin PFmax PFdist "
    "Yformat RateMin PPV EtaPV Offset deltatime "
    "colorP colorU colorPF colorF colorA colorI colorTHD"
)

#: (function, label) per device, in the notebooks' own call order.
ECON_STEPS = [
    ("read_measurement_data", "Reading measurement data"),
    ("plot_total_power_active_total", "1.1 Power - total period"),
    ("plot_total_power_active_weekly", "1.2 Power - weekly"),
    ("plot_total_power_active_daily", "1.3 Power - daily"),
    ("plot_phase_power_active_total", "2.1 Power per phase - total period"),
    ("plot_phase_power_active_weekly", "2.2 Power per phase - weekly"),
    ("plot_phase_power_active_daily", "2.3 Power per phase - daily"),
    ("plot_total_power_apparent_total", "3.1 Apparent power - total period"),
    ("plot_total_power_apparent_weekly", "3.2 Apparent power - weekly"),
    ("plot_total_power_apparent_daily", "3.3 Apparent power - daily"),
    ("plot_phase_power_apparent_total", "4.1 Apparent power per phase - total period"),
    ("plot_phase_power_apparent_weekly", "4.2 Apparent power per phase - weekly"),
    ("plot_phase_power_apparent_daily", "4.3 Apparent power per phase - daily"),
    ("plot_phase_voltage_total", "5.1 Voltage - total period"),
    ("plot_phase_voltage_weekly", "5.2 Voltage - weekly"),
    ("plot_phase_voltage_daily", "5.3 Voltage - daily"),
    ("plot_phase_current_total", "6.1 Current - total period"),
    ("plot_phase_current_weekly", "6.2 Current - weekly"),
    ("plot_phase_current_daily", "6.3 Current - daily"),
    ("plot_total_max_apparent_power_total", "3.4 Max apparent power - total"),
    ("plot_phase_max_apparent_power_total", "6.4 Max apparent power per phase - total"),
    ("plot_phase_max_apparent_power_weekly", "6.5 Max apparent power per phase - weekly"),
    ("plot_phase_max_apparent_power_daily", "6.6 Max apparent power per phase - daily"),
    ("plot_total_max_current_total", "6.10 Max current - total"),
    ("plot_phase_max_current_total", "6.7 Max current per phase - total"),
    ("plot_phase_max_current_weekly", "6.8 Max current per phase - weekly"),
    ("plot_phase_max_current_daily", "6.9 Max current per phase - daily"),
    ("plot_phase_THD_total", "7.1 Voltage THD - total period"),
    ("plot_phase_THD_weekly", "7.2 Voltage THD - weekly"),
    ("plot_phase_THD_daily", "7.3 Voltage THD - daily"),
    ("plot_phase_PF_total", "8.1 Power factor - total period"),
    ("plot_phase_PF_weekly", "8.2 Power factor - weekly"),
    ("plot_phase_PF_daily", "8.3 Power factor - daily"),
    ("plot_frequency_total", "9.1 Frequency - total period"),
    ("plot_frequency_weekly", "9.2 Frequency - weekly"),
    ("plot_frequency_daily", "9.3 Frequency - daily"),
    ("plot_power_active_daily_average", "10.1/10.2 Average day"),
    ("summary_energy", "Energy summary"),
    ("read_radiation_data", "13.1 Irradiance"),
    ("simulation_generation_daily_average", "11.1/11.2 PV generation"),
    ("simulation_generation_daily_subplots", "11.3 PV generation - daily"),
    ("summary_yield", "PV yield summary"),
    ("summary_generation_yield", "12 Summary sheet"),
    ("calculation_SMA", "13.2 SunnyDesign export"),
]

SHELLY_STEPS = [
    ("read_measurement_data", "Reading measurement data"),
    ("plot_total_power_active_total", "1.1 Power - total period"),
    ("plot_total_power_active_weekly", "1.2 Power - weekly"),
    ("plot_total_power_active_daily", "1.3 Power - daily"),
    ("plot_phase_power_active_total", "2.1 Power per phase - total period"),
    ("plot_phase_power_active_weekly", "2.2 Power per phase - weekly"),
    ("plot_phase_power_active_daily", "2.3 Power per phase - daily"),
    ("plot_total_power_apparent_total", "3.1 Max apparent power - total period"),
    ("plot_total_power_apparent_weekly", "3.2 Max apparent power - weekly"),
    ("plot_total_power_apparent_daily", "3.3 Max apparent power - daily"),
    ("plot_phase_power_apparent_total", "4.1 Max apparent power per phase - total"),
    ("plot_phase_power_apparent_weekly", "4.2 Max apparent power per phase - weekly"),
    ("plot_phase_power_apparent_daily", "4.3 Max apparent power per phase - daily"),
    ("plot_phase_voltage_total", "5.1 Voltage - total period"),
    ("plot_phase_voltage_weekly", "5.2 Voltage - weekly"),
    ("plot_phase_voltage_daily", "5.3 Voltage - daily"),
    ("plot_phase_current_total", "6.1 Current - total period"),
    ("plot_phase_current_weekly", "6.2 Current - weekly"),
    ("plot_phase_current_daily", "6.3 Current - daily"),
    ("plot_phase_max_current_total", "6.1max Max current - total period"),
    ("plot_phase_max_current_weekly", "6.2max Max current - weekly"),
    ("plot_phase_max_current_daily", "6.3max Max current - daily"),
    ("plot_phase_PF_total", "8.1 Power factor - total period"),
    ("plot_phase_PF_weekly", "8.2 Power factor - weekly"),
    ("plot_phase_PF_daily", "8.3 Power factor - daily"),
    ("plot_power_active_daily_average", "10.1/10.2 Average day"),
    ("summary_energy", "Energy summary"),
    ("read_radiation_data", "13.1 Irradiance"),
    ("simulation_generation_daily_average", "11.1/11.2 PV generation"),
    ("simulation_generation_daily_subplots", "11.3 PV generation - daily"),
    ("summary_yield", "PV yield summary"),
    ("summary_generation_yield", "12 Summary sheet"),
]


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------

def notebook_function_cell(path):
    """The code cell that defines the plotting functions."""
    nb = json.loads(Path(path).read_text(encoding="utf-8"))
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        src = "".join(cell["source"])
        if "def read_measurement_data()" in src:
            return src
    raise SystemExit("no function cell found in %s" % path)


def generate(device, notebook, out_path):
    body = notebook_function_cell(notebook)

    # drop the dataframe-initialisation preamble; the header supplies it
    marker = "# Read Measurement Data"
    if marker in body:
        body = marker + body.split(marker, 1)[1]

    patches = COMMON_PATCHES + (ECON_PATCHES if device == "econ"
                                else SHELLY_PATCHES)
    report = []
    for old, new, required in patches:
        hits = body.count(old)
        if hits:
            body = body.replace(old, new)
        elif required:
            raise SystemExit(
                "%s: required patch not found in the notebook:\n  %s"
                % (device, old[:100]))
        report.append((hits, old[:64]))

    # nothing must still write to the notebook's hard-coded folder
    if "'Graphs/'" in body:
        raise SystemExit("%s: an unpatched 'Graphs/' path remains" % device)
    if re.search(r"\.index\.week\b", body):
        raise SystemExit("%s: an unpatched .index.week remains" % device)

    steps = ECON_STEPS if device == "econ" else SHELLY_STEPS
    # every step must exist in the generated module
    defined = set(re.findall(r"^def (\w+)", body, re.M))
    missing = [f for f, _ in steps if f not in defined]
    if missing:
        raise SystemExit("%s: STEPS names %s are not defined in the notebook"
                         % (device, missing))

    title = "%s measurement plotting" % device.capitalize()
    header = HEADER_TEMPLATE.format(
        title=title,
        underline="=" * len(title),
        source=Path(notebook).name,
        device=device,
        axis_defaults=(ECON_AXIS_DEFAULTS if device == "econ"
                       else SHELLY_AXIS_DEFAULTS),
        extra_config=ECON_EXTRA if device == "econ" else SHELLY_EXTRA,
        settings="\n".join(
            (ECON_SETTINGS if device == "econ" else SHELLY_SETTINGS).split()),
        yformat="1" if device == "econ" else "1e-3",
        ppv="[150, 200, 250, 300]" if device == "econ" else "[10, 15, 18, 20]",
        steps="\n".join('    ("%s", "%s"),' % s for s in steps),
        pp_line=("Pp = 'Pactive total avg [kW]'" if device == "econ"
                 else "Pp = 'Pp'"),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + body + "\n", encoding="utf-8")

    n_figs = body.count("fig.savefig")
    print("  %-14s -> %s" % (device, out_path.relative_to(REPO)))
    print("     %d figure functions, %d steps, %d patches applied"
          % (n_figs, len(steps), sum(1 for h, _ in report if h)))
    for hits, old in report:
        if hits == 0:
            print("     note: optional patch not present -> %s" % old)
    return n_figs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--econ", help="path to the Econ notebook (.ipynb)")
    ap.add_argument("--shelly", help="path to the Shelly notebook (.ipynb)")
    args = ap.parse_args(argv)

    if not args.econ and not args.shelly:
        ap.error("give --econ, --shelly, or both")

    print("Regenerating plot modules")
    if args.econ:
        generate("econ", args.econ, OUT_DIR / "econ_plots.py")
    if args.shelly:
        generate("shelly", args.shelly, OUT_DIR / "shelly_plots.py")
    print("Done. Run the tests before committing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
