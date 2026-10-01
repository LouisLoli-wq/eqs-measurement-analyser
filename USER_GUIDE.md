# User guide

For anyone producing a measurement report. No Python needed.

---

## Before you start

You need two files:

1. **The measurement file** straight from the logger — the Econ export or the
   Shelly export. A CSV is best. If someone has already opened it in Excel and
   saved it as `.xlsx`, upload that anyway; the app reads it back. The
   readings are the same either way.
2. **An irradiation CSV** for the site. Kampala and Mbale are built in. Only
   upload your own if the site needs a different profile.

## Step 1 — Open the app

Either the link a colleague sent you, or on your own machine:

```
streamlit run app.py
```

Read the home page once. The part that matters: **the system sizes this tool
suggests are preliminary and need an engineer to sign them off.**

## Step 2 — Upload and configure

Go to **2 · Upload and configuration**.

Leave the device on **Auto-detect**. Drag in the measurement CSV. The app
tells you what it found:

- *"Detected Econ power-quality logger"* — nothing to do.
- *"Probably Shelly…"* — check it is right, and set the device by hand if not.
- *"Could not tell which logger…"* — pick the device yourself.

Pick a bundled irradiation profile, or upload your own.

Fill in the customer name. It goes into every chart title and every filename,
so spell it the way the report should read. Location and project reference are
for the report header only and change no number.

Under **Analysis settings**, the sample rate is read from the timestamps —
leave it. Set a time offset only if you know the logger clock was wrong. The
power unit is chosen for you: kW for Econ, W for Shelly.

Under **Proposed system sizes**, type the kWp figures you want compared, for
example `150, 200, 250, 300`. Any number of sizes. Leave efficiency and offset
alone unless the job calls for something else.

**Leave the axis panel closed.** The app reads sensible ranges off your file.
Open it only to force a particular scale, such as making two sites comparable
side by side.

## Step 3 — Check the data

Press **Check the data**. This page is worth reading properly.

**Measurement period.** From, to, span, and how much was actually recorded. If
"Recorded" is well under 100%, the logger was offline for part of the period.

**Findings.** Red stops the analysis and has to be fixed. Amber is a warning
you must tick to acknowledge. Blue is information.

**Coverage.** The chart shows how much of each hour of the day was recorded.
The table shows the three tariff windows. A window under 50% is reported as
**"not measured"** instead of a number, because a window with no data behind it
would otherwise appear as `0 kWh` — which reads like the site used nothing,
when in fact nothing was measured. If you see this, say so in the report.

When you are satisfied, tick the acknowledgement and press **Run the
analysis**. It takes about a minute. If someone else is running one, yours
starts when theirs finishes.

## Step 4 — Read the results

**Summary tables.** Consumption per day, month and year; maximum PV yield per
size; direct consumption and share.

**Proposed system sizes.** A ranking with a one-line reason per size, and the
inputs split three ways: what came from the measurements, what you typed, and
what the tool worked out. Expand any size to see the reasoning.

Say this part out loud when you hand the report over: **these are preliminary.
The tool does not know the roof area, the orientation, the inverter limits, the
tariff or the payback.** An engineer decides the size.

**Figures.** Grouped by section. Same numbering and filenames as before.

## Step 5 — Download

- **All figures (ZIP)** — every PNG plus a text file recording the settings
  used. This is the one to keep.
- **Summary (XLSX)** — the tables, the validation findings, the hourly
  coverage and the settings, one sheet each.
- **Report (PDF)** — press Build first. Cover page, the basis, the caveats,
  then every figure. Takes a few seconds.

Individual figures are listed underneath if you only need one.

When you are done, press **Clear this analysis** at the bottom. That deletes
the uploaded file and the generated figures from the machine running the app.

---

## Things that go wrong

**"Only one column was found using ';' as the separator."** A CSV that has
been through Excel and come out with the wrong separator. Either export it
again from the logger, or send the `.xlsx` itself — the app handles that.

**"12,329 of 14,400 rows hold no measurement."** The Econ keeps writing rows
when it is not measuring, so the file looks complete while most of it is
empty. The figures still draw, but the energy totals only reflect the hours
the logger was actually recording. Check the coverage chart before quoting
any annual figure.

**"Physically implausible readings."** A few rows with THD above 100% or a
power factor above 1, usually where the supply cut in or out. They are left in
the data and shown on the charts; they are only kept out of the automatic axis
ranges so they cannot flatten everything else.

**A required column is missing.** The wrong export template. The message names
exactly what is absent.

**The charts look flat.** One spike stretched the scale. Open the axis panel
on page 2 and halve `Ymax`.

**Peak shows "not measured".** The meter recorded nothing in the evening. Not
a fault in the tool. Either accept it and note it in the report, or get a
longer measurement.

**The app says another analysis is running.** One at a time per server. Yours
starts automatically.

---

## What the tool will not do

- Decide a system size.
- Account for roof area, orientation, shading, inverter or transformer limits.
- Model a battery, or exported energy.
- Model seasons — one irradiation day is applied to all 365, as in the
  original spreadsheet analysis.
- Fill in missing data. Gaps stay gaps, and are reported.
