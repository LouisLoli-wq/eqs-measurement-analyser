"""
Shelly measurement plotting
===========================

GENERATED FILE -- do not edit by hand.

Produced by tools/generate_plot_modules.py from "1a7fda8c-Shelly_code.ipynb".
Every plotting function below is that notebook's own code. See the generator
and TECHNICAL_NOTES.md for the complete list of changes applied.

Regenerate with:
    python tools/generate_plot_modules.py --shelly "<path to the notebook>"
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

# Power axis [W, displayed via Yformat]
Ymax, Ymin, Ydist = 10000, 0, 1000
# Apparent power axis [VA]
Amax, Adist = 50000, 5000
# Voltage axis [V]
Umin, Umax, Udist = 150, 300, 20
# Current axis [A]
Imin, Imax, Idist = -5, 50, 10
# Power factor axis [-]
PFmin, PFmax, PFdist = 0.0, 1.1, 0.1

Yformat = 1e-3                      # 1 -> P in kW, 1e-3 -> P in W
RateMin = 1                              # sample interval of the data, minutes
rate = "1Min"

PPV = [10, 15, 18, 20]                              # simulated PV system sizes [kWp]
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

# Correction 2 (see TECHNICAL_NOTES.md). total_act_energy is Wh accumulated
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
    return 60.0 / float(RateMin)

_SETTINGS = set("""
customer
PathMeasurement
PathRadiation
OUTDIR
Ymax
Ymin
Ydist
Amax
Adist
Umin
Umax
Udist
Imin
Imax
Idist
PFmin
PFmax
PFdist
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
            raise KeyError("unknown setting %r for shelly (valid: %s)"
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

Pp = 'Pp'


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
    global dfImax
    df = _read_measurement_table(PathMeasurement, sep=',')
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    #df['timestamp'] = pd.to_datetime(df['timestamp'], format='%d/%m/%Y %H:%M:%S')
    #df['Time'] = pd.to_datetime(df['Time'], format='%d/%m/%Y %H:%M')
    
    # Measurement time offset correction
    df['timestamp']=df['timestamp']+pd.DateOffset(hours=deltatime)

    df.set_index(['timestamp'],inplace=True)
    df.index.name = 'DateTime'
    df = df.resample(rate).mean(numeric_only=True)
    
    df['Pp'] = (df['a_total_act_energy'] + df['b_total_act_energy'] + df['c_total_act_energy']) * _WH_TO_W()
    
    dfP = df[['Pp']].copy()
    dfP = dfP.resample(rate).mean(numeric_only=True)

    dfU = df[['a_avg_voltage','b_avg_voltage','c_avg_voltage']].copy()
    dfPL = df[['a_total_act_energy', 'b_total_act_energy', 'c_total_act_energy']].copy() * _WH_TO_W()
    dfI = df[['a_avg_current','b_avg_current','c_avg_current']].copy()
    #dfTHD = df[['L1 U THD avg [%]','L2 U THD avg [%]','L3 U THD avg [%]']].copy()
    
    # This block is for max currents
    dfImax = df[['a_max_current','b_max_current','c_max_current']].copy()

#Plot total period
#-------------------

def plot_total_power_active_total():

    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    #Background colour
    
    ax = plt.axes()
    ax.plot(dfP['Pp'], '-', linewidth =0.5, label="consumption")
    #ax.plot(dfP[Pn], '-', linewidth =0.5, label ="feed-in")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Power [kW] \n', fontsize='large')
    ax.set_title('Power consumption ' + customer + ' - total measurement period\n', fontsize='large')
    #ax.legend(loc='best', frameon = True)
    #ax.set_xlim(pd.Timestamp('2018-25-09 00:00'), pd.Timestamp('2018-10-10 00:00'))
    ax.set_ylim(Ymin, Ymax)
    #ax.set_ylim(0,5000)
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
    ax.plot(df['a_total_act_energy']*60, '-', linewidth =0.5, color=colorP[0], label = "Phase a")
    ax.plot(df['b_total_act_energy']*60, '-', linewidth =0.5, color=colorP[1], label = "Phase b")
    ax.plot(df['c_total_act_energy']*60, '-', linewidth =0.5, color=colorP[2], label = "Phase c")
    #ax.plot(dfP[Pn], '-', linewidth =0.5, label ="feed-in")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Power [kW] \n', fontsize='large')
    ax.set_title('Power per phase ' + customer + ' - total measurement period\n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    #ax.set_xlim(pd.Timestamp('2018-25-09 00:00'), pd.Timestamp('2018-10-10 00:00'))
    #ax.set_ylim(0, 200) changed to the line below
    ax.set_ylim(Ymin, Ymax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
    #ax.yaxis.set_major_locator(plt.MultipleLocator(100))
    #Line 210 changed to 211
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

    dfPaweekS_L1 = df[['a_total_act_energy']].copy()*60
    dfPaweekS_L1['Week']='CW ' + dfPaweekS_L1.index.isocalendar().week.astype(str)
    dfPaweekS_L1.reset_index(inplace = True, drop = False)
    dfPaweekS_L1.set_index(['Week'], inplace=True, append = True)
    dfPaweekS_L1 = dfPaweekS_L1.unstack(1)

    dfPaweekS_L2 = df[['b_total_act_energy']].copy()*60
    dfPaweekS_L2['Week']='CW ' + dfPaweekS_L2.index.isocalendar().week.astype(str)
    dfPaweekS_L2.reset_index(inplace = True, drop = False)
    dfPaweekS_L2.set_index(['Week'], inplace=True, append = True)
    dfPaweekS_L2 = dfPaweekS_L2.unstack(1)
                    
    dfPaweekS_L3 = df[['c_total_act_energy']].copy()*60
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
        ax.plot(dfPaweekS_L1[dfPaweekS_L1.columns[n]], dfPaweekS_L1[dfPaweekS_L1.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase a', color=colorP[0])
        ax.plot(dfPaweekS_L2[dfPaweekS_L2.columns[n]], dfPaweekS_L2[dfPaweekS_L2.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase b', color=colorP[1])
        ax.plot(dfPaweekS_L3[dfPaweekS_L3.columns[n]], dfPaweekS_L3[dfPaweekS_L3.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase c', color=colorP[2])
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
            #y-axis
        ax.set_ylabel('Power [kW] \n', fontsize='large')       
        ax.set_ylim(Ymin, Ymax)
        ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist))
        #ax.yaxis.set_major_locator(plt.MultipleLocator(100))
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
        ax.plot(dfPLday[dfPLday.columns[n]], dfPLday[dfPLday.columns[int(n+j)]], '-', linewidth = 0.5, label = dfPLday[dfPLday.columns[n]].min().date().strftime('%a %d-%m-%y')+'\nPhase a', color=colorP[0])
        ax.plot(dfPLday[dfPLday.columns[n]], dfPLday[dfPLday.columns[int(n+j*2)]], '-', linewidth = 0.5, label= 'Phase b', color=colorP[1])
        ax.plot(dfPLday[dfPLday.columns[n]], dfPLday[dfPLday.columns[int(n+j*3)]], '-', linewidth = 0.5, label= 'Phase c', color=colorP[2])
        
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Ydist)) 
        #ax.yaxis.set_major_locator(plt.MultipleLocator(100))
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
    ax.plot(df['a_max_aprt_power'] + df['b_max_aprt_power'] + df['c_max_aprt_power'],
        '-', linewidth=0.5, label="consumption", color=colorA[2])

    #ax.plot((df['a_max_aprt_power'] + df['b_max_aprt_power'] + df['c_max_aprt_power'], '-', linewidth =0.5, label="consumption", color=colorA[2])
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Apparent Power [kVA] \n', fontsize='large')
    ax.set_title('Max Apparent Power ' + customer + ' - total measurement period\n', fontsize='large')
    #ax.legend(loc='best', frameon = True)
    #ax.set_xlim(pd.Timestamp('2018-25-09 00:00'), pd.Timestamp('2018-10-10 00:00'))
    ax.set_ylim(Ymin, Amax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Adist))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,12)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'3.1 '+customer+'_Max apparent power_total period.png', format = 'png')
    display(fig)
    plt.close("all")

def plot_total_power_apparent_weekly():

   # Apparent Power
    # Subplots per week
    #----------------------------------

    #Create dataframe for weekly subplots
    #----------------------------------
    dfAPweekS = pd.DataFrame()
    dfAPweekS['Papparent total avg [VA]'] = (df['a_max_aprt_power'] + df['b_max_aprt_power'] + df['c_max_aprt_power'])
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
        ax.yaxis.set_major_locator(plt.MultipleLocator(Adist))        
        ax.set_ylim(Ymin, Amax)
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        #ax.legend(loc='best', frameon = True)

        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_title('Max Apparent Power '+customer+' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfAPweekS[dfAPweekS.columns[n]].max() - timedelta(days=7),dfAPweekS[dfAPweekS.columns[n]].max())
        else:
            ax.set_xlim(dfAPweekS[dfAPweekS.columns[n]].min(),dfAPweekS[dfAPweekS.columns[n]].min() + timedelta(days=7))
    # Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR+'3.2 '+customer+'_ Max apparent power_weekly subplots.png', format = 'png')
    display(fig)
    plt.close("all") 
def plot_total_power_apparent_daily():
        # Power Subplots per day
    #----------------------------------
    
    #Create dataframe for daily subplots
    #----------------------------------
    dfAPdayS = dfP.copy()
    dfAPdayS = pd.DataFrame()
    dfAPdayS['Papparent total avg [VA]'] = (df['a_max_aprt_power'] + df['b_max_aprt_power'] + df['c_max_aprt_power'])
    dfAPdayS['Date']=dfAPdayS.index.date
    dfAPdayS.reset_index(inplace = True, drop = False)
    dfAPdayS.set_index(['Date'], inplace=True, append = True)
    dfAPdayS = dfAPdayS.unstack(1)
    
    #display(dfAPdayS)
    
    #Plot daily subplots
    #----------------------------------
    j = int(len(dfAPdayS.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*1.5), facecolor="white")
    fig.suptitle('Max Apparent Power '+customer+' - daily subplots \n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfAPdayS[dfAPdayS.columns[n]], dfAPdayS[dfAPdayS.columns[int(n+j)]], '-', linewidth = 0.5,color=colorA[2], label = dfAPdayS[dfAPdayS.columns[n]].min().date().strftime('%a %d-%m-%y'))
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Adist))        
        ax.set_ylim(Ymin, Amax)
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
    fig.savefig(OUTDIR+'3.3 '+customer+'_Max apparent power_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")

    
def plot_phase_power_apparent_total():   
        # Apparent Power per phase
    #Plot total period
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(df['a_max_aprt_power'], '-', linewidth =0.5, color=colorA[0], label = "Phase a")
    ax.plot(df['b_max_aprt_power'], '-', linewidth =0.5, color=colorA[1], label = "Phase b")
    ax.plot(df['c_max_aprt_power'], '-', linewidth =0.5, color=colorA[2], label = "Phase c")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Apparent Power [kVA] \n', fontsize='large')
    ax.set_title('Max Apparent Power per phase ' + customer + ' - total measurement period\n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    #ax.set_xlim(pd.Timestamp('2018-25-09 00:00'), pd.Timestamp('2018-10-10 00:00'))
    ax.set_ylim(Ymin, Amax)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Adist))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
    #ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,12)))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'4.1 '+customer+'_Max apparent Power per phase_total period.png', format = 'png')
    display(fig)
    plt.close("all")

def plot_phase_power_apparent_weekly():

    # Apparent Power per phase
    # Subplots per week
    #----------------------------------

    #Create dataframe for weekly subplots
    #----------------------------------

    dfAPweekS_L1 = pd.DataFrame()
    dfAPweekS_L1['L1 Papparent avg [VA]'] = df['a_max_aprt_power']
    #display(dfAPweekS_L1.head())
    dfAPweekS_L1['Week']='CW ' + dfAPweekS_L1.index.isocalendar().week.astype(str)
    dfAPweekS_L1.reset_index(inplace = True, drop = False)
    dfAPweekS_L1.set_index(['Week'], inplace=True, append = True)
    dfAPweekS_L1 = dfAPweekS_L1.unstack(1)
    
    dfAPweekS_L2 = pd.DataFrame()
    dfAPweekS_L2['L2 Papparent avg [VA]'] = df['b_max_aprt_power']
    #dfAPweekS_L2 = df[['L2 Pactive avg [kW]']].copy()
    dfAPweekS_L2['Week']='CW ' + dfAPweekS_L2.index.isocalendar().week.astype(str)
    dfAPweekS_L2.reset_index(inplace = True, drop = False)
    dfAPweekS_L2.set_index(['Week'], inplace=True, append = True)
    dfAPweekS_L2 = dfAPweekS_L2.unstack(1)
    
    dfAPweekS_L3 = pd.DataFrame()
    dfAPweekS_L3['L3 Papparent avg [VA]'] = df['c_max_aprt_power']
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
        ax.plot(dfAPweekS_L1[dfAPweekS_L1.columns[n]], dfAPweekS_L1[dfAPweekS_L1.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase a', color=colorA[0])
        ax.plot(dfAPweekS_L2[dfAPweekS_L2.columns[n]], dfAPweekS_L2[dfAPweekS_L2.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase b', color=colorA[1])
        ax.plot(dfAPweekS_L3[dfAPweekS_L3.columns[n]], dfAPweekS_L3[dfAPweekS_L3.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase c', color=colorA[2])
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
            #y-axis
        ax.set_ylabel('Apparent Power [kVA] \n', fontsize='large')       
        ax.set_ylim(Ymin, Amax)
        ax.yaxis.set_major_locator(plt.MultipleLocator(Adist))
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
            #Others
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='best', frameon = True)
        # Formatting only for first plot/other plots
        if n == 0:
            ax.set_title('Max Apparent Power per phase '+customer+' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfAPweekS_L1[dfAPweekS_L1.columns[n]].max() - timedelta(days=7),dfAPweekS_L1[dfAPweekS_L1.columns[n]].max())
        else:
            ax.set_xlim(dfAPweekS_L1[dfAPweekS_L1.columns[n]].min(),dfAPweekS_L1[dfAPweekS_L1.columns[n]].min() + timedelta(days=7))
    #Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR+'4.2 '+customer+'_Max apparent Power per phase_weekly subplots.png', format = 'png')
    display(fig)
    plt.close("all")
    
def plot_phase_power_apparent_daily():    
    # Apparent Power per phase Subplots per day
    #----------------------------------
    
    #Create dataframe for daily subplots
    #---------------------------------- 
    dfPAday = pd.DataFrame()   
    dfPAday['L1 Papparent avg [VA]'] = df['a_max_aprt_power']
    dfPAday['L2 Papparent avg [VA]'] = df['b_max_aprt_power']
    dfPAday['L3 Papparent avg [VA]'] = df['c_max_aprt_power']

    
    dfPAday['Date']=dfPAday.index.date
    dfPAday.reset_index(inplace = True, drop = False)
    dfPAday.set_index(['Date'], inplace=True, append = True)
    dfPAday = dfPAday.unstack(1)
    #display(dfPAday)
    
    #Plot daily subplots
    #----------------------------------
    j = int(len(dfPAday.columns)/4)
    fig = plt.figure(1, dpi=300, figsize=(12,j*1.5), facecolor="white")
    fig.suptitle('Max Apparent Power per phase '+customer+' - daily subplots \n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfPAday[dfPAday.columns[n]], dfPAday[dfPAday.columns[int(n+j)]], '-', linewidth = 0.5, label = dfPAday[dfPAday.columns[n]].min().date().strftime('%a %d-%m-%y')+'\nPhase a', color=colorA[0])
        ax.plot(dfPAday[dfPAday.columns[n]], dfPAday[dfPAday.columns[int(n+j*2)]], '-', linewidth = 0.5, label= 'Phase b', color=colorA[1])
        ax.plot(dfPAday[dfPAday.columns[n]], dfPAday[dfPAday.columns[int(n+j*3)]], '-', linewidth = 0.5, label= 'Phase c', color=colorA[2])
        
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Adist))        
        ax.set_ylim(Ymin, Amax)
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
    fig.savefig(OUTDIR+'4.3 '+customer+'_Max apparent Power per phase_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")    
    
    
def plot_phase_voltage_total():     
    # Voltage
    #Plot total period
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(df['a_avg_voltage'], '-', linewidth =0.5, color=colorU[0], label = "Phase a")
    ax.plot(df['b_avg_voltage'], '-', linewidth =0.5, color=colorU[1], label = "Phase b")
    ax.plot(df['c_avg_voltage'], '-', linewidth =0.5, color=colorU[2], label = "Phase c")
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
    dfUweekS_L1 = dfU[['a_avg_voltage']].copy()
    dfUweekS_L1['Week']='CW ' + dfUweekS_L1.index.isocalendar().week.astype(str)
    dfUweekS_L1.reset_index(inplace = True, drop = False)
    dfUweekS_L1.set_index(['Week'], inplace=True, append = True)
    dfUweekS_L1 = dfUweekS_L1.unstack(1)
    
    dfUweekS_L2 = dfU[['b_avg_voltage']].copy()
    dfUweekS_L2['Week']='CW ' + dfUweekS_L2.index.isocalendar().week.astype(str)
    dfUweekS_L2.reset_index(inplace = True, drop = False)
    dfUweekS_L2.set_index(['Week'], inplace=True, append = True)
    dfUweekS_L2 = dfUweekS_L2.unstack(1)
                           
    dfUweekS_L3 = dfU[['c_avg_voltage']].copy()
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
        ax.plot(dfUweekS_L1[dfUweekS_L1.columns[n]], dfUweekS_L1[dfUweekS_L1.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase a', color=colorU[0])
        ax.plot(dfUweekS_L2[dfUweekS_L2.columns[n]], dfUweekS_L2[dfUweekS_L2.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase b', color=colorU[1])
        ax.plot(dfUweekS_L3[dfUweekS_L3.columns[n]], dfUweekS_L3[dfUweekS_L3.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase c', color=colorU[2])
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
        ax.plot(dfUday[dfUday.columns[n]], dfUday[dfUday.columns[int(n+j)]], '-', linewidth = 0.5, label = dfUday[dfUday.columns[n]].min().date().strftime('%a %d-%m-%y')+'\nPhase a', color=colorU[0])
        ax.plot(dfUday[dfUday.columns[n]], dfUday[dfUday.columns[int(n+j*2)]], '-', linewidth = 0.5, label= 'Phase b', color=colorU[1])
        ax.plot(dfUday[dfUday.columns[n]], dfUday[dfUday.columns[int(n+j*3)]], '-', linewidth = 0.5, label= 'Phase c', color=colorU[2])
        
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Udist))        
        ax.set_ylim(Umin, Umax)
        #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % y))
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
    ax.plot(df['a_avg_current'], '-', linewidth =0.5, color=colorI[0], label = "Phase a")
    ax.plot(df['b_avg_current'], '-', linewidth =0.5, color=colorI[1], label = "Phase b")
    ax.plot(df['c_avg_current'], '-', linewidth =0.5, color=colorI[2], label = "Phase c")
    #ax.plot(dfP[Pn], '-', linewidth =0.5, label ="feed-in")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Current [A] \n', fontsize='large')
    ax.set_title('Current ' + customer + ' - total measurement period\n', fontsize='large')
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
    fig.savefig(OUTDIR+'6.1 '+customer+'_current_total period.png', format = 'png')
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
    dfIweekS_L1 = dfI[['a_avg_current']].copy()
    dfIweekS_L1['Week']='CW ' + dfIweekS_L1.index.isocalendar().week.astype(str)
    dfIweekS_L1.reset_index(inplace = True, drop = False)
    dfIweekS_L1.set_index(['Week'], inplace=True, append = True)
    dfIweekS_L1 = dfIweekS_L1.unstack(1)
    
    dfIweekS_L2 = dfI[['b_avg_current']].copy()
    dfIweekS_L2['Week']='CW ' + dfIweekS_L2.index.isocalendar().week.astype(str)
    dfIweekS_L2.reset_index(inplace = True, drop = False)
    dfIweekS_L2.set_index(['Week'], inplace=True, append = True)
    dfIweekS_L2 = dfIweekS_L2.unstack(1)
                           
    dfIweekS_L3 = dfI[['c_avg_current']].copy()
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
        ax.plot(dfIweekS_L1[dfIweekS_L1.columns[n]], dfIweekS_L1[dfIweekS_L1.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase a', color=colorI[0])
        ax.plot(dfIweekS_L2[dfIweekS_L2.columns[n]], dfIweekS_L2[dfIweekS_L2.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase b', color=colorI[1])
        ax.plot(dfIweekS_L3[dfIweekS_L3.columns[n]], dfIweekS_L3[dfIweekS_L3.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase c', color=colorI[2])
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
            ax.set_title('Current '+customer+' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfIweekS_L1[dfIweekS_L1.columns[n]].max() - timedelta(days=7),dfIweekS_L1[dfIweekS_L1.columns[n]].max())
        else:
            ax.set_xlim(dfIweekS_L1[dfIweekS_L1.columns[n]].min(),dfIweekS_L1[dfIweekS_L1.columns[n]].min() + timedelta(days=7))
    #Formatting only for first plot
    ax.set_xlabel('\n Day', fontsize='large')
    # Save to file
    fig.savefig(OUTDIR+'6.2 '+customer+'_current_weekly subplots.png', format = 'png')
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
    fig = plt.figure(1, dpi=300, figsize=(12,j*3), facecolor="white")
    fig.suptitle('Current '+customer+' - daily subplots \n\n\n\n', fontsize='x-large')
    for n in range(j):
        # Subplot for each day
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfIday[dfIday.columns[n]], dfIday[dfIday.columns[int(n+j)]], '-', linewidth = 0.5, label = dfIday[dfIday.columns[n]].min().date().strftime('%a %d-%m-%y')+'\nPhase a', color=colorI[0])
        ax.plot(dfIday[dfIday.columns[n]], dfIday[dfIday.columns[int(n+j*2)]], '-', linewidth = 0.5, label= 'Phase b', color=colorI[1])
        ax.plot(dfIday[dfIday.columns[n]], dfIday[dfIday.columns[int(n+j*3)]], '-', linewidth = 0.5, label= 'Phase c', color=colorI[2])
        
        # General formatting for all subplots
            #x-axis
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
            #y-axis
        ax.yaxis.set_major_locator(plt.MultipleLocator(Idist))        
        ax.set_ylim(0, Imax)
        #ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % (y*Yformat)))
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % y))
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
    fig.savefig(OUTDIR+'6.3 '+customer+'_current_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")   
    
    
    
    
    #Added section for Max current  
def plot_phase_max_current_total():     
    # Max Current
    # Plot total period
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(df['a_max_current'], '-', linewidth =0.5, color=colorI[0], label = "Phase a")
    ax.plot(df['b_max_current'], '-', linewidth =0.5, color=colorI[1], label = "Phase b")
    ax.plot(df['c_max_current'], '-', linewidth =0.5, color=colorI[2], label = "Phase c")
    ax.set_xlabel('\n Date', fontsize='large')
    ax.set_ylabel('Max Current [A] \n', fontsize='large')
    ax.set_title('Max Current ' + customer + ' - total measurement period\n', fontsize='large')
    ax.legend(loc='best', frameon = True)
    ax.set_ylim(Imin, Imax)  # Adjust if needed, e.g., to (-5, 100)
    ax.yaxis.set_major_locator(plt.MultipleLocator(Idist))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator([12]))
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
    plt.xticks(rotation=90, fontsize='medium')
    plt.yticks(fontsize='medium')
    plt.tight_layout()
    fig.savefig(OUTDIR+'6.1_max '+customer+'_max_current_total period.png', format = 'png')
    display(fig)
    plt.close("all")  
    
    
def plot_phase_max_current_weekly():
    # Max Current
    # Subplots per week
    #----------------------------------

    # Create dataframe for weekly subplots
    #----------------------------------
    dfIweekS_L1 = dfImax[['a_max_current']].copy()
    dfIweekS_L1['Week']='CW ' + dfIweekS_L1.index.isocalendar().week.astype(str)
    dfIweekS_L1.reset_index(inplace = True, drop = False)
    dfIweekS_L1.set_index(['Week'], inplace=True, append = True)
    dfIweekS_L1 = dfIweekS_L1.unstack(1)
    
    dfIweekS_L2 = dfImax[['b_max_current']].copy()
    dfIweekS_L2['Week']='CW ' + dfIweekS_L2.index.isocalendar().week.astype(str)
    dfIweekS_L2.reset_index(inplace = True, drop = False)
    dfIweekS_L2.set_index(['Week'], inplace=True, append = True)
    dfIweekS_L2 = dfIweekS_L2.unstack(1)
                           
    dfIweekS_L3 = dfImax[['c_max_current']].copy()
    dfIweekS_L3['Week']='CW ' + dfIweekS_L3.index.isocalendar().week.astype(str)
    dfIweekS_L3.reset_index(inplace = True, drop = False)
    dfIweekS_L3.set_index(['Week'], inplace=True, append = True)
    dfIweekS_L3 = dfIweekS_L3.unstack(1)

    # Plot weekly subplots
    #----------------------------------
    j = int(len(dfIweekS_L1.columns)/2)
    fig = plt.figure(1, dpi=300, figsize=(12,j*3), facecolor="white")
    for n in range(j):
        # Plot one subplot per week
        ax = fig.add_subplot(j,1,n+1)
        ax.plot(dfIweekS_L1[dfIweekS_L1.columns[n]], dfIweekS_L1[dfIweekS_L1.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase a', color=colorI[0])
        ax.plot(dfIweekS_L2[dfIweekS_L2.columns[n]], dfIweekS_L2[dfIweekS_L2.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase b', color=colorI[1])
        ax.plot(dfIweekS_L3[dfIweekS_L3.columns[n]], dfIweekS_L3[dfIweekS_L3.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase c', color=colorI[2])
        # General formatting for all subplots
        ax.xaxis.set_major_locator(mpl.dates.HourLocator([0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%a %d-%m %H:%M'))
        ax.set_ylabel('Max Current [A] \n', fontsize='large')
        ax.yaxis.set_major_locator(plt.MultipleLocator(Idist))        
        ax.set_ylim(Imin, Imax)  # Adjust if needed, e.g., to (-5, 100)
        plt.xticks(rotation=90, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='best', frameon = True)
        if n == 0:
            ax.set_title('Max Current '+customer+' - weekly subplots \n', fontsize='large')
            ax.set_xlim(dfIweekS_L1[dfIweekS_L1.columns[n]].max() - timedelta(days=7),dfIweekS_L1[dfIweekS_L1.columns[n]].max())
        else:
            ax.set_xlim(dfIweekS_L1[dfIweekS_L1.columns[n]].min(),dfIweekS_L1[dfIweekS_L1.columns[n]].min() + timedelta(days=7))
    ax.set_xlabel('\n Day', fontsize='large')
    fig.savefig(OUTDIR+'6.2_max '+customer+'_max_current_weekly subplots.png', format = 'png')
    display(fig)
    plt.close("all")  
    
    
def plot_phase_max_current_daily(): 
    # Max Current Subplots per day
    #----------------------------------
    
    # Create dataframe for daily subplots
    #----------------------------------
    dfIday = dfImax.copy()
    dfIday['Date']=dfIday.index.date
    dfIday.reset_index(inplace = True, drop = False)
    dfIday.set_index(['Date'], inplace=True, append = True)
    dfIday = dfIday.unstack(1)
    
    # Plot daily subplots
    #----------------------------------
    j = int(len(dfIday.columns)/4)  # Note: Original has /4 because of 4 columns (timestamp + 3 phases), but dfImax has 3 columns—keep as is if it works
    fig = plt.figure(1, dpi=300, figsize=(12,j*3), facecolor="white")
    fig.suptitle('Max Current '+customer+' - daily subplots \n\n\n\n', fontsize='x-large')
    for n in range(j):
        ax = fig.add_subplot(math.ceil(j/2),2,n+1)
        ax.plot(dfIday[dfIday.columns[n]], dfIday[dfIday.columns[int(n+j)]], '-', linewidth = 0.5, label = dfIday[dfIday.columns[n]].min().date().strftime('%a %d-%m-%y')+'\nPhase a', color=colorI[0])
        ax.plot(dfIday[dfIday.columns[n]], dfIday[dfIday.columns[int(n+j*2)]], '-', linewidth = 0.5, label= 'Phase b', color=colorI[1])
        ax.plot(dfIday[dfIday.columns[n]], dfIday[dfIday.columns[int(n+j*3)]], '-', linewidth = 0.5, label= 'Phase c', color=colorI[2])
        ax.xaxis.set_major_locator(mpl.dates.HourLocator(range(0,24,2)))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M'))
        ax.yaxis.set_major_locator(plt.MultipleLocator(Idist))        
        ax.set_ylim(0, Imax)  # Adjust if needed, e.g., to (0, 100)
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, pos: '%.0f' % y))
        plt.xticks(rotation=45, fontsize='medium')
        plt.yticks(fontsize='medium')
        plt.tight_layout()
        ax.legend(loc='upper right', frameon = True)
        if n == 0:
            ax.set_xlim(dfIday[dfIday.columns[n]].max() - timedelta(days=1),dfIday[dfIday.columns[n]].max())
            ax.set_ylabel('Max Current [A] \n', fontsize='large')
        else:
            ax.set_xlim(dfIday[dfIday.columns[n]].min(),dfIday[dfIday.columns[n]].min() + timedelta(days=1))
    ax.set_xlabel('\n Daytime', fontsize='large')
    plt.subplots_adjust(top=0.96)
    fig.savefig(OUTDIR+'6.3_max '+customer+'_max_current_daily subplots.png', format = 'png')
    display(fig)
    plt.close("all")       
        
           
    #End of the added section for Max current

    
    
    
    
    
def plot_phase_PF_total():     
    # Power factor
    #Plot total period
    
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(df['a_max_act_power'] / df['a_max_aprt_power'], '-', linewidth =0.5, color=colorPF[0], label = "Phase a")
    ax.plot(df['b_max_act_power'] / df['b_max_aprt_power'], '-', linewidth =0.5, color=colorPF[1], label = "Phase b")
    ax.plot(df['c_max_act_power'] / df['c_max_aprt_power'], '-', linewidth =0.5, color=colorPF[2], label = "Phase c")
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

    #dfPFweekS_L1 = (df['a_max_act_power'] / df['a_max_aprt_power']).copy()
    dfPFweekS_L1 = (df['a_max_act_power'] / df['a_max_aprt_power']).to_frame(name='PF')
    dfPFweekS_L1['Week']='CW ' + dfPFweekS_L1.index.isocalendar().week.astype(str)
    dfPFweekS_L1.reset_index(inplace = True, drop = False)
    dfPFweekS_L1.set_index(['Week'], inplace=True, append = True)
    dfPFweekS_L1 = dfPFweekS_L1.unstack(1)
    
    #dfPFweekS_L2 = (df['b_max_act_power'] / df['b_max_aprt_power']).copy()
    dfPFweekS_L2 = (df['b_max_act_power'] / df['b_max_aprt_power']).to_frame(name='PF')
    dfPFweekS_L2['Week']='CW ' + dfPFweekS_L2.index.isocalendar().week.astype(str)
    dfPFweekS_L2.reset_index(inplace = True, drop = False)
    dfPFweekS_L2.set_index(['Week'], inplace=True, append = True)
    dfPFweekS_L2 = dfPFweekS_L2.unstack(1)
                         
    #dfPFweekS_L3 = df(['c_max_act_power'] / df['c_max_aprt_power']).copy()
    dfPFweekS_L3 = (df['c_max_act_power'] / df['c_max_aprt_power']).to_frame(name='PF')
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
        ax.plot(dfPFweekS_L1[dfPFweekS_L1.columns[n]], dfPFweekS_L1[dfPFweekS_L1.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase a', color=colorPF[0])
        ax.plot(dfPFweekS_L2[dfPFweekS_L2.columns[n]], dfPFweekS_L2[dfPFweekS_L2.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase b', color=colorPF[1])
        ax.plot(dfPFweekS_L3[dfPFweekS_L3.columns[n]], dfPFweekS_L3[dfPFweekS_L3.columns[int(n+j)]], '-', linewidth = 0.5, label= 'Phase c', color=colorPF[2])
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
    #dfPFday = df['a_max_act_power'] / df['a_max_aprt_power'],df['b_max_act_power'] / df['b_max_aprt_power'],df['c_max_act_power'] / df['c_max_aprt_power'].copy()
    #dfPFday = dfP.copy()
    dfPFday = pd.DataFrame({
    'PF_a': df['a_max_act_power'] / df['a_max_aprt_power'],
    'PF_b': df['b_max_act_power'] / df['b_max_aprt_power'],
    'PF_c': df['c_max_act_power'] / df['c_max_aprt_power'],
})
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
        ax.plot(dfPFday[dfPFday.columns[n]], dfPFday[dfPFday.columns[int(n+j)]], '-', linewidth = 0.5, label = dfPFday[dfPFday.columns[n]].min().date().strftime('%a %d-%m-%y')+'\nPhase a', color=colorPF[0])
        ax.plot(dfPFday[dfPFday.columns[n]], dfPFday[dfPFday.columns[int(n+j*2)]], '-', linewidth = 0.5, label= 'Phase b', color=colorPF[1])
        ax.plot(dfPFday[dfPFday.columns[n]], dfPFday[dfPFday.columns[int(n+j*3)]], '-', linewidth = 0.5, label= 'Phase c', color=colorPF[2])
        
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
    #df['Time'] = pd.to_datetime(dfRad['timestamp'], unit='s')
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
        dfSim['Act '+str(i)+' kWp'] = dfSim.apply(lambda row: calc_PVact(row['Pp'],row['Max '+str(i)+' kWp']), axis=1)
    
        
    #Calculate daily representation of simulation
    
    dfSimDay = dfSim.copy()
    dfSimDay = dfSimDay.groupby(dfSim['Time']).mean(numeric_only=True)
    
    #Plot daily average with PV production
    #PVact
    
    fig = plt.figure(1, dpi=300, figsize=(12,6), facecolor="white")
    ax = plt.axes()
    ax.plot(dfSimDay['Pp'], '-', linewidth = 2, label=" Average consumption")
    
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
    dfPVd = dfPVd.replace([np.inf, -np.inf], np.nan)  # Replace infinite values with NaN
    dfPVd = dfPVd.fillna(0)  # Replace NaNs with 0
    dfPVd = dfPVd.round().astype(int)
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
    dfPweekSMA['mean'].to_csv(customer+' measurement, SunnyDesign.csv', index=False)
    
            
