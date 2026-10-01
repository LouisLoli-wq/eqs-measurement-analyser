"""
Econ measurement plotting
=========================

GENERATED FILE -- do not edit by hand.

Produced by tools/generate_plot_modules.py from "8b270b90-Econ_code_with_Max_apparent__Max_current.ipynb".
Every plotting function below is that notebook's own code. See the generator
and TECHNICAL_NOTES.md for the complete list of changes applied.

Regenerate with:
    python tools/generate_plot_modules.py --econ "<path to the notebook>"
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

# Power / apparent power axis [kW or kVA]
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
Fmin, Fmax, Fdist = 40, 60, 2

Yformat = 1                      # 1 -> P in kW, 1e-3 -> P in W
RateMin = 1                              # sample interval of the data, minutes
rate = "1Min"

PPV = [150, 200, 250, 300]                              # simulated PV system sizes [kWp]
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

# Correction 1 (see TECHNICAL_NOTES.md). Set PRESERVE_LEGACY_PF_TYPO to
# reproduce the original graph 4.1, which divided L3 by L2's power factor.
PRESERVE_LEGACY_PF_TYPO = False
_L3_PF_COLUMN = "L3 PF avg [-]"


def set_legacy_pf_typo(enabled):
    """Choose which power-factor column graph 4.1 divides L3 by."""
    global PRESERVE_LEGACY_PF_TYPO, _L3_PF_COLUMN
    PRESERVE_LEGACY_PF_TYPO = bool(enabled)
    _L3_PF_COLUMN = "L2 PF avg [-]" if enabled else "L3 PF avg [-]"

_SETTINGS = set("""
customer
PathMeasurement
PathRadiation
OUTDIR
Ymax
Ymin
Ydist
Umin
Umax
Udist
Imin
Imax
Idist
THDmin
THDmax
THDdist
PFmin
PFmax
PFdist
Fmin
Fmax
Fdist
Yformat
RateMin
PPV
EtaPV
Offset
deltatime
colorP
colorU
colorPF
colorF
colorA
colorI
colorTHD
""".split())


def configure(**kwargs):
    """Set any configuration value above. Unknown names raise KeyError."""
    g = globals()
    for key, value in kwargs.items():
        if key not in _SETTINGS:
            raise KeyError("unknown setting %r for econ (valid: %s)"
                           % (key, ", ".join(sorted(_SETTINGS))))
        g[key] = value
    g["rate"] = str(int(g["RateMin"])) + "Min"
    out = str(g["OUTDIR"])
    if not out.endswith(("/", "\\", os.sep)):
        out += os.sep
    g["OUTDIR"] = out
    os.makedirs(out, exist_ok=True)
    return current_config()


def current_config():
    """The configuration actually in force, for the audit trail in reports."""
    g = globals()
    return {k: g[k] for k in sorted(_SETTINGS)}


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
    dfr = dfr.rename(columns={dfr.columns[0]: "Time"})
    for col in dfr.columns:
        if col != "Time" and col.upper().startswith("G"):
            dfr = dfr.rename(columns={col: "G [W/m\u00b2]"})
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
TABLES = {}
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


def run_all(progress=None, stop_on_error=False):
    """Run every step in the notebook's order.

    progress: optional callable(index, total, label), called before each step.
    Returns {"files": [...], "tables": {step: [frame, ...]},
              "errors": [(label, message)]}.
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
    return {"files": files, "tables": dict(TABLES), "errors": errors}


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

Pp = 'Pactive total avg [kW]'


# ===========================================================================
# PLOTTING FUNCTIONS -- the notebook's code, unchanged
# ===========================================================================

# Read Measurement Data
#-------------------

def read_measurement_data():
    
    global dfP
    global df
    global dfPL
    global dfU
    global dfI
    global dfTHD
    # Added to global variables
    global dfAPmax
    global dfImax
    
    df = _read_measurement_table(PathMeasurement, sep=';')
    df['Time'] = _to_datetime_dayfirst(df['Time'])
    #df['Time'] = pd.to_datetime(df['Time'], format='%d/%m/%Y %H:%M')
    
    # Measurement time offset correction
    df['Time']=df['Time']+pd.DateOffset(hours=deltatime)

    df.set_index(['Time'],inplace=True)
    df.index.name = 'DateTime'
    df = df.resample(rate).mean(numeric_only=True)
    
    dfP = df[[Pp]].copy()
    dfP = dfP.resample(rate).mean(numeric_only=True)

    dfU = df[['L1 Urms avg [V]','L2 Urms avg [V]','L3 Urms avg [V]']].copy()
    dfPL = df[['L1 Pactive avg [kW]','L2 Pactive avg [kW]','L3 Pactive avg [kW]']].copy()
    dfI = df[['L1 Irms avg [A]','L2 Irms avg [A]','L3 Irms avg [A]']].copy()
    dfTHD = df[['L1 U THD avg [%]','L2 U THD avg [%]','L3 U THD avg [%]']].copy()
    
    # Calculate maximum apparent power per phase in kVA
    dfAPmax = pd.DataFrame()
    dfAPmax['L1 Smax [kVA]'] = (df['L1 Irms max [A]'] * df['L1 Urms max [V]']) / 1000
    dfAPmax['L2 Smax [kVA]'] = (df['L2 Irms max [A]'] * df['L2 Urms max [V]']) / 1000
    dfAPmax['L3 Smax [kVA]'] = (df['L3 Irms max [A]'] * df['L3 Urms max [V]']) / 1000
    
     # Calculate maximum current per phase
    dfImax = pd.DataFrame()
    dfImax['L1 Imax [A]'] = df['L1 Irms max [A]']
    dfImax['L2 Imax [A]'] = df['L2 Irms max [A]']
    dfImax['L3 Imax [A]'] = df['L3 Irms max [A]']

#Plot total period
#-------------------

def plot_total_power_active_total():

    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    #Background colour
    
    ax = plt.axes()
    ax.plot(dfP[Pp], '-', linewidth =0.5, label="consumption")
    #ax.plot(dfP[Pn], '-', linewidth =0.5, label ="feed-in")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Power [kW] \n', fontsize='large')
    ax.set_title('Power consumption ' + customer + ' - total measurement period\n', fontsize='large')
    #ax.legend(loc='best', frameon = True)
    #ax.set_xlim(pd.Timestamp('2018-25-09 00:00'), pd.Timestamp('2018-10-10 00:00'))
    ax.set_ylim(Ymin, Ymax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,12)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'1.1 '+customer+'_power_total period.png', format = 'png')
    display(fig)
    plt.close("all")

def plot_total_power_active_weekly():

   # Power
    # Subplots per week
    #----------------------------------

    #Create dataframe for weekly subplots
    #----------------------------------
    dfPweekS = dfP.copy()
    dfPweekS['Week']='CW ' + dfPweekS.index.isocalendar().week.astype(str)
    dfPweekS.reset_index(inplace = True, drop = False)
    dfPweekS.set_index(['Week'], inplace=True, append = True)
    dfPweekS = dfPweekS.unstack(1)
    
    
    #Plot weekly subplots
    #----------------------------------
    j = int(len(dfPweekS.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*3), facecolor="white")

    for n in range(j):
        # Plot one subplot per week
        ax = fig.add_subplot(j,1,n+1)
        ax.plot(dfPweekS[dfPweekS.columns[n]], dfPweekS[dfPweekS.columns[int(n+j)]], '-', linewidth = 0.5)
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
            #y-axis
        ax.set_ylabel('Power [kW] \n', fontsize='large')
        ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))        
        ax.set_ylim(Ymin,Ymax)
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        #ax.legend(loc='best', frameon = True)

        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_title('Power consumption '+customer+' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfPweekS[dfPweekS.columns[n]].max() - timedelta(days=7),dfPweekS[dfPweekS.columns[n]].max())
        else:
            ax.set_xlim(dfPweekS[dfPweekS.columns[n]].min(),dfPweekS[dfPweekS.columns[n]].min() + timedelta(days=7))
    # Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR+'1.2 '+customer+'_power_weekly subplots.png', format = 'png')
    display(fig)
    plt.close("all")
    
def plot_total_power_active_daily():
        # Power Subplots per day
    #----------------------------------
    
    #Create dataframe for daily subplots
    #----------------------------------
    dfPdayS = dfP.copy()
    dfPdayS['Date']=dfPdayS.index.date
    dfPdayS.reset_index(inplace = True, drop = False)
    dfPdayS.set_index(['Date'], inplace=True, append = True)
    dfPdayS = dfPdayS.unstack(1)
    
    #display(dfPdayS)
    
    #Plot daily subplots
    #----------------------------------
    j = int(len(dfPdayS.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*1.5), facecolor="white")
    fig.suptitle('Power consumption '+customer+' - daily subplots \n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfPdayS[dfPdayS.columns[n]], dfPdayS[dfPdayS.columns[int(n+j)]], '-', linewidth = 0.5, label = dfPdayS[dfPdayS.columns[n]].min().date().strftime('%a %d-%m-%y'))
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))        
        ax.set_ylim(Ymin, Ymax)
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others 
        plt.xticks(rotation=45, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='upper right', frameon = True, handlelength=0)
        
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_xlim(dfPdayS[dfPdayS.columns[n]].max() - timedelta(days=1),dfPdayS[dfPdayS.columns[n]].max())
            ax.set_ylabel('Power [kW] \n', fontsize='large')
        else:
            ax.set_xlim(dfPdayS[dfPdayS.columns[n]].min(),dfPdayS[dfPdayS.columns[n]].min() + timedelta(days=1))
    
    # Formatting only for last plot
    ax.set_xlabel('\n Daytime', fontsize='large')
    plt.subplots_adjust(top=0.96)
    # Save to file
    fig.savefig(OUTDIR+'1.3 '+customer+'_power_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")
    
def plot_phase_power_active_total():   
        # Power per phase
    #Plot total period
    
    #display(dfP.size)
    #dfP = dfP[dfP[Pp] > 0]
    #dfP = dfP.resample(rate).mean(numeric_only=True)
    #display(dfP.size)
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(df['L1 Pactive avg [kW]'], '-', linewidth =0.5, color=colorP[0], label = "Phase L1")
    ax.plot(df['L2 Pactive avg [kW]'], '-', linewidth =0.5, color=colorP[1], label = "Phase L2")
    ax.plot(df['L3 Pactive avg [kW]'], '-', linewidth =0.5, color=colorP[2], label = "Phase L3")
    #ax.plot(dfP[Pn], '-', linewidth =0.5, label ="feed-in")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Power [kW] \n', fontsize='large')
    ax.set_title('Power per phase ' + customer + ' - total measurement period\n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    #ax.set_xlim(pd.Timestamp('2018-25-09 00:00'), pd.Timestamp('2018-10-10 00:00'))
    ax.set_ylim(Ymin, Ymax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,12)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'2.1 '+customer+'_power per phase_total period.png', format = 'png')
    display(fig)
    plt.close("all")

def plot_phase_power_active_weekly():

    # Power per phase
    # Subplots per week
    #----------------------------------

    #Create dataframe for weekly subplots
    #----------------------------------

    dfPaweekS_L1 = df[['L1 Pactive avg [kW]']].copy()
    dfPaweekS_L1['Week']='CW ' + dfPaweekS_L1.index.isocalendar().week.astype(str)
    dfPaweekS_L1.reset_index(inplace = True, drop = False)
    dfPaweekS_L1.set_index(['Week'], inplace=True, append = True)
    dfPaweekS_L1 = dfPaweekS_L1.unstack(1)

    dfPaweekS_L2 = df[['L2 Pactive avg [kW]']].copy()
    dfPaweekS_L2['Week']='CW ' + dfPaweekS_L2.index.isocalendar().week.astype(str)
    dfPaweekS_L2.reset_index(inplace = True, drop = False)
    dfPaweekS_L2.set_index(['Week'], inplace=True, append = True)
    dfPaweekS_L2 = dfPaweekS_L2.unstack(1)
                    
    dfPaweekS_L3 = df[['L3 Pactive avg [kW]']].copy()
    dfPaweekS_L3['Week']='CW ' + dfPaweekS_L3.index.isocalendar().week.astype(str)
    dfPaweekS_L3.reset_index(inplace = True, drop = False)
    dfPaweekS_L3.set_index(['Week'], inplace=True, append = True)
    dfPaweekS_L3 = dfPaweekS_L3.unstack(1)


    #Plot weekly subplots
    #----------------------------------
    j = int(len(dfPaweekS_L1.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*3), facecolor="white")
    for n in range(j):
        # Plot one subplot per week
        ax = fig.add_subplot(j,1,n+1)
        ax.plot(dfPaweekS_L1[dfPaweekS_L1.columns[n]], dfPaweekS_L1[dfPaweekS_L1.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L1', color=colorP[0])
        ax.plot(dfPaweekS_L2[dfPaweekS_L2.columns[n]], dfPaweekS_L2[dfPaweekS_L2.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L2', color=colorP[1])
        ax.plot(dfPaweekS_L3[dfPaweekS_L3.columns[n]], dfPaweekS_L3[dfPaweekS_L3.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L3', color=colorP[2])
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
            #y-axis
        ax.set_ylabel('Power [kW] \n', fontsize='large')       
        ax.set_ylim(Ymin, Ymax)
        ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='best', frameon = True)
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_title('Power per phase '+customer+' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfPaweekS_L1[dfPaweekS_L1.columns[n]].max() - timedelta(days=7),dfPaweekS_L1[dfPaweekS_L1.columns[n]].max())
        else:
            ax.set_xlim(dfPaweekS_L1[dfPaweekS_L1.columns[n]].min(),dfPaweekS_L1[dfPaweekS_L1.columns[n]].min() + timedelta(days=7))
    #Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR+'2.2 '+customer+'_power per phase_weekly subplots.png', format = 'png')
    display(fig)
    plt.close("all")
    
def plot_phase_power_active_daily():    

        # Power per phase Subplots per day
    #----------------------------------
    
    #Create dataframe for daily subplots
    #----------------------------------
    dfPLday = dfPL.copy()
    dfPLday['Date']=dfPLday.index.date
    dfPLday.reset_index(inplace = True, drop = False)
    dfPLday.set_index(['Date'], inplace=True, append = True)
    dfPLday = dfPLday.unstack(1)
    
    #display(dfPLday)
    
    #Plot daily subplots
    #----------------------------------
    j = int(len(dfPLday.columns)/4)
    fig = plt.figure(1, dpi=300, figsize=(12,j*1.5), facecolor="white")
    fig.suptitle('Power per phase '+customer+' - daily subplots \n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfPLday[dfPLday.columns[n]], dfPLday[dfPLday.columns[int(n+j)]], '-', linewidth = 0.5, label = dfPLday[dfPLday.columns[n]].min().date().strftime('%a %d-%m-%y')+'\nPhase L1', color=colorP[0])
        ax.plot(dfPLday[dfPLday.columns[n]], dfPLday[dfPLday.columns[int(n+j*2)]], '-', linewidth = 0.5, label= 'Phase L2', color=colorP[1])
        ax.plot(dfPLday[dfPLday.columns[n]], dfPLday[dfPLday.columns[int(n+j*3)]], '-', linewidth = 0.5, label= 'Phase L3', color=colorP[2])
        
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))        
        ax.set_ylim(Ymin, Ymax)
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others 
        plt.xticks(rotation=45, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='upper right', frameon = True)
        
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_xlim(dfPLday[dfPLday.columns[n]].max() - timedelta(days=1),dfPLday[dfPLday.columns[n]].max())
            ax.set_ylabel('Power [kW] \n', fontsize='large')
        else:
            ax.set_xlim(dfPLday[dfPLday.columns[n]].min(),dfPLday[dfPLday.columns[n]].min() + timedelta(days=1))
    
    # Formatting only for last plot
    ax.set_xlabel('\n Daytime', fontsize='large')
    plt.subplots_adjust(top=0.96)
    # Save to file
    fig.savefig(OUTDIR+'2.3 '+customer+'_power per phase_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")   
    
def plot_total_power_apparent_total():

    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot((df['Pactive total avg [kW]']**2 + df['Qreactive total avg [kvar]']**2)**0.5, '-', linewidth =0.5, label="consumption", color=colorA[2])
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Apparent Power [kVA] \n', fontsize='large')
    ax.set_title('Average apparent Power ' + customer + ' - total measurement period\n', fontsize='large')
    #ax.legend(loc='best', frameon = True)
    #ax.set_xlim(pd.Timestamp('2018-25-09 00:00'), pd.Timestamp('2018-10-10 00:00'))
    ax.set_ylim(Ymin, Ymax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,12)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'3.1 '+customer+'_average apparent power_total period.png', format = 'png')
    display(fig)
    plt.close("all")
    
def plot_total_power_apparent_weekly():

   # Apparent Power
    # Subplots per week
    #----------------------------------

    #Create dataframe for weekly subplots
    #----------------------------------
    dfAPweekS = pd.DataFrame()
    dfAPweekS['Papparent total avg [VA]'] = (df['Pactive total avg [kW]']**2 + df['Qreactive total avg [kvar]']**2)**0.5
    dfAPweekS['Week']='CW ' + dfAPweekS.index.isocalendar().week.astype(str)
    dfAPweekS.reset_index(inplace = True, drop = False)
    dfAPweekS.set_index(['Week'], inplace=True, append = True)
    dfAPweekS = dfAPweekS.unstack(1)
    
    
    #Plot weekly subplots
    #----------------------------------
    j = int(len(dfAPweekS.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*3), facecolor="white")

    for n in range(j):
        # Plot one subplot per week
        ax = fig.add_subplot(j,1,n+1)
        ax.plot(dfAPweekS[dfAPweekS.columns[n]], dfAPweekS[dfAPweekS.columns[int(n+j)]], '-', linewidth = 0.5, color=colorA[2])
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
            #y-axis
        ax.set_ylabel('Apparent Power [kVA] \n', fontsize='large')
        ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))        
        ax.set_ylim(Ymin,Ymax)
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        #ax.legend(loc='best', frameon = True)

        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_title('Average apparent Power '+customer+' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfAPweekS[dfAPweekS.columns[n]].max() - timedelta(days=7),dfAPweekS[dfAPweekS.columns[n]].max())
        else:
            ax.set_xlim(dfAPweekS[dfAPweekS.columns[n]].min(),dfAPweekS[dfAPweekS.columns[n]].min() + timedelta(days=7))
    # Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR+'3.2 '+customer+'_average apparent power_weekly subplots.png', format = 'png')
    display(fig)
    plt.close("all") 
    
def plot_total_power_apparent_daily():
        # Power Subplots per day
    #----------------------------------
    
    #Create dataframe for daily subplots
    #----------------------------------
    dfAPdayS = dfP.copy()
    dfAPdayS = pd.DataFrame()
    dfAPdayS['Papparent total avg [VA]'] = (df['Pactive total avg [kW]']**2 + df['Qreactive total avg [kvar]']**2)**0.5
    dfAPdayS['Date']=dfAPdayS.index.date
    dfAPdayS.reset_index(inplace = True, drop = False)
    dfAPdayS.set_index(['Date'], inplace=True, append = True)
    dfAPdayS = dfAPdayS.unstack(1)
    
    #display(dfAPdayS)
    
    #Plot daily subplots
    #----------------------------------
    j = int(len(dfAPdayS.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*1.5), facecolor="white")
    fig.suptitle('Average apparent Power '+customer+' - daily subplots \n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfAPdayS[dfAPdayS.columns[n]], dfAPdayS[dfAPdayS.columns[int(n+j)]], '-', linewidth = 0.5,color=colorA[2], label = dfAPdayS[dfAPdayS.columns[n]].min().date().strftime('%a %d-%m-%y'))
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))        
        ax.set_ylim(Ymin, Ymax)
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others 
        plt.xticks(rotation=45, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='upper right', frameon = True, handlelength=0)
        
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_xlim(dfAPdayS[dfAPdayS.columns[n]].max() - timedelta(days=1),dfAPdayS[dfAPdayS.columns[n]].max())
            ax.set_ylabel('Apparent Power [kVA] \n', fontsize='large')
        else:
            ax.set_xlim(dfAPdayS[dfAPdayS.columns[n]].min(),dfAPdayS[dfAPdayS.columns[n]].min() + timedelta(days=1))
    
    # Formatting only for last plot
    ax.set_xlabel('\n Daytime', fontsize='large')
    plt.subplots_adjust(top=0.96)
    # Save to file
    fig.savefig(OUTDIR+'3.3 '+customer+'_average apparent power_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")

    
def plot_phase_power_apparent_total():   
        # Apparent Power per phase
    #Plot total period
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(df['L1 Pactive avg [kW]']/df['L1 PF avg [-]'], '-', linewidth =0.5, color=colorA[0], label = "Phase L1")
    ax.plot(df['L2 Pactive avg [kW]']/df['L2 PF avg [-]'], '-', linewidth =0.5, color=colorA[1], label = "Phase L2")
    ax.plot(df['L3 Pactive avg [kW]']/df[_L3_PF_COLUMN], '-', linewidth =0.5, color=colorA[2], label = "Phase L3")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Apparent Power [kVA] \n', fontsize='large')
    ax.set_title('Average apparent Power per phase ' + customer + ' - total measurement period\n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    #ax.set_xlim(pd.Timestamp('2018-25-09 00:00'), pd.Timestamp('2018-10-10 00:00'))
    ax.set_ylim(Ymin, Ymax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,12)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'4.1 '+customer+'_average apparent Power per phase_total period.png', format = 'png')
    display(fig)
    plt.close("all")

def plot_phase_power_apparent_weekly():

    # Apparent Power per phase
    # Subplots per week
    #----------------------------------

    #Create dataframe for weekly subplots
    #----------------------------------

    dfAPweekS_L1 = pd.DataFrame()
    dfAPweekS_L1['L1 Papparent avg [VA]'] = df['L1 Pactive avg [kW]']/df['L1 PF avg [-]']
    #display(dfAPweekS_L1.head())
    dfAPweekS_L1['Week']='CW ' + dfAPweekS_L1.index.isocalendar().week.astype(str)
    dfAPweekS_L1.reset_index(inplace = True, drop = False)
    dfAPweekS_L1.set_index(['Week'], inplace=True, append = True)
    dfAPweekS_L1 = dfAPweekS_L1.unstack(1)
    
    dfAPweekS_L2 = pd.DataFrame()
    dfAPweekS_L2['L2 Papparent avg [VA]'] = df['L2 Pactive avg [kW]']/df['L2 PF avg [-]']
    #dfAPweekS_L2 = df[['L2 Pactive avg [kW]']].copy()
    dfAPweekS_L2['Week']='CW ' + dfAPweekS_L2.index.isocalendar().week.astype(str)
    dfAPweekS_L2.reset_index(inplace = True, drop = False)
    dfAPweekS_L2.set_index(['Week'], inplace=True, append = True)
    dfAPweekS_L2 = dfAPweekS_L2.unstack(1)
    
    dfAPweekS_L3 = pd.DataFrame()
    dfAPweekS_L3['L3 Papparent avg [VA]'] = df['L3 Pactive avg [kW]']/df['L3 PF avg [-]']
    #dfAPweekS_L3 = df[['L3 Pactive avg [kW]']].copy()
    dfAPweekS_L3['Week']='CW ' + dfAPweekS_L3.index.isocalendar().week.astype(str)
    dfAPweekS_L3.reset_index(inplace = True, drop = False)
    dfAPweekS_L3.set_index(['Week'], inplace=True, append = True)
    dfAPweekS_L3 = dfAPweekS_L3.unstack(1)


    #Plot weekly subplots
    #----------------------------------
    j = int(len(dfAPweekS_L1.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*3), facecolor="white")
    for n in range(j):
        # Plot one subplot per week
        ax = fig.add_subplot(j,1,n+1)
        ax.plot(dfAPweekS_L1[dfAPweekS_L1.columns[n]], dfAPweekS_L1[dfAPweekS_L1.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L1', color=colorA[0])
        ax.plot(dfAPweekS_L2[dfAPweekS_L2.columns[n]], dfAPweekS_L2[dfAPweekS_L2.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L2', color=colorA[1])
        ax.plot(dfAPweekS_L3[dfAPweekS_L3.columns[n]], dfAPweekS_L3[dfAPweekS_L3.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L3', color=colorA[2])
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
            #y-axis
        ax.set_ylabel('Apparent Power [kVA] \n', fontsize='large')       
        ax.set_ylim(Ymin, Ymax)
        ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='best', frameon = True)
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_title('Average apparent Power per phase '+customer+' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfAPweekS_L1[dfAPweekS_L1.columns[n]].max() - timedelta(days=7),dfAPweekS_L1[dfAPweekS_L1.columns[n]].max())
        else:
            ax.set_xlim(dfAPweekS_L1[dfAPweekS_L1.columns[n]].min(),dfAPweekS_L1[dfAPweekS_L1.columns[n]].min() + timedelta(days=7))
    #Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR+'4.2 '+customer+'_average apparent Power per phase_weekly subplots.png', format = 'png')
    display(fig)
    plt.close("all")
    
def plot_phase_power_apparent_daily():    
    # Apparent Power per phase Subplots per day
    #----------------------------------
    
    #Create dataframe for daily subplots
    #---------------------------------- 
    dfPAday = pd.DataFrame()   
    dfPAday['L1 Papparent avg [VA]'] = df['L1 Pactive avg [kW]']/df['L1 PF avg [-]']
    dfPAday['L2 Papparent avg [VA]'] = df['L2 Pactive avg [kW]']/df['L2 PF avg [-]']
    dfPAday['L3 Papparent avg [VA]'] = df['L3 Pactive avg [kW]']/df['L3 PF avg [-]']

    
    dfPAday['Date']=dfPAday.index.date
    dfPAday.reset_index(inplace = True, drop = False)
    dfPAday.set_index(['Date'], inplace=True, append = True)
    dfPAday = dfPAday.unstack(1)
    #display(dfPAday)
    
    #Plot daily subplots
    #----------------------------------
    j = int(len(dfPAday.columns)/4)
    fig = plt.figure(1, dpi=300, figsize=(12,j*1.5), facecolor="white")
    fig.suptitle('Average apparent Power per phase '+customer+' - daily subplots \n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfPAday[dfPAday.columns[n]], dfPAday[dfPAday.columns[int(n+j)]], '-', linewidth = 0.5, label = dfPAday[dfPAday.columns[n]].min().date().strftime('%a %d-%m-%y')+'\nPhase L1', color=colorA[0])
        ax.plot(dfPAday[dfPAday.columns[n]], dfPAday[dfPAday.columns[int(n+j*2)]], '-', linewidth = 0.5, label= 'Phase L2', color=colorA[1])
        ax.plot(dfPAday[dfPAday.columns[n]], dfPAday[dfPAday.columns[int(n+j*3)]], '-', linewidth = 0.5, label= 'Phase L3', color=colorA[2])
        
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))        
        ax.set_ylim(Ymin, Ymax)
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others 
        plt.xticks(rotation=45, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='upper right', frameon = True)
        
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_xlim(dfPAday[dfPAday.columns[n]].max() - timedelta(days=1),dfPAday[dfPAday.columns[n]].max())
            ax.set_ylabel('Apparent Power [kVA] \n', fontsize='large')
        else:
            ax.set_xlim(dfPAday[dfPAday.columns[n]].min(),dfPAday[dfPAday.columns[n]].min() + timedelta(days=1))
    
    # Formatting only for last plot
    ax.set_xlabel('\n Daytime', fontsize='large')
    plt.subplots_adjust(top=0.96)
    # Save to file
    fig.savefig(OUTDIR+'4.3 '+customer+'_average apparent Power per phase_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")    
    
    
def plot_phase_voltage_total():     
    # Voltage
    #Plot total period
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(df['L1 Urms avg [V]'], '-', linewidth =0.5, color=colorU[0], label = "Phase L1")
    ax.plot(df['L2 Urms avg [V]'], '-', linewidth =0.5, color=colorU[1], label = "Phase L2")
    ax.plot(df['L3 Urms avg [V]'], '-', linewidth =0.5, color=colorU[2], label = "Phase L3")
    #ax.plot(dfP[Pn], '-', linewidth =0.5, label ="feed-in")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Voltage [V] \n', fontsize='large')
    ax.set_title('Voltage ' + customer + ' - total measurement period\n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    #ax.set_xlim(pd.Timestamp('2018-25-09 00:00'), pd.Timestamp('2018-10-10 00:00'))
    ax.set_ylim(Umin, Umax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Udist))
    #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,12)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'5.1 '+customer+'_voltage_total period.png', format = 'png')
    display(fig)
    plt.close("all")

    
def plot_phase_voltage_weekly():

    # Voltage
    # Subplots per week
    #----------------------------------

    #Create dataframe for weekly subplots
    #----------------------------------
    #dfUweekS_L1 = pd.DataFrame()
    #dfUweekS_L1 = dfU.copy()
    #display(dfUweekS_L1.head())
    dfUweekS_L1 = dfU[['L1 Urms avg [V]']].copy()
    dfUweekS_L1['Week']='CW ' + dfUweekS_L1.index.isocalendar().week.astype(str)
    dfUweekS_L1.reset_index(inplace = True, drop = False)
    dfUweekS_L1.set_index(['Week'], inplace=True, append = True)
    dfUweekS_L1 = dfUweekS_L1.unstack(1)
    
    dfUweekS_L2 = dfU[['L2 Urms avg [V]']].copy()
    dfUweekS_L2['Week']='CW ' + dfUweekS_L2.index.isocalendar().week.astype(str)
    dfUweekS_L2.reset_index(inplace = True, drop = False)
    dfUweekS_L2.set_index(['Week'], inplace=True, append = True)
    dfUweekS_L2 = dfUweekS_L2.unstack(1)
                           
    dfUweekS_L3 = dfU[['L3 Urms avg [V]']].copy()
    dfUweekS_L3['Week']='CW ' + dfUweekS_L3.index.isocalendar().week.astype(str)
    dfUweekS_L3.reset_index(inplace = True, drop = False)
    dfUweekS_L3.set_index(['Week'], inplace=True, append = True)
    dfUweekS_L3 = dfUweekS_L3.unstack(1)


    #Plot weekly subplots
    #----------------------------------
    j = int(len(dfUweekS_L1.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*3), facecolor="white")
    for n in range(j):
        # Plot one subplot per week
        ax = fig.add_subplot(j,1,n+1)
        ax.plot(dfUweekS_L1[dfUweekS_L1.columns[n]], dfUweekS_L1[dfUweekS_L1.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L1', color=colorU[0])
        ax.plot(dfUweekS_L2[dfUweekS_L2.columns[n]], dfUweekS_L2[dfUweekS_L2.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L2', color=colorU[1])
        ax.plot(dfUweekS_L3[dfUweekS_L3.columns[n]], dfUweekS_L3[dfUweekS_L3.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L3', color=colorU[2])
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
            #y-axis
        ax.set_ylabel('Voltage [V] \n', fontsize='large')
        ax.yaxis.set_major_locator(plt.MultipleLocator(Udist))        
        ax.set_ylim(Umin, Umax)
        #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='best', frameon = True)
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_title('Voltage '+customer+' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfUweekS_L1[dfUweekS_L1.columns[n]].max() - timedelta(days=7),dfUweekS_L1[dfUweekS_L1.columns[n]].max())
        else:
            ax.set_xlim(dfUweekS_L1[dfUweekS_L1.columns[n]].min(),dfUweekS_L1[dfUweekS_L1.columns[n]].min() + timedelta(days=7))
    #Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR+'5.2 '+customer+'_voltage_weekly subplots.png', format = 'png')
    display(fig)
    plt.close("all")

    
def plot_phase_voltage_daily(): 
        # Voltage Subplots per day
    #----------------------------------
    
    #Create dataframe for daily subplots
    #----------------------------------
    dfUday = dfU.copy()
    dfUday['Date']=dfUday.index.date
    dfUday.reset_index(inplace = True, drop = False)
    dfUday.set_index(['Date'], inplace=True, append = True)
    dfUday = dfUday.unstack(1)
    
    #display(dfUday)
    
    #Plot daily subplots
    #----------------------------------
    j = int(len(dfUday.columns)/4)
    fig = plt.figure(1, dpi=300, figsize=(12,j*1.5), facecolor="white")
    fig.suptitle('Voltage '+customer+' - daily subplots \n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfUday[dfUday.columns[n]], dfUday[dfUday.columns[int(n+j)]], '-', linewidth = 0.5, label = dfUday[dfUday.columns[n]].min().date().strftime('%a %d-%m-%y')+'\nPhase L1', color=colorU[0])
        ax.plot(dfUday[dfUday.columns[n]], dfUday[dfUday.columns[int(n+j*2)]], '-', linewidth = 0.5, label= 'Phase L2', color=colorU[1])
        ax.plot(dfUday[dfUday.columns[n]], dfUday[dfUday.columns[int(n+j*3)]], '-', linewidth = 0.5, label= 'Phase L3', color=colorU[2])
        
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Udist))        
        ax.set_ylim(Umin, Umax)
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others 
        plt.xticks(rotation=45, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='upper right', frameon = True)
        
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_xlim(dfUday[dfUday.columns[n]].max() - timedelta(days=1),dfUday[dfUday.columns[n]].max())
            ax.set_ylabel('Voltage [V] \n', fontsize='large')
        else:
            ax.set_xlim(dfUday[dfUday.columns[n]].min(),dfUday[dfUday.columns[n]].min() + timedelta(days=1))
    
    # Formatting only for last plot
    ax.set_xlabel('\n Daytime', fontsize='large')
    plt.subplots_adjust(top=0.96)
    # Save to file
    fig.savefig(OUTDIR+'5.3 '+customer+'_voltage_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")

def plot_phase_current_total():     
    # Current
    #Plot total period
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(df['L1 Irms avg [A]'], '-', linewidth =0.5, color=colorI[0], label = "Phase L1")
    ax.plot(df['L2 Irms avg [A]'], '-', linewidth =0.5, color=colorI[1], label = "Phase L2")
    ax.plot(df['L3 Irms avg [A]'], '-', linewidth =0.5, color=colorI[2], label = "Phase L3")
    #ax.plot(dfP[Pn], '-', linewidth =0.5, label ="feed-in")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Current [A] \n', fontsize='large')
    ax.set_title('Average current ' + customer + ' - total measurement period\n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    #ax.set_xlim(pd.Timestamp('2018-25-09 00:00'), pd.Timestamp('2018-10-10 00:00'))
    ax.set_ylim(Imin, Imax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Idist))
    #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,12)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'6.1 '+customer+'_average current_total period.png', format = 'png')
    display(fig)
    plt.close("all")    
    
def plot_phase_current_weekly():

    # Current
    # Subplots per week
    #----------------------------------

    #Create dataframe for weekly subplots
    #----------------------------------
    #dfIweekS_L1 = pd.DataFrame()
    #dfIweekS_L1 = dfU.copy()
    #display(dfIweekS_L1.head())
    dfIweekS_L1 = dfI[['L1 Irms avg [A]']].copy()
    dfIweekS_L1['Week']='CW ' + dfIweekS_L1.index.isocalendar().week.astype(str)
    dfIweekS_L1.reset_index(inplace = True, drop = False)
    dfIweekS_L1.set_index(['Week'], inplace=True, append = True)
    dfIweekS_L1 = dfIweekS_L1.unstack(1)
    
    dfIweekS_L2 = dfI[['L2 Irms avg [A]']].copy()
    dfIweekS_L2['Week']='CW ' + dfIweekS_L2.index.isocalendar().week.astype(str)
    dfIweekS_L2.reset_index(inplace = True, drop = False)
    dfIweekS_L2.set_index(['Week'], inplace=True, append = True)
    dfIweekS_L2 = dfIweekS_L2.unstack(1)
                           
    dfIweekS_L3 = dfI[['L3 Irms avg [A]']].copy()
    dfIweekS_L3['Week']='CW ' + dfIweekS_L3.index.isocalendar().week.astype(str)
    dfIweekS_L3.reset_index(inplace = True, drop = False)
    dfIweekS_L3.set_index(['Week'], inplace=True, append = True)
    dfIweekS_L3 = dfIweekS_L3.unstack(1)


    #Plot weekly subplots
    #----------------------------------
    j = int(len(dfIweekS_L1.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*3), facecolor="white")
    for n in range(j):
        # Plot one subplot per week
        ax = fig.add_subplot(j,1,n+1)
        ax.plot(dfIweekS_L1[dfIweekS_L1.columns[n]], dfIweekS_L1[dfIweekS_L1.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L1', color=colorI[0])
        ax.plot(dfIweekS_L2[dfIweekS_L2.columns[n]], dfIweekS_L2[dfIweekS_L2.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L2', color=colorI[1])
        ax.plot(dfIweekS_L3[dfIweekS_L3.columns[n]], dfIweekS_L3[dfIweekS_L3.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L3', color=colorI[2])
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
            #y-axis
        ax.set_ylabel('Current [A] \n', fontsize='large')
        ax.yaxis.set_major_locator(plt.MultipleLocator(Idist))        
        ax.set_ylim(Imin, Imax)
        #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='best', frameon = True)
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_title('Average current '+customer+' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfIweekS_L1[dfIweekS_L1.columns[n]].max() - timedelta(days=7),dfIweekS_L1[dfIweekS_L1.columns[n]].max())
        else:
            ax.set_xlim(dfIweekS_L1[dfIweekS_L1.columns[n]].min(),dfIweekS_L1[dfIweekS_L1.columns[n]].min() + timedelta(days=7))
    #Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR+'6.2 '+customer+'_average current_weekly subplots.png', format = 'png')
    display(fig)
    plt.close("all")    
    
def plot_phase_current_daily(): 
        # Current Subplots per day
    #----------------------------------
    
    #Create dataframe for daily subplots
    #----------------------------------
    dfIday = dfI.copy()
    dfIday['Date']=dfIday.index.date
    dfIday.reset_index(inplace = True, drop = False)
    dfIday.set_index(['Date'], inplace=True, append = True)
    dfIday = dfIday.unstack(1)
    
    #display(dfIday)
    
    #Plot daily subplots
    #----------------------------------
    j = int(len(dfIday.columns)/4)
    fig = plt.figure(1, dpi=300, figsize=(12,j*1.5), facecolor="white")
    fig.suptitle('Average current '+customer+' - daily subplots \n\n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfIday[dfIday.columns[n]], dfIday[dfIday.columns[int(n+j)]], '-', linewidth = 0.5, label = dfIday[dfIday.columns[n]].min().date().strftime('%a %d-%m-%y')+'\nPhase L1', color=colorI[0])
        ax.plot(dfIday[dfIday.columns[n]], dfIday[dfIday.columns[int(n+j*2)]], '-', linewidth = 0.5, label= 'Phase L2', color=colorI[1])
        ax.plot(dfIday[dfIday.columns[n]], dfIday[dfIday.columns[int(n+j*3)]], '-', linewidth = 0.5, label= 'Phase L3', color=colorI[2])
        
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Idist))        
        ax.set_ylim(Imin, Imax)
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others 
        plt.xticks(rotation=45, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='upper right', frameon = True)
        
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_xlim(dfIday[dfIday.columns[n]].max() - timedelta(days=1),dfIday[dfIday.columns[n]].max())
            ax.set_ylabel('Current [A] \n', fontsize='large')
        else:
            ax.set_xlim(dfIday[dfIday.columns[n]].min(),dfIday[dfIday.columns[n]].min() + timedelta(days=1))
    
    # Formatting only for last plot
    ax.set_xlabel('\n Daytime', fontsize='large')
    plt.subplots_adjust(top=0.96)
    # Save to file
    fig.savefig(OUTDIR+'6.3 '+customer+'_ average current_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")    
    
    
    
    
    
    
    
    
    
    
    
    
    
    #ADDED SECTION
    
def plot_total_max_apparent_power_total():
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    # Sum the maximum apparent power across all phases
    total_max_apparent = dfAPmax['L1 Smax [kVA]'] + dfAPmax['L2 Smax [kVA]'] + dfAPmax['L3 Smax [kVA]']
    ax.plot(total_max_apparent, '-', linewidth=0.5, label="Total Max Apparent Power", color=colorA[2])
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Max apparent power [kVA] \n', fontsize='large')
    ax.set_title('Total maximum apparent power ' + customer + ' - total measurement period\n', fontsize='large')
    ax.legend(loc='best', frameon=True)
    ax.set_ylim(Ymin, Ymax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y * Yformat)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR + '3.4 ' + customer + '_total_max_apparent_power_total_period.png', format='png')
    display(fig)
    plt.close("all")
    
def plot_phase_max_apparent_power_total():
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(dfAPmax['L1 Smax [kVA]'], '-', linewidth=0.5, color=colorA[0], label="Phase L1")
    ax.plot(dfAPmax['L2 Smax [kVA]'], '-', linewidth=0.5, color=colorA[1], label="Phase L2")
    ax.plot(dfAPmax['L3 Smax [kVA]'], '-', linewidth=0.5, color=colorA[2], label="Phase L3")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Max apparent power [kVA] \n', fontsize='large')
    ax.set_title('Maximum apparent power per phase ' + customer + ' - total measurement period\n', fontsize='large')
    ax.legend(loc='best', frameon=True)
    ax.set_ylim(Ymin, Ymax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y * Yformat)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR + '6.4 ' + customer + '_max apparent power_total period.png', format='png')
    display(fig)
    plt.close("all")

def plot_phase_max_apparent_power_weekly():
    # Maximum Apparent Power per phase
    # Subplots per week
    #----------------------------------

    # Create dataframe for weekly subplots
    #----------------------------------
    dfAPmaxweekS_L1 = dfAPmax[['L1 Smax [kVA]']].copy()
    dfAPmaxweekS_L1['Week'] = 'CW ' + dfAPmaxweekS_L1.index.isocalendar().week.astype(str)
    dfAPmaxweekS_L1.reset_index(inplace=True, drop=False)
    dfAPmaxweekS_L1.set_index(['Week'], inplace=True, append=True)
    dfAPmaxweekS_L1 = dfAPmaxweekS_L1.unstack(1)

    dfAPmaxweekS_L2 = dfAPmax[['L2 Smax [kVA]']].copy()
    dfAPmaxweekS_L2['Week'] = 'CW ' + dfAPmaxweekS_L2.index.isocalendar().week.astype(str)
    dfAPmaxweekS_L2.reset_index(inplace=True, drop=False)
    dfAPmaxweekS_L2.set_index(['Week'], inplace=True, append=True)
    dfAPmaxweekS_L2 = dfAPmaxweekS_L2.unstack(1)

    dfAPmaxweekS_L3 = dfAPmax[['L3 Smax [kVA]']].copy()
    dfAPmaxweekS_L3['Week'] = 'CW ' + dfAPmaxweekS_L3.index.isocalendar().week.astype(str)
    dfAPmaxweekS_L3.reset_index(inplace=True, drop=False)
    dfAPmaxweekS_L3.set_index(['Week'], inplace=True, append=True)
    dfAPmaxweekS_L3 = dfAPmaxweekS_L3.unstack(1)

    # Plot weekly subplots
    #----------------------------------
    j = int(len(dfAPmaxweekS_L1.columns) / 2)
    fig = plt.figure(1, dpi=300, figsize=(12, j * 3), facecolor="white")
    for n in range(j):
        # Plot one subplot per week
        ax = fig.add_subplot(j, 1, n + 1)
        ax.plot(dfAPmaxweekS_L1[dfAPmaxweekS_L1.columns[n]], dfAPmaxweekS_L1[dfAPmaxweekS_L1.columns[int(n + j)]], '-', linewidth=0.5, label='Phase L1', color=colorA[0])
        ax.plot(dfAPmaxweekS_L2[dfAPmaxweekS_L2.columns[n]], dfAPmaxweekS_L2[dfAPmaxweekS_L2.columns[int(n + j)]], '-', linewidth=0.5, label='Phase L2', color=colorA[1])
        ax.plot(dfAPmaxweekS_L3[dfAPmaxweekS_L3.columns[n]], dfAPmaxweekS_L3[dfAPmaxweekS_L3.columns[int(n + j)]], '-', linewidth=0.5, label='Phase L3', color=colorA[2])
        # General formatting for all subplots
        # x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
        # y-axis
        ax.set_ylabel('Max apparent power [kVA] \n', fontsize='large')
        ax.set_ylim(Ymin, Ymax)
        ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y * Yformat)))
        # Others
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='best', frameon=True)
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_title('Maximum apparent power per phase ' + customer + ' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfAPmaxweekS_L1[dfAPmaxweekS_L1.columns[n]].max() - timedelta(days=7), dfAPmaxweekS_L1[dfAPmaxweekS_L1.columns[n]].max())
        else:
            ax.set_xlim(dfAPmaxweekS_L1[dfAPmaxweekS_L1.columns[n]].min(), dfAPmaxweekS_L1[dfAPmaxweekS_L1.columns[n]].min() + timedelta(days=7))
    # Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR + '6.5 ' + customer + '_max apparent power_weekly subplots.png', format='png')
    display(fig)
    plt.close("all")

def plot_phase_max_apparent_power_daily():
    # Maximum Apparent Power per phase Subplots per day
    #----------------------------------

    # Create dataframe for daily subplots
    #----------------------------------
    dfAPmaxday = dfAPmax.copy()
    dfAPmaxday['Date'] = dfAPmaxday.index.date
    dfAPmaxday.reset_index(inplace=True, drop=False)
    dfAPmaxday.set_index(['Date'], inplace=True, append=True)
    dfAPmaxday = dfAPmaxday.unstack(1)

    # Plot daily subplots
    #----------------------------------
    j = int(len(dfAPmaxday.columns) / 4)
    fig = plt.figure(1, dpi=300, figsize=(12, j * 1.5), facecolor="white")
    fig.suptitle('Maximum apparent power per phase ' + customer + ' - daily subplots \n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j / 2), 2, n + 1)
        ax.plot(dfAPmaxday[dfAPmaxday.columns[n]], dfAPmaxday[dfAPmaxday.columns[int(n + j)]], '-', linewidth=0.5, label=dfAPmaxday[dfAPmaxday.columns[n]].min().date().strftime('%a %d-%m-%y') + '\nPhase L1', color=colorA[0])
        ax.plot(dfAPmaxday[dfAPmaxday.columns[n]], dfAPmaxday[dfAPmaxday.columns[int(n + j * 2)]], '-', linewidth=0.5, label='Phase L2', color=colorA[1])
        ax.plot(dfAPmaxday[dfAPmaxday.columns[n]], dfAPmaxday[dfAPmaxday.columns[int(n + j * 3)]], '-', linewidth=0.5, label='Phase L3', color=colorA[2])
        # General formatting for all subplots
        # x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0, 24, 2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
        # y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
        ax.set_ylim(Ymin, Ymax)
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y * Yformat)))
        # Others
        plt.xticks(rotation=45, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='upper right', frameon=True)
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_xlim(dfAPmaxday[dfAPmaxday.columns[n]].max() - timedelta(days=1), dfAPmaxday[dfAPmaxday.columns[n]].max())
            ax.set_ylabel('Max apparent power [kVA] \n', fontsize='large')
        else:
            ax.set_xlim(dfAPmaxday[dfAPmaxday.columns[n]].min(), dfAPmaxday[dfAPmaxday.columns[n]].min() + timedelta(days=1))
    # Formatting only for last plot
    ax.set_xlabel('\n Daytime', fontsize='large')
    plt.subplots_adjust(top=0.96)
    # Save to file
    fig.savefig(OUTDIR + '6.6 ' + customer + '_max apparent power_daily subplots.png', format='png')
    display(fig)
    plt.close("all")
    
    # New plotting functions for maximum current
def plot_total_max_current_total():
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    # Sum the maximum current across all phases
    total_max_current = dfImax['L1 Imax [A]'] + dfImax['L2 Imax [A]'] + dfImax['L3 Imax [A]']
    ax.plot(total_max_current, '-', linewidth=0.5, label="Total Max Current", color=colorI[2])
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Max current [A] \n', fontsize='large')
    ax.set_title('Total maximum Current ' + customer + ' - total measurement period\n', fontsize='large')
    ax.legend(loc='best', frameon=True)
    ax.set_ylim(Imin, Imax)  # Consistent with plot_phase_current_total
    ax.yaxis.set_major_locator(plt.MultipleLocator(Idist))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR + '6.10 ' + customer + '_total_max_current_total_period.png', format='png')
    display(fig)
    plt.close("all")
    
def plot_phase_max_current_total():
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(dfImax['L1 Imax [A]'], '-', linewidth=0.5, color=colorI[0], label="Phase L1")
    ax.plot(dfImax['L2 Imax [A]'], '-', linewidth=0.5, color=colorI[1], label="Phase L2")
    ax.plot(dfImax['L3 Imax [A]'], '-', linewidth=0.5, color=colorI[2], label="Phase L3")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Max current [A] \n', fontsize='large')
    ax.set_title('Maximum current per phase ' + customer + ' - total measurement period\n', fontsize='large')
    ax.legend(loc='best', frameon=True)
    ax.set_ylim(Imin, Imax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Idist))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR + '6.7 ' + customer + '_max current_total period.png', format='png')
    display(fig)
    plt.close("all")

def plot_phase_max_current_weekly():
    # Maximum Current per phase
    # Subplots per week
    #----------------------------------

    # Create dataframe for weekly subplots
    #----------------------------------
    dfImaxweekS_L1 = dfImax[['L1 Imax [A]']].copy()
    dfImaxweekS_L1['Week'] = 'CW ' + dfImaxweekS_L1.index.isocalendar().week.astype(str)
    dfImaxweekS_L1.reset_index(inplace=True, drop=False)
    dfImaxweekS_L1.set_index(['Week'], inplace=True, append=True)
    dfImaxweekS_L1 = dfImaxweekS_L1.unstack(1)

    dfImaxweekS_L2 = dfImax[['L2 Imax [A]']].copy()
    dfImaxweekS_L2['Week'] = 'CW ' + dfImaxweekS_L2.index.isocalendar().week.astype(str)
    dfImaxweekS_L2.reset_index(inplace=True, drop=False)
    dfImaxweekS_L2.set_index(['Week'], inplace=True, append=True)
    dfImaxweekS_L2 = dfImaxweekS_L2.unstack(1)

    dfImaxweekS_L3 = dfImax[['L3 Imax [A]']].copy()
    dfImaxweekS_L3['Week'] = 'CW ' + dfImaxweekS_L3.index.isocalendar().week.astype(str)
    dfImaxweekS_L3.reset_index(inplace=True, drop=False)
    dfImaxweekS_L3.set_index(['Week'], inplace=True, append=True)
    dfImaxweekS_L3 = dfImaxweekS_L3.unstack(1)

    # Plot weekly subplots
    #----------------------------------
    j = int(len(dfImaxweekS_L1.columns) / 2)
    fig = plt.figure(1, dpi=300, figsize=(12, j * 3), facecolor="white")
    for n in range(j):
        # Plot one subplot per week
        ax = fig.add_subplot(j, 1, n + 1)
        ax.plot(dfImaxweekS_L1[dfImaxweekS_L1.columns[n]], dfImaxweekS_L1[dfImaxweekS_L1.columns[int(n + j)]], '-', linewidth=0.5, label='Phase L1', color=colorI[0])
        ax.plot(dfImaxweekS_L2[dfImaxweekS_L2.columns[n]], dfImaxweekS_L2[dfImaxweekS_L2.columns[int(n + j)]], '-', linewidth=0.5, label='Phase L2', color=colorI[1])
        ax.plot(dfImaxweekS_L3[dfImaxweekS_L3.columns[n]], dfImaxweekS_L3[dfImaxweekS_L3.columns[int(n + j)]], '-', linewidth=0.5, label='Phase L3', color=colorI[2])
        # General formatting for all subplots
        # x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
        # y-axis
        ax.set_ylabel('Max current [A] \n', fontsize='large')
        ax.set_ylim(Imin, Imax)
        ax.yaxis.set_major_locator(plt.MultipleLocator(Idist))
        # Others
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='best', frameon=True)
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_title('Maximum current per phase ' + customer + ' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfImaxweekS_L1[dfImaxweekS_L1.columns[n]].max() - timedelta(days=7), dfImaxweekS_L1[dfImaxweekS_L1.columns[n]].max())
        else:
            ax.set_xlim(dfImaxweekS_L1[dfImaxweekS_L1.columns[n]].min(), dfImaxweekS_L1[dfImaxweekS_L1.columns[n]].min() + timedelta(days=7))
    # Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR + '6.8 ' + customer + '_max current_weekly subplots.png', format='png')
    display(fig)
    plt.close("all")

def plot_phase_max_current_daily():
    # Maximum Current per phase Subplots per day
    #----------------------------------

    # Create dataframe for daily subplots
    #----------------------------------
    dfImaxday = dfImax.copy()
    dfImaxday['Date'] = dfImaxday.index.date
    dfImaxday.reset_index(inplace=True, drop=False)
    dfImaxday.set_index(['Date'], inplace=True, append=True)
    dfImaxday = dfImaxday.unstack(1)

    # Plot daily subplots
    #----------------------------------
    j = int(len(dfImaxday.columns) / 4)
    fig = plt.figure(1, dpi=300, figsize=(12, j * 1.5), facecolor="white")
    fig.suptitle('Maximum current per phase ' + customer + ' - daily subplots \n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j / 2), 2, n + 1)
        ax.plot(dfImaxday[dfImaxday.columns[n]], dfImaxday[dfImaxday.columns[int(n + j)]], '-', linewidth=0.5, label=dfImaxday[dfImaxday.columns[n]].min().date().strftime('%a %d-%m-%y') + '\nPhase L1', color=colorI[0])
        ax.plot(dfImaxday[dfImaxday.columns[n]], dfImaxday[dfImaxday.columns[int(n + j * 2)]], '-', linewidth=0.5, label='Phase L2', color=colorI[1])
        ax.plot(dfImaxday[dfImaxday.columns[n]], dfImaxday[dfImaxday.columns[int(n + j * 3)]], '-', linewidth=0.5, label='Phase L3', color=colorI[2])
        # General formatting for all subplots
        # x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0, 24, 2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
        # y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Idist))
        ax.set_ylim(Imin, Imax)
        # Others
        plt.xticks(rotation=45, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='upper right', frameon=True)
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_xlim(dfImaxday[dfImaxday.columns[n]].max() - timedelta(days=1), dfImaxday[dfImaxday.columns[n]].max())
            ax.set_ylabel('Max current [A] \n', fontsize='large')
        else:
            ax.set_xlim(dfImaxday[dfImaxday.columns[n]].min(), dfImaxday[dfImaxday.columns[n]].min() + timedelta(days=1))
    # Formatting only for last plot
    ax.set_xlabel('\n Daytime', fontsize='large')
    plt.subplots_adjust(top=0.96)
    # Save to file
    fig.savefig(OUTDIR + '6.9 ' + customer + '_max current_daily subplots.png', format='png')
    display(fig)
    plt.close("all")

    #End of added section
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
def plot_phase_THD_total():     
    # Voltage THD
    #Plot total period
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(df['L1 U THD avg [%]'], '-', linewidth =0.5, color=colorTHD[0], label = "Phase L1")
    ax.plot(df['L2 U THD avg [%]'], '-', linewidth =0.5, color=colorTHD[1], label = "Phase L2")
    ax.plot(df['L3 U THD avg [%]'], '-', linewidth =0.5, color=colorTHD[2], label = "Phase L3")
    #ax.plot(dfP[Pn], '-', linewidth =0.5, label ="feed-in")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Voltage THD [%] \n', fontsize='large')
    ax.set_title('Voltage THD ' + customer + ' - total measurement period\n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    #ax.set_xlim(pd.Timestamp('2018-25-09 00:00'), pd.Timestamp('2018-10-10 00:00'))
    ax.set_ylim(THDmin, THDmax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(THDdist))
    #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,12)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'7.1 '+customer+'_Voltage THD_total period.png', format = 'png')
    display(fig)
    plt.close("all")    
    
def plot_phase_THD_weekly():

    # Voltage THD
    # Subplots per week
    #----------------------------------

    #Create dataframe for weekly subplots
    #----------------------------------
    #dfTHDweekS_L1 = pd.DataFrame()
    #dfTHDweekS_L1 = dfTHD.copy()
    #display(dfTHDweekS_L1.head())
    dfTHDweekS_L1 = dfTHD[['L1 U THD avg [%]']].copy()
    dfTHDweekS_L1['Week']='CW ' + dfTHDweekS_L1.index.isocalendar().week.astype(str)
    dfTHDweekS_L1.reset_index(inplace = True, drop = False)
    dfTHDweekS_L1.set_index(['Week'], inplace=True, append = True)
    dfTHDweekS_L1 = dfTHDweekS_L1.unstack(1)
    
    dfTHDweekS_L2 = dfTHD[['L2 U THD avg [%]']].copy()
    dfTHDweekS_L2['Week']='CW ' + dfTHDweekS_L2.index.isocalendar().week.astype(str)
    dfTHDweekS_L2.reset_index(inplace = True, drop = False)
    dfTHDweekS_L2.set_index(['Week'], inplace=True, append = True)
    dfTHDweekS_L2 = dfTHDweekS_L2.unstack(1)
                           
    dfTHDweekS_L3 = dfTHD[['L3 U THD avg [%]']].copy()
    dfTHDweekS_L3['Week']='CW ' + dfTHDweekS_L3.index.isocalendar().week.astype(str)
    dfTHDweekS_L3.reset_index(inplace = True, drop = False)
    dfTHDweekS_L3.set_index(['Week'], inplace=True, append = True)
    dfTHDweekS_L3 = dfTHDweekS_L3.unstack(1)


    #Plot weekly subplots
    #----------------------------------
    j = int(len(dfTHDweekS_L1.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*3), facecolor="white")
    for n in range(j):
        # Plot one subplot per week
        ax = fig.add_subplot(j,1,n+1)
        ax.plot(dfTHDweekS_L1[dfTHDweekS_L1.columns[n]], dfTHDweekS_L1[dfTHDweekS_L1.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L1', color=colorTHD[0])
        ax.plot(dfTHDweekS_L2[dfTHDweekS_L2.columns[n]], dfTHDweekS_L2[dfTHDweekS_L2.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L2', color=colorTHD[1])
        ax.plot(dfTHDweekS_L3[dfTHDweekS_L3.columns[n]], dfTHDweekS_L3[dfTHDweekS_L3.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L3', color=colorTHD[2])
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
            #y-axis
        ax.set_ylabel('Voltage THD [%] \n', fontsize='large')
        ax.yaxis.set_major_locator(plt.MultipleLocator(THDdist))        
        ax.set_ylim(THDmin, THDmax)
        #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='best', frameon = True)
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_title('Voltage THD '+customer+' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfTHDweekS_L1[dfTHDweekS_L1.columns[n]].max() - timedelta(days=7),dfTHDweekS_L1[dfTHDweekS_L1.columns[n]].max())
        else:
            ax.set_xlim(dfTHDweekS_L1[dfTHDweekS_L1.columns[n]].min(),dfTHDweekS_L1[dfTHDweekS_L1.columns[n]].min() + timedelta(days=7))
    #Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR+'7.2 '+customer+'_Voltage THD_weekly subplots.png', format = 'png')
    display(fig)
    plt.close("all")    
    
def plot_phase_THD_daily(): 
        # Current Subplots per day
    #----------------------------------
    
    #Create dataframe for daily subplots
    #----------------------------------
    dfTHDday = dfTHD.copy()
    dfTHDday['Date']=dfTHDday.index.date
    dfTHDday.reset_index(inplace = True, drop = False)
    dfTHDday.set_index(['Date'], inplace=True, append = True)
    dfTHDday = dfTHDday.unstack(1)
    
    #display(dfTHDday)
    
    #Plot daily subplots
    #----------------------------------
    j = int(len(dfTHDday.columns)/4)
    fig = plt.figure(1, dpi=300, figsize=(12,j*1.5), facecolor="white")
    fig.suptitle('Voltage THD '+customer+' - daily subplots \n\n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfTHDday[dfTHDday.columns[n]], dfTHDday[dfTHDday.columns[int(n+j)]], '-', linewidth = 0.5, label = dfTHDday[dfTHDday.columns[n]].min().date().strftime('%a %d-%m-%y')+'\nPhase L1', color=colorTHD[0])
        ax.plot(dfTHDday[dfTHDday.columns[n]], dfTHDday[dfTHDday.columns[int(n+j*2)]], '-', linewidth = 0.5, label= 'Phase L2', color=colorTHD[1])
        ax.plot(dfTHDday[dfTHDday.columns[n]], dfTHDday[dfTHDday.columns[int(n+j*3)]], '-', linewidth = 0.5, label= 'Phase L3', color=colorTHD[2])
        
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(THDdist))        
        ax.set_ylim(THDmin, THDmax)
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others 
        plt.xticks(rotation=45, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='upper right', frameon = True)
        
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_xlim(dfTHDday[dfTHDday.columns[n]].max() - timedelta(days=1),dfTHDday[dfTHDday.columns[n]].max())
            ax.set_ylabel('Voltage THD [%] \n', fontsize='large')
        else:
            ax.set_xlim(dfTHDday[dfTHDday.columns[n]].min(),dfTHDday[dfTHDday.columns[n]].min() + timedelta(days=1))
    
    # Formatting only for last plot
    ax.set_xlabel('\n Daytime', fontsize='large')
    plt.subplots_adjust(top=0.96)
    # Save to file
    fig.savefig(OUTDIR+'7.3 '+customer+'_Voltage THD_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")    
    
def plot_phase_PF_total():     
    # Power factor
    #Plot total period
    
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(df['L1 PF avg [-]'], '-', linewidth =0.5, color=colorPF[0], label = "Phase L1")
    ax.plot(df['L2 PF avg [-]'], '-', linewidth =0.5, color=colorPF[1], label = "Phase L2")
    ax.plot(df['L3 PF avg [-]'], '-', linewidth =0.5, color=colorPF[2], label = "Phase L3")
    #ax.plot(dfP[Pn], '-', linewidth =0.5, label ="feed-in")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Power Factor [-] \n', fontsize='large')
    ax.set_title('Power Factor ' + customer + ' - total measurement period\n', fontsize='large')
    #ax.legend(loc='best', frameon = True)
    ax.legend(loc='lower right', frameon = True)
    #ax.set_xlim(pd.Timestamp('2018-25-09 00:00'), pd.Timestamp('2018-10-10 00:00'))
    ax.set_ylim(PFmin, PFmax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(PFdist))
    #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,12)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'8.1 '+customer+'_power factor_total period.png', format = 'png')
    display(fig)
    plt.close("all")


    
def plot_phase_PF_weekly():
    # Power Factor
    # Subplots per week
    #----------------------------------

    #Create dataframe for weekly subplots
    #----------------------------------

    dfPFweekS_L1 = df[['L1 PF avg [-]']].copy()
    dfPFweekS_L1['Week']='CW ' + dfPFweekS_L1.index.isocalendar().week.astype(str)
    dfPFweekS_L1.reset_index(inplace = True, drop = False)
    dfPFweekS_L1.set_index(['Week'], inplace=True, append = True)
    dfPFweekS_L1 = dfPFweekS_L1.unstack(1)
    
    dfPFweekS_L2 = df[['L2 PF avg [-]']].copy()
    dfPFweekS_L2['Week']='CW ' + dfPFweekS_L2.index.isocalendar().week.astype(str)
    dfPFweekS_L2.reset_index(inplace = True, drop = False)
    dfPFweekS_L2.set_index(['Week'], inplace=True, append = True)
    dfPFweekS_L2 = dfPFweekS_L2.unstack(1)
                         
    dfPFweekS_L3 = df[['L3 PF avg [-]']].copy()
    dfPFweekS_L3['Week']='CW ' + dfPFweekS_L3.index.isocalendar().week.astype(str)
    dfPFweekS_L3.reset_index(inplace = True, drop = False)
    dfPFweekS_L3.set_index(['Week'], inplace=True, append = True)
    dfPFweekS_L3 = dfPFweekS_L3.unstack(1)


    #Plot weekly subplots
    #----------------------------------
    j = int(len(dfPFweekS_L1.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*3), facecolor="white")
    for n in range(j):
        # Plot one subplot per week
        ax = fig.add_subplot(j,1,n+1)
        ax.plot(dfPFweekS_L1[dfPFweekS_L1.columns[n]], dfPFweekS_L1[dfPFweekS_L1.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L1', color=colorPF[0])
        ax.plot(dfPFweekS_L2[dfPFweekS_L2.columns[n]], dfPFweekS_L2[dfPFweekS_L2.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L2', color=colorPF[1])
        ax.plot(dfPFweekS_L3[dfPFweekS_L3.columns[n]], dfPFweekS_L3[dfPFweekS_L3.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase L3', color=colorPF[2])
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
            #y-axis
        ax.set_ylabel('Power Factor [-] \n', fontsize='large')
        ax.yaxis.set_major_locator(plt.MultipleLocator(PFdist))        
        ax.set_ylim(PFmin, PFmax)
        #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='lower right', frameon = True)
        #ax.legend(loc='best', frameon = True)
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_title('Power Factor '+customer+' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfPFweekS_L1[dfPFweekS_L1.columns[n]].max() - timedelta(days=7),dfPFweekS_L1[dfPFweekS_L1.columns[n]].max())
        else:
            ax.set_xlim(dfPFweekS_L1[dfPFweekS_L1.columns[n]].min(),dfPFweekS_L1[dfPFweekS_L1.columns[n]].min() + timedelta(days=7))
    #Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR+'8.2 '+customer+'_power factor_weekly subplots.png', format = 'png')
    display(fig)
    plt.close("all")
    
def plot_phase_PF_daily(): 
    # Power Factor Subplots per day
    #----------------------------------
    
    #Create dataframe for daily subplots
    #----------------------------------
    dfPFday = df[['L1 PF avg [-]','L2 PF avg [-]','L3 PF avg [-]']].copy()
    #dfPFday = dfP.copy()
    dfPFday['Date']=dfPFday.index.date
    dfPFday.reset_index(inplace = True, drop = False)
    dfPFday.set_index(['Date'], inplace=True, append = True)
    dfPFday = dfPFday.unstack(1)
    

    
    #Plot daily subplots
    #----------------------------------
    j = int(len(dfPFday.columns)/4)
    fig = plt.figure(1, dpi=300, figsize=(12,j*1.5), facecolor="white")
    fig.suptitle('Power Factor '+customer+' - daily subplots \n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfPFday[dfPFday.columns[n]], dfPFday[dfPFday.columns[int(n+j)]], '-', linewidth = 0.5, label = dfPFday[dfPFday.columns[n]].min().date().strftime('%a %d-%m-%y')+'\nPhase L1', color=colorPF[0])
        ax.plot(dfPFday[dfPFday.columns[n]], dfPFday[dfPFday.columns[int(n+j*2)]], '-', linewidth = 0.5, label= 'Phase L2', color=colorPF[1])
        ax.plot(dfPFday[dfPFday.columns[n]], dfPFday[dfPFday.columns[int(n+j*3)]], '-', linewidth = 0.5, label= 'Phase L3', color=colorPF[2])
        
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(PFdist))        
        ax.set_ylim(PFmin, PFmax)
        #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others 
        plt.xticks(rotation=45, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='lower right', frameon = True)
        
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_xlim(dfPFday[dfPFday.columns[n]].max() - timedelta(days=1),dfPFday[dfPFday.columns[n]].max())
            ax.set_ylabel('Power Factor [-] \n', fontsize='large')
        else:
            ax.set_xlim(dfPFday[dfPFday.columns[n]].min(),dfPFday[dfPFday.columns[n]].min() + timedelta(days=1))
    
    # Formatting only for last plot
    ax.set_xlabel('\n Daytime', fontsize='large')
    plt.subplots_adjust(top=0.96)
    # Save to file
    fig.savefig(OUTDIR+'8.3 '+customer+'_power factor_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")
    
def plot_frequency_total():

    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(df['Frequency [Hz]'], '-', linewidth =0.5, label="frequency", color=colorF[2])
    #ax.plot(dfP[Pn], '-', linewidth =0.5, label ="feed-in")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Frequency [Hz] \n', fontsize='large')
    ax.set_title('Frequency ' + customer + ' - total measurement period\n', fontsize='large')
    #ax.legend(loc='best', frameon = True)
    #ax.set_xlim(pd.Timestamp('2018-25-09 00:00'), pd.Timestamp('2018-10-10 00:00'))
    ax.set_ylim(Fmin, Fmax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Fdist))
    #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,12)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'9.1 '+customer+'_frequency_total period.png', format = 'png')
    display(fig)
    plt.close("all")

def plot_frequency_weekly():

   # frequency
    # Subplots per week
    #----------------------------------

    #Create dataframe for weekly subplots
    #----------------------------------
    dfFweekS = df[['Frequency [Hz]']].copy()
    dfFweekS['Week']='CW ' + dfFweekS.index.isocalendar().week.astype(str)
    dfFweekS.reset_index(inplace = True, drop = False)
    dfFweekS.set_index(['Week'], inplace=True, append = True)
    dfFweekS = dfFweekS.unstack(1)
    
    
    #Plot weekly subplots
    #----------------------------------
    j = int(len(dfFweekS.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*3), facecolor="white")

    for n in range(j):
        # Plot one subplot per week
        ax = fig.add_subplot(j,1,n+1)
        ax.plot(dfFweekS[dfFweekS.columns[n]], dfFweekS[dfFweekS.columns[int(n+j)]], '-', linewidth = 0.5, color=colorF[2])
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
            #y-axis
        ax.set_ylabel('Frequency [Hz] \n', fontsize='large')
        ax.yaxis.set_major_locator(plt.MultipleLocator(Fdist))        
        ax.set_ylim(Fmin, Fmax)
        #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        #ax.legend(loc='best', frameon = True)

        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_title('Frequency '+customer+' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfFweekS[dfFweekS.columns[n]].max() - timedelta(days=7),dfFweekS[dfFweekS.columns[n]].max())
        else:
            ax.set_xlim(dfFweekS[dfFweekS.columns[n]].min(),dfFweekS[dfFweekS.columns[n]].min() + timedelta(days=7))
    # Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR+'9.2 '+customer+'_frequency_weekly subplots.png', format = 'png')
    display(fig)
    plt.close("all")
    
def plot_frequency_daily():
        # frequency Subplots per day
    #----------------------------------
    
    #Create dataframe for daily subplots
    #----------------------------------
    dfFdayS = df[['Frequency [Hz]']].copy()
    dfFdayS['Date']=dfFdayS.index.date
    dfFdayS.reset_index(inplace = True, drop = False)
    dfFdayS.set_index(['Date'], inplace=True, append = True)
    dfFdayS = dfFdayS.unstack(1)
    
    #display(dfFdayS)
    
    #Plot daily subplots
    #----------------------------------
    j = int(len(dfFdayS.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*1.5), facecolor="white")
    fig.suptitle('Frequency '+customer+' - daily subplots \n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfFdayS[dfFdayS.columns[n]], dfFdayS[dfFdayS.columns[int(n+j)]], '-', linewidth = 0.5, color=colorF[2], label = dfFdayS[dfFdayS.columns[n]].min().date().strftime('%a %d-%m-%y'))
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Fdist))        
        ax.set_ylim(Fmin, Fmax)
        #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others 
        plt.xticks(rotation=45, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='upper right', frameon = True, handlelength=0)
        
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_xlim(dfFdayS[dfFdayS.columns[n]].max() - timedelta(days=1),dfFdayS[dfFdayS.columns[n]].max())
            ax.set_ylabel('Frequency [Hz] \n', fontsize='large')
        else:
            ax.set_xlim(dfFdayS[dfFdayS.columns[n]].min(),dfFdayS[dfFdayS.columns[n]].min() + timedelta(days=1))
    
    # Formatting only for last plot
    ax.set_xlabel('\n Daytime', fontsize='large')
    plt.subplots_adjust(top=0.96)
    # Save to file
    fig.savefig(OUTDIR+'9.3 '+customer+'_frequency_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")
    
    
def plot_power_active_daily_average():
    
    global dfPday
    #Calculate daily representation
    
    dfPday = dfP.copy()
    
    dfPday['Time']=dfPday.index.time
    dfPday['Date']=dfPday.index.date
    
    dfPday.reset_index(inplace = True, drop = False)
    
    dfPday['DtTime'] = '1900-01-01 ' +dfPday['Time'].astype(str)
    dfPday['DtTime']=_to_datetime_flex(dfPday['DtTime'])
    
    dfPday.set_index(['Date', 'DtTime'], inplace=True)
    dfPday.drop(['DateTime', 'Time'], axis = 1, inplace = True)
    
    dfPday = dfPday.unstack(0)
    #dfPday = dfPday.mean(axis=1)
    dfPday
    
    #Plot daily average with details
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(dfPday, '--', color='grey', linewidth = 0.5)
    ax.plot(dfPday.mean(axis=1), '-', linewidth = 1, label="Average")
    ax.plot(dfPday.quantile(0.25,axis=1), '-', linewidth = 1, label="25% Quantile")
    ax.plot(dfPday.quantile(0.5,axis=1), '-', linewidth = 1, label="50% Quantile")
    ax.plot(dfPday.quantile(0.75,axis=1), '-', linewidth = 1, label="75% Quantile")
    #ax.plot(dfPday.quantile(0.9,axis=1), '-', linewidth = 1, label="90% Quantile")
    ax.set_xlabel('\n Daytime', fontsize='large')
    ax.set_ylabel('Power [kW] \n', fontsize='large')
    ax.set_title('Power consumption '+customer+' - per day \n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    ax.set_ylim(Ymin, Ymax)
    ax.set_xlim([pd.to_datetime('1900-01-01 00:00:00'), pd.to_datetime('1900-01-02 00:00:00')])
    ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y * Yformat)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,1)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
    plt.xticks(rotation=30, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'10.1 '+customer+'_power_day detail.png', format = 'png')   
    display(fig)
    plt.close("all")
    
    #Plot daily average only
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    #ax.plot(dfPday, '--', color='grey', linewidth = 0.5)
    ax.plot(dfPday.mean(axis=1), '-', linewidth = 1, label="Average")
    #ax.plot(dfPday.quantile(0.25,axis=1), '-', linewidth = 1, label="25% Quantile")
    #ax.plot(dfPday.quantile(0.5,axis=1), '-', linewidth = 1, label="50% Quantile")
    #ax.plot(dfPday.quantile(0.75,axis=1), '-', linewidth = 1, label="75% Quantile")
    #ax.plot(dfPday.quantile(0.9,axis=1), '-', linewidth = 1, label="90% Quantile")
    ax.set_xlabel('\n Daytime', fontsize='large')
    ax.set_ylabel('Power [kW] \n', fontsize='large')
    ax.set_title('Power consumption '+customer+' - per day \n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    ax.set_ylim(Ymin, Ymax)
    ax.set_xlim([pd.to_datetime('1900-01-01 00:00:00'), pd.to_datetime('1900-01-02 00:00:00')])
    ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y * Yformat)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,1)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
    plt.xticks(rotation=30, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'10.2 '+customer+'_power_day avg.png', format = 'png')
    display(fig)
    plt.close("all")

def summary_energy():
    #Summary Energy
    
    global dfEd
    dfEd = pd.DataFrame(index=['kWh/day', 'kWh/month', 'kWh/year'])
    
    dfPdayX = dfPday.copy()
    dfPdayX = dfPdayX.mean(axis=1)
    
    dfEd.at['kWh/day','Off-Peak'] = (dfPdayX.loc['1900-01-01 00:00':'1900-01-01 06:00'].sum(axis=0)/60*RateMin*Yformat).round().astype(int)
    dfEd.at['kWh/day', 'Shoulder'] = (dfPdayX.loc['1900-01-01 06:00':'1900-01-01 18:00'].sum(axis=0)/60*RateMin*Yformat).round().astype(int)
    dfEd.at['kWh/day','Peak'] = (dfPdayX.loc['1900-01-01 18:00':'1900-01-01 23:59'].sum(axis=0)/60*RateMin*Yformat).round().astype(int)
    dfEd.at['kWh/day','Total'] = (dfPdayX.sum(axis=0)/60*RateMin*Yformat).round().astype(int)
    dfEd = dfEd.T
    dfEd['kWh/month'] = dfEd['kWh/day']*30
    dfEd['kWh/year'] = dfEd['kWh/day']*365
    dfEd = dfEd.round().astype(int)
    dfEd = dfEd.T
    
    display(dfEd)
    
def read_radiation_data():
    
    # Read radiation file
    global dfRad
    dfRad = _read_radiation_table(PathRadiation)
    dfRad = dfRad[['Time','G [W/m²]']]
    dfRad['Time'] = '1900-01-01 ' +dfRad['Time'].astype(str)
    dfRad['Time']=_to_datetime_flex(dfRad['Time'])
    dfRad.set_index(['Time'], inplace=True)
    dfRad = dfRad.resample(rate).ffill(limit=1).interpolate()
    
    # Plot radiation
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(dfRad['G [W/m²]'], '-', linewidth = 1, label="Global irradiance on a fixed plane (Source: PVGIS)")
    ax.set_xlabel('\n Daytime', fontsize='large')
    ax.set_ylabel('Irradiance [W/m²] \n', fontsize='large')
    ax.set_title('Daily irradiance\n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    ax.set_xlim([pd.to_datetime('1900-01-01 00:00:00'), pd.to_datetime('1900-01-02 00:00:00')])
    #ax.set_ylim(0, 270000)
    #ax.yaxis.set_major_locator(plt.MultipleLocator(20000))
    #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y * Yformat)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,1)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
    plt.xticks(rotation=30, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'13.1 '+customer+'_irradiance.png', format = 'png')
    display(fig)
    plt.close("all")
    
def simulation_generation_daily_average():
    # PV simulation
    global dfGen
    global dfSim
    global EPVmax
    global EPVmaxP
    
    EPVmax = pd.DataFrame()
    dfGen = dfRad.copy()
    
    
    for i in PPV:
        dfGen["Max "+str(i)+" kWp"] = dfGen['G [W/m²]']/1000*i*EtaPV
        #EPVmax.iat(0,1)=dfRad[i].sum()/4
        EPVmax.at[str(i)+" kWp",'kWh/day'] = (dfGen["Max "+str(i)+" kWp"].sum()/60*RateMin).round().astype(int)
        EPVmax.at[str(i)+" kWp",'kWh/month'] = (dfGen["Max "+str(i)+" kWp"].sum()/60*RateMin*30).round().astype(int)
        EPVmax.at[str(i)+" kWp",'kWh/year'] = (dfGen["Max "+str(i)+" kWp"].sum()/60*RateMin*365).round().astype(int)
    
        
    EPVmax.reset_index(inplace = True)
    EPVmax.rename(columns={'index':'PV kWp'}, inplace=True)
    
    EPVmaxP=EPVmax.copy()
    EPVmaxP.set_index(EPVmax['PV kWp'],inplace=True)
    EPVmaxP.rename_axis(None, inplace=True)
    EPVmaxP.drop(['PV kWp'], axis = 1, inplace = True)
    display('PV generation')
    EPVmaxP = EPVmaxP.round().astype(int)
    EPVmaxP=EPVmaxP.T
    display(EPVmaxP)
    
    #Plot daily average with PV production
    #PVmax
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(dfPday.mean(axis=1), '-', linewidth = 2, label="Average consumption")
    #ax.plot(dfPday.quantile(0.25,axis=1), '--', linewidth = 0.5, label="25% Quantile")
    for i in PPV:
        ax.plot(dfGen["Max "+str(i)+" kWp"]/Yformat, '-', linewidth = 1, label=str(i) +' kWp PV generation')
    ax.set_xlabel('\n Daytime', fontsize='large')
    ax.set_ylabel('Power [kW] \n', fontsize='large')
    ax.set_title('Daily average power consumption and solar generation - '+customer+' \n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    ax.set_ylim(Ymin, Ymax)
    ax.set_xlim([pd.to_datetime('1900-01-01 00:00:00'), pd.to_datetime('1900-01-02 00:00:00')])
    ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y * Yformat)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,1)))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
    plt.xticks(rotation=30, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'11.1 '+customer+'_generation_day max.png', format = 'png')
    display(fig)
    plt.close("all")
    
    #Calculate actual generation for raw data

    dfSim = pd.DataFrame()
    dfSim=dfP.copy()
    
    dfSim['Time']=dfSim.index.time
    dfSim['Time'] = '1900-01-01 ' +dfSim['Time'].astype(str)
    dfSim['Time']=_to_datetime_flex(dfSim['Time'])
    dfSim = dfSim.reset_index().merge(dfGen/Yformat, on="Time", how='left').set_index('DateTime')
    dfSim=dfSim.fillna(0)
    
    def calc_PVact(Con,Gen):
        if Con > Gen*(1+Offset):
            return Gen
        else:   
            return Con*(1-Offset)
    
    for i in PPV:
        dfSim['Act '+str(i)+' kWp'] = dfSim.apply(lambda row: calc_PVact(row[Pp],row['Max '+str(i)+' kWp']), axis=1)
    
        
    #Calculate daily representation of simulation
    
    dfSimDay = dfSim.copy()
    dfSimDay = dfSimDay.groupby(dfSim['Time']).mean(numeric_only=True)
    
    #Plot daily average with PV production
    #PVact
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(dfSimDay[Pp], '-', linewidth = 2, label=" Average consumption")
    
    for i in PPV:
        ax.plot(dfSimDay["Act "+str(i)+" kWp"], '-', linewidth = 1, label=str(i) +' kWp actual PV generation')
    ax.set_xlabel('\n Daytime', fontsize='large')
    ax.set_ylabel('Power [kW] \n', fontsize='large')
    ax.set_title('Daily average power consumption and solar generation - '+customer+' \n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    ax.set_ylim(Ymin, Ymax)
    ax.set_xlim([pd.to_datetime('1900-01-01 00:00:00'), pd.to_datetime('1900-01-02 00:00:00')])
    ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y * Yformat)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,1)))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
    plt.xticks(rotation=30, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'11.2 '+customer+'_generation_day act.png', format = 'png')
    display(fig)
    plt.close("all")
    
def summary_yield():
    #Summary PV yield max vs. act
    
    global dfPVd
    dfPVd = pd.DataFrame(index=['Consumption kWh/year','PV max kWh/year', 'PV direct kWh/year', 'PV direct share %', 'PV maximum share %'])
    
    dfPV = dfSim.copy()
    #dfPVd=pd.DataFrame()
    
    j=0
    for i in PPV:
        #dfPVd.at['Consumption kWh/year',str(i)+' kWp']=dfPV[Pp].sum(axis=0)/len(dfPV.index)*Yformat*24*365
        dfPVd.at['Consumption kWh/year',str(i)+' kWp']= dfEd.iloc[2,3]
        #dfPVd.at['PV max kWh/year',str(i)+' kWp']=dfPV['Max '+str(i)+' kWp'].sum(axis=0)/len(dfPV.index)*Yformat*24*365
        dfPVd.at['PV max kWh/year',str(i)+' kWp']= EPVmax.iloc[j,3]
        dfPVd.at['PV direct kWh/year',str(i)+' kWp']=dfPV['Act '+str(i)+' kWp'].sum(axis=0)/len(dfPV.index)*Yformat*24*365
        dfPVd.at['PV direct share %',str(i)+' kWp']=dfPVd.at['PV direct kWh/year',str(i)+' kWp']/dfPVd.at['PV max kWh/year',str(i)+' kWp']*100
        dfPVd.at['PV maximum share %',str(i)+' kWp']=dfPVd.at['PV max kWh/year',str(i)+' kWp']/dfPVd.at['Consumption kWh/year',str(i)+' kWp']*100
        j=j+1
    dfPVd=dfPVd.round(1).astype(int)
    dfPVd
    
def simulation_generation_daily_subplots():
    # Subplots per day incl. generation
    #----------------------------------
    
    #Create dataframe for daily subplots
    #----------------------------------
    dfSimS = dfSim.copy()
    dfSimS.drop(['Time','G [W/m²]'], axis = 1, inplace = True)
    for i in PPV:
        dfSimS.drop(['Max '+str(i)+' kWp'], axis = 1, inplace = True)
    dfSimS['Date']=dfSimS.index.date
    dfSimS.reset_index(inplace = True, drop = False)
    dfSimS.set_index(['Date'], inplace=True, append = True)
    dfSimS = dfSimS.unstack(1)
    
    #with pd.option_context('display.max_rows', None, 'display.max_columns', None):
    #    display(dfSimS)
    
    #Plot daily subplots
    #----------------------------------
    j = int(len(dfSimS.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*0.8), facecolor="white")
    fig.suptitle('Power consumption and generation '+customer+' - daily subplots \n\n\n', fontsize='x-large')
    j = int(len(dfSimS.columns)/(2+len(PPV)))
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfSimS[dfSimS.columns[n]], dfSimS[dfSimS.columns[int(n+j)]], '-', linewidth = 0.5, label = dfSimS[dfSimS.columns[n]].min().date().strftime('%a %d-%m-%y')+'\n Consumption')
        for i in range(len(PPV)):
            #display(i)
            ax.plot(dfSimS[dfSimS.columns[n]], dfSimS[dfSimS.columns[int(n+j*(i+2))]], '-', linewidth = 0.5, label = str(PPV[i]) +' kWp PV generation')
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))        
        ax.set_ylim(Ymin, Ymax)
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y * Yformat)))
            #Others 
        plt.xticks(rotation=45, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        #ax.legend(loc='upper right', frameon = True, handlelength=0)
        ax.legend(loc='upper right', frameon = True)
        
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_xlim(dfSimS[dfSimS.columns[n]].max() - timedelta(days=1),dfSimS[dfSimS.columns[n]].max())
            ax.set_ylabel('Power consumption [W] \n', fontsize='large')
        else:
            ax.set_xlim(dfSimS[dfSimS.columns[n]].min(),dfSimS[dfSimS.columns[n]].min() + timedelta(days=1))
    
    # Formatting only for last plot
    ax.set_xlabel('\n Daytime', fontsize='large')
    plt.subplots_adjust(top=0.96)
    # Save to file
    fig.savefig(OUTDIR+'11.3 '+customer+'_generation_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")
    
def summary_generation_yield():
    from matplotlib.colors import ListedColormap
    sns.set()
    
    fig = plt.figure(figsize=(8,15),dpi=300, facecolor="white")
    fig.subplots_adjust(hspace=1)
    fig.suptitle('Electricity consumption and PV generation \n '+customer+'\n\n', fontsize="16", weight='bold',x=0.6)
    fig.subplots_adjust(left=0.4, top=0.85)
    
    ax1 = plt.subplot(3,1,1)
    #ax1 = sns.heatmap(dfEd, annot=True,  linewidths=0.5, cbar=False, yticklabels=True, cmap=ListedColormap(['whitesmoke']))
    ax1 = sns.heatmap(dfEd, annot=True, fmt="d", linewidths=0.5, cbar=False, yticklabels=True, cmap=ListedColormap(['whitesmoke']))
    ax1.set_title('Electricity consumption \n\n',x=0, fontsize="14", weight='bold',horizontalalignment='left')
    ax1.tick_params(labelbottom=False,labeltop=True)
    ax1.axhline(y=0,color='k')
    for t in ax1.texts:
        t.set_text('{:,d}'.format(int(t.get_text())))
    plt.xticks(fontsize="12", weight='bold')
    plt.yticks(fontsize="12", weight='bold')
    
    
    ax2 = plt.subplot(3,1,2)
    ax2 = sns.heatmap(EPVmaxP.astype(int), annot=True, fmt="d", linewidths=0.5, cbar=False, yticklabels=True, cmap=ListedColormap(['lavender']))
    ax2.set_title('Maximum PV yield \n\n',x=0, fontsize="14", weight='bold', horizontalalignment='left')
    ax2.tick_params(labelbottom=False,labeltop=True)
    ax2.axhline(y=0,color='k')
    for t in ax2.texts:
        t.set_text('{:,d}'.format(int(t.get_text())))
    plt.xticks(fontsize="12", weight='bold')
    plt.yticks(fontsize="12", weight='bold', rotation = 0)
    
    ax3 = plt.subplot(3,1,3)
    ax3 = sns.heatmap(dfPVd.astype(int), annot=True, fmt="d", linewidths=0.5, cbar=False, yticklabels=True, cmap=ListedColormap(['lavender']))
    ax3.set_title('Direct PV consumption and share \n\n',x=0, fontsize="14", weight='bold', horizontalalignment='left')
    ax3.tick_params(labelbottom=False,labeltop=True)
    ax3.axhline(y=0,color='k')
    for t in ax3.texts:
        t.set_text('{:,d}'.format(int(t.get_text())))
    plt.xticks(fontsize="12", weight='bold')
    plt.yticks(fontsize="12", weight='bold', rotation = 0)
    
    fig.savefig(OUTDIR+'12 '+customer+' Summary.png', format = 'png')
    display(fig)
    plt.close("all")

def calculation_SMA():
    # Data for SMA calculation
    # 5min, 24 h
    
      #Calculate weekly representation

    dfPweek = dfP.copy()
    display(dfPweek.head())
    display(dfP.head())
    #dfPweek['Weekday']=dfPweek.index.day_name()
    dfPweek['Week']=dfPweek.index.isocalendar().week
    dfPweek['WeekdayNo']=dfPweek.index.weekday
    dfPweek['Time']=dfPweek.index.time
    
    dfPweek.reset_index(inplace = True, drop = False)
    
    dfPweek['WeekdayNo']+=1
    dfPweek['WeekDateTime'] = '1900-01-' +dfPweek['WeekdayNo'].astype(str) + ' ' + dfPweek['Time'].astype(str)
    dfPweek['WeekDateTime']=_to_datetime_flex(dfPweek['WeekDateTime'])
    
    dfPweek.set_index(['Week', 'WeekDateTime'], inplace=True)
    dfPweek.drop(['Time', 'DateTime', 'WeekdayNo'], axis = 1, inplace = True)
    dfPweek = dfPweek.unstack(0)

    
    dfPweekSMA = dfPweek.resample('10Min').mean(numeric_only=True)
    dfPweekSMA['mean'] = dfPweekSMA.mean(axis=1)
    dfPweekSMA.head()
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor= "white")
    ax = plt.axes()
    ax.plot(dfPweekSMA['mean'], '--', color='red', linewidth = 1, label="SMA mean")
    ax.plot(dfPweek.mean(axis=1), '--', linewidth = 1, label="Mean raw data")
    ax.set_xlabel('\n weektime', fontsize='large')
    ax.set_ylabel('Power consumption [W] \n', fontsize='large')
    ax.set_title('Power consumption '+customer+' - check resampling \n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    #ax.set_ylim(0, 270000)
    #ax.yaxis.set_major_locator(plt.MultipleLocator(20000))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y * Yformat)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,12)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %H:%M'))
    plt.xticks(rotation=30, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'13.2 '+customer+'_check SMA resampling.png', format = 'png')
    display(fig)
    plt.close("all")
    dfPweekSMA['mean'].to_csv(OUTDIR + customer + ' measurement, SunnyDesign.csv', index=False)
    
            
