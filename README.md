# EQS Measurement Analyser

Turns the Econ and Shelly load-profile notebooks into a web application. Upload
a measurement CSV, set the plant details, and get every graph the notebooks
produced, the energy and PV-yield summaries, and a preliminary comparison of
candidate system sizes.

The calculations are not a rewrite. Every figure function is the original
notebook code, copied by a generator script that records exactly what it
changed on the way.

---

## Contents

- [What it does](#what-it-does)
- [Supported file formats](#supported-file-formats)
- [Installation](#installation)
- [Running it locally](#running-it-locally)
- [How the application works](#how-the-application-works)
- [Required inputs](#required-inputs)
- [Validation rules](#validation-rules)
- [What comes out](#what-comes-out)
- [System-size guidance](#system-size-guidance)
- [Known limitations](#known-limitations)
- [Data privacy and retention](#data-privacy-and-retention)
- [Troubleshooting](#troubleshooting)
- [Updating the analysis logic](#updating-the-analysis-logic)

---

## What it does

1. Detects whether an uploaded CSV came from an Econ logger or a Shelly meter.
2. Checks the file properly before analysing it, and says what is wrong.
3. Runs the original analysis: 43 figures for Econ, 32 for Shelly.
4. Produces the energy summary, the PV yield tables and the generation
   simulation for every candidate system size.
5. Ranks those sizes against the measures the existing analysis produces, and
   explains each ranking in plain language.
6. Packages everything as a ZIP, a spreadsheet and a PDF report.

---

## Supported file formats

### Econ power-quality logger

| | |
|---|---|
| Separator | `;` |
| Encoding | Windows "ansi" (cp1252); UTF-8 also accepted |
| Time column | `Time`, formatted `DD/MM/YYYY HH:MM:SS` |
| Figures | 43 |
| Also accepted | the same export saved as `.xlsx` (see below) |

Required columns: `Time`, `Frequency [Hz]`, `Pactive total avg [kW]`,
`Qreactive total avg [kvar]`, and for each of L1, L2, L3: `Urms avg [V]`,
`Urms max [V]`, `Irms avg [A]`, `Irms max [A]`, `Pactive avg [kW]`,
`U THD avg [%]`, `PF avg [-]`.

Power is measured directly. Total apparent power is `sqrt(P² + Q²)`;
per-phase apparent power is `P / PF`.

**Idle rows.** The Econ writes a row every interval whether or not it is
measuring: status `Code` 256, every value zero. A file can therefore have no
timestamp gaps at all and still hold almost no measurements. Coverage is
counted over rows where `Code` is 0, not over rows that exist. The idle rows
are never removed — the analysis sees the file exactly as the notebook did.

**Workbook uploads.** If someone opens the export in Excel and saves it, you
get an `.xlsx`. Upload it anyway. Excel does not split a semicolon-separated
file into columns, so the whole row sits in one cell; the app reads those
cells back as the text the file started as. A test asserts the CSV and the
workbook give identical summaries.

### Shelly energy meter

| | |
|---|---|
| Separator | `,` |
| Encoding | UTF-8 |
| Time column | `timestamp`, Unix epoch seconds |
| Figures | 32 |

Required columns: `timestamp`, and for each of a, b, c: `avg_voltage`,
`avg_current`, `max_current`, `total_act_energy`, `max_act_power`,
`max_aprt_power`.

Power is **derived**. `*_total_act_energy` is the watt-hours accumulated during
one sample interval, so watts is that value times `60 / RateMin`. This was
verified against the meter's own `min_act_power` and `max_act_power` columns on
a real export: the derived value falls inside that envelope on every row.

The meter measures no reactive power, no voltage THD and no frequency, so
those charts do not exist for Shelly. It does report apparent power directly,
which is why the Shelly apparent-power charts are of a maximum where the Econ
ones are of an average — same chart numbers, different quantity.

### Irradiation file

Both devices need one: `Time,G [W/m²]`, one row per hour from `00:00` to
`23:00`, plus a closing `23:59` row. Kampala and Mbale are bundled in
`sample_data/`.

---

## Installation

Python 3.10 or newer.

```bash
git clone https://github.com/LouisLoli-wq/eqs-measurement-analyser.git
cd eqs-measurement-analyser
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Running it locally

```bash
streamlit run app.py
```

Your browser opens at `http://localhost:8501`. The console window is the
application; closing it stops the app.

To let colleagues on the same network use it, add `--server.address=0.0.0.0`
and send them `http://<your-ip>:8501`. See `DEPLOYMENT.md` for the options,
including what that means for customer data.

Run the tests with:

```bash
pytest                # 64 tests, about 70 seconds
pytest -m "not slow"  # skip the full figure runs, about 3 seconds
```

---

## How the application works

**Page 1 — Home.** What the tool accepts, what it does with your data, and
what it will not tell you.

**Page 2 — Upload and configuration.** Device (or auto-detect), measurement
CSV, irradiation CSV, customer and project details, analysis settings,
candidate system sizes, and an axis panel pre-filled from your file.

**Page 3 — Data validation.** File summary, measurement period, every finding,
coverage by hour, by day and by tariff window, the largest gaps, and the
detected columns. Blocking issues stop here. Warnings have to be acknowledged
before the analysis will run.

**Page 4 — Analysis results.** Summary tables, the size comparison with its
reasoning, and every figure grouped by section.

**Page 5 — Downloads.** ZIP, spreadsheet, PDF, and each figure on its own.
Also the button that deletes this session's temporary files.

---

## Required inputs

| Input | Where it came from | Effect |
|---|---|---|
| Device | new — the combined notebook's `DEVICE` | Chooses the adapter |
| Customer name | `customer` | Every chart title and filename |
| Site or location | new | Report metadata only |
| Project reference | new | Report metadata only |
| Measurement CSV | `PathMeasurement` | The data |
| Irradiation CSV | `PathRadiation` | The PV simulation |
| Sample rate | `RateMin` | Resampling; Shelly's Wh-to-W conversion |
| Time offset | `deltatime` | Shifts timestamps, in hours |
| Power unit | `Yformat` | `1` for kW, `1e-3` for W |
| Date range | new | Restricts the analysis; the file is untouched |
| System sizes | `PPV` | Simulated, in kWp |
| Efficiency | `EtaPV` | PV rated to AC out |
| Offset | `Offset` | Keeps generation below consumption |
| Axis ranges | `Ymin/Ymax/Ydist` and the limits that were inside the plot functions | Chart scales |

Everything was a variable in the notebooks except device, location, project
reference and date range, which are new.

---

## Validation rules

Blocking, so the analysis will not run:

- the file is empty, undecodable, or has no field separator
- a workbook that cannot be opened
- only one column is found with the detected separator
- a required column is missing
- more than half the timestamps cannot be parsed, or none can
- no row in the file holds a measurement
- the date range leaves no rows

Warnings, which must be acknowledged:

- less than 80% of the measurement period actually recorded
- a tariff window with less than 50% of its hours measured
- duplicate timestamps, or rows out of order
- non-numeric values in a measurement column
- rows present but holding no measurement (Econ idle rows)
- physically implausible readings, such as voltage THD above 100% or a power
  factor above 1
- less than one full day of data
- some timestamps unparseable

Information:

- days with no data at all
- blank values per column
- a measurement period under a week
- rows excluded by the date range

**The rule behind all of it: nothing is altered.** No rows are dropped, no
blanks filled, no outliers removed, no values coerced. Anything unusual is
reported and left where it is.

### Two ways a file can be emptier than it looks

A Shelly meter goes offline and simply stops writing. The gap is visible in
the timestamps.

An Econ keeps writing. Status `Code` 256, every value zero, one row a minute,
forever. Nothing in the timestamps betrays it.

The real Econ file this was tested against has **14,400 rows, every minute for
ten days, not one gap** — and 12,329 of those rows are idle. The site was
measured for about three hours a day. Counting timestamps would have called
that a perfect file.

So coverage is counted over rows that hold a reading. Both devices then flow
into the same reporting, below.

### Why "not measured" exists

The original `summary_energy` sums a daily average profile across three tariff
windows. When a window has no measurements the sum is zero, and the table
reports `0 kWh` — which on a customer's report reads as "nothing was used
then", not "we did not measure then".

This is not hypothetical, in either direction. The Shelly sample has no data
between 20:00 and 04:00 and the original code reports Peak as 0 kWh/day. The
Econ sample is worse: 86% idle, measured only between about 09:00 and 15:00,
and the original code reports a confident 11,315 kWh/year for a site it barely
saw.

So a window below 50% coverage is shown as `not measured`. The original
figure is preserved untouched in `result.energy_summary`; the annotated copy
is what the app and the reports display. The threshold is
`MIN_WINDOW_COVERAGE` in `src/config.py`.

---

## What comes out

| Output | Econ | Shelly |
|---|---|---|
| Figures (300 dpi PNG, original filenames) | 43 | 31 |
| Energy summary, per tariff window | yes | yes |
| Maximum PV yield per size | yes | yes |
| Direct PV consumption and share | yes | yes |
| Summary sheet (figure 12) | yes | yes |
| SunnyDesign load-profile CSV | yes | not produced by the Shelly notebook |
| Voltage THD, frequency | yes | not measured by the meter |

Plus the ZIP (figures and the settings used), the XLSX (every table, the
validation findings, the hourly coverage, the settings) and the PDF (cover,
basis, caveats, every figure).

---

## System-size guidance

**Read this before quoting anything the tool says.**

The original notebooks contain no sizing rule. `PPV` is a list an engineer
types in; nothing in the code selects from it. What the notebooks compute, per
candidate size, is the ceiling yield, the part actually consumed on site, the
share of generation used, and the share of load covered.

This tool ranks the sizes you enter against the last two, and says why each
ranks where it does. It keeps three things apart, on screen and in every
export:

1. **Calculated from your data** — annual consumption, measurement period,
   share of the period actually recorded.
2. **Assumptions you entered** — EtaPV, Offset, the candidate sizes, the
   irradiation profile.
3. **Generated by this tool** — the ranking and its reasoning.

The thresholds it ranks against (85% minimum direct use, 60% maximum share of
load) are **placeholders with no engineering authority**. They are at the top
of `src/sizing.py`. Until Equator Solar sets them and flips
`THRESHOLDS_APPROVED`, every output carries a preliminary label.

What an engineer still has to supply, and why the tool cannot: the acceptable
floor for direct-use share (inverter clipping, export rules, whether storage
is in scope), the target share of load (commercial, not technical), roof or
ground area and orientation, inverter and transformer limits, tariff, capital
cost and payback horizon, and whether the measured period is representative of
the year.

---

## Known limitations

- **One irradiation day, applied to all 365.** Seasonal variation is not
  modelled. This is how the original analysis worked.
- **30-day months, 365-day years**, as in `summary_energy`.
- **Tariff windows are fixed** at 00:00–06:00, 06:00–18:00, 18:00–24:00.
  Change them in `TARIFF_WINDOWS` in `src/config.py`.
- **One analysis at a time per server.** The plotting modules keep state in
  module globals, exactly as the notebooks did, so a second run queues behind
  the first.
- **A full run takes about a minute**, and longer for measurement periods over
  a few weeks, because the daily subplots grow with the number of days.
- **Implausible readings are reported, not corrected.** Voltage THD above 100%
  and power factor above 1 both occur in real exports around supply
  transients. They stay in the data and in the charts; they are only excluded
  from the suggested axis ranges, so a handful of bad rows cannot flatten a
  chart.
- **No battery or export modelling.** `calc_PVact` caps generation at
  consumption; anything above that is simply not counted.

---

## Data privacy and retention

- Uploads are held in a temporary folder unique to your browser session, and
  deleted when you press **Clear this analysis** on page 5.
- Folders left behind by an abandoned session are swept after six hours
  (`Session.STALE_AFTER_HOURS`).
- Nothing is written into the repository. `.gitignore` blocks `*.csv`,
  `*.png`, `*.xlsx`, `*.pdf`, `*.zip` and `*.ipynb`, with a narrow exception
  for the two public irradiation profiles.
- No measurement file, customer name, credential or local path is committed.
- The analysis runs on whatever machine hosts the app. On a public cloud
  service, the upload leaves your premises — see `DEPLOYMENT.md`.
- The app has no login. Anyone who can reach it can use it.

---

## Troubleshooting

**"Could not tell which logger produced this file."** The columns match
neither signature. Check you are uploading the measurement export rather than
a summary or a converted spreadsheet, then pick the device manually.

**"Only one column was found using ';' as the separator."** The file was
probably opened and re-saved in Excel, which changes the separator. Export it
again from the logger.

**A required column is missing.** The export template has changed, or the
wrong template was used. The message lists exactly what is missing.

**Coverage is very low.** The logger was offline for part of the period. The
figures still draw, but the energy totals are averages over the data that
exists. Check the gap table on page 3.

**Charts look flat or clipped.** Open the axis panel on page 2 and raise
`Ymax`. The suggestion clears the peak in your file, but a single spike can
stretch the scale and flatten everything else.

**A step failed but the rest worked.** Page 4 names the step and the error,
and every figure that succeeded is still produced.

**The app will not start.** Check the virtual environment is active and
`pip install -r requirements.txt` completed. `pytest -m "not slow"` is a quick
way to confirm the installation.

---

## Updating the analysis logic

The plotting modules are generated, not maintained by hand. When a notebook
changes:

```bash
python tools/generate_plot_modules.py \
    --econ   "path/to/Econ code with Max apparent & Max current.ipynb" \
    --shelly "path/to/Shelly code.ipynb"
pytest
```

The generator copies the notebook's function cell verbatim and applies a fixed
list of patches, which it prints. If a patch it needs is missing it fails
loudly rather than producing a module that silently does the wrong thing.

Adding a new figure to a notebook also means adding it to `ECON_STEPS` or
`SHELLY_STEPS` in the generator, otherwise it will not be called. The
generator checks every name in those lists exists and refuses to run if one
does not.

To add a third logger, write `src/adapters/<name>.py` to the interface in
`src/adapters/base.py` and register it in `ADAPTERS`. Nothing outside that
folder knows a column name.

See `TECHNICAL_NOTES.md` for the full list of changes made to the original
code and why, and `USER_GUIDE.md` for a walkthrough aimed at non-technical
staff.
