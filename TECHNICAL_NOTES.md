# Technical notes

What was changed on the way from the notebooks to this application, and why.
Anyone auditing whether the numbers still mean what they used to should read
this first.

---

## 1. Provenance of the plotting code

`src/plots/econ_plots.py` and `src/plots/shelly_plots.py` are **generated**.
`tools/generate_plot_modules.py` reads the function cell out of each notebook,
copies it verbatim, and applies a fixed list of textual patches. Nothing is
retyped or re-implemented.

The generator fails loudly if a patch it expects is not found, so a notebook
that has drifted cannot silently produce a module that does the wrong thing.
It also checks that every function named in `STEPS` is actually defined.

| Notebook | Figures | Steps |
|---|---|---|
| Econ code with Max apparent & Max current.ipynb | 43 | 44 |
| Shelly code.ipynb | 32 | 32 |

The combined notebook was **not** used. See section 5.

---

## 2. Changes with no effect on the numbers

### 2.1 Configuration

The "Manual Input" cell became module-level variables set through
`configure()`. Same variables, same defaults, now settable from the interface.

### 2.2 Library compatibility

The notebooks were written against pandas around 1.0 and matplotlib around
3.1. Current versions reject the following, so each was replaced with the
equivalent that produces identical results.

| Original | Replacement | Why |
|---|---|---|
| `DatetimeIndex.week` | `.isocalendar().week` | removed in pandas 1.1 |
| `resample(...).mean()` | `.mean(numeric_only=True)` | pandas 2.0 raises on mixed frames |
| `tick_params(labelbottom='off')` | `labelbottom=False` | matplotlib 3.3 wants bools |
| `pd.to_datetime(..., format='%Y/%m/%d %H:%M:%S')` on `1900-01-01 …` strings | `_to_datetime_flex` | pandas 2.0 is strict; the separator never matched |
| `encoding='ansi'` | try cp1252, latin-1, utf-8 | `ansi` is a Windows-only alias |
| `plt.style.use('seaborn-whitegrid')` | `seaborn-v0_8-whitegrid`, falling back | renamed in matplotlib 3.6 |
| `fig.savefig('Graphs/'...)` | `OUTDIR` | per-session output folders |

The date-format one is worth spelling out. Both notebooks build synthetic
timestamps by string concatenation — `'1900-01-01 ' + time.astype(str)` — and
then parse them with `format='%Y/%m/%d %H:%M:%S'`. The string has hyphens and
the format has slashes. Old pandas accepted it; pandas 2 raises. The
replacement tries the layouts these strings actually take and falls back to
element-wise inference. No value changes.

### 2.3 Axis limits

Limits that were literals inside plotting functions became named settings,
with defaults equal to the original literals.

| Quantity | Original literal | Setting |
|---|---|---|
| Voltage | `150, 300` step `20` | `Umin, Umax, Udist` |
| Current (Econ) | `-5, 100` step `10` | `Imin, Imax, Idist` |
| Current (Shelly) | `-5, 50` step `10` | `Imin, Imax, Idist` |
| Voltage THD | `0, 40` step `8` | `THDmin, THDmax, THDdist` |
| Power factor | `0.0, 1.1` step `0.1` | `PFmin, PFmax, PFdist` |
| Frequency | `40, 60` step `2` | `Fmin, Fmax, Fdist` |
| Apparent power (Shelly) | `50000` step `5000` | `Amax, Adist` |

This is what lets the app propose limits from the uploaded file. Leaving them
at the defaults reproduces the notebooks exactly.

---

## 3. Corrections, each behind a flag

Both are in `src/config.py`. Setting either to `True` restores the original
behaviour.

### Defect 1 — Econ graph 4.1 divides L3 by L2's power factor

In `plot_phase_power_apparent_total`:

```python
ax.plot(df['L1 Pactive avg [kW]']/df['L1 PF avg [-]'], ...)   # L1 / L1  ok
ax.plot(df['L2 Pactive avg [kW]']/df['L2 PF avg [-]'], ...)   # L2 / L2  ok
ax.plot(df['L3 Pactive avg [kW]']/df['L2 PF avg [-]'], ...)   # L3 / L2  wrong
```

The weekly (4.2) and daily (4.3) versions of the same chart use `L3 PF` for
L3, and the combined notebook had already fixed it. Graph 4.1 was the outlier,
which is what makes it a typo rather than an intention.

**Effect:** the L3 trace on graph 4.1 only. Every other chart, and every
summary figure, is unaffected — per-phase apparent power feeds no total.

**Flag:** `PRESERVE_LEGACY_PF_TYPO`, default `False` (corrected).

### Defect 3 — Shelly's hard-coded ×60

```python
df['Pp'] = (a_total_act_energy + b_ + c_) * 60
```

`total_act_energy` is watt-hours accumulated over **one sample interval**, so
watts is `Wh × 60 / RateMin`. The bare `60` assumes a one-minute interval.

Verified on a real 2,845-row export: `energy × 60` falls inside
`[min_act_power, max_act_power]` on 100% of rows at a one-minute rate, so the
formula is right and only the constant is fragile.

**Effect:** none at `RateMin = 1`, which is what every file seen so far uses.
At 5 minutes the original would overstate power fivefold.

**Flag:** `PRESERVE_LEGACY_X60`, default `False` (rate-derived).

### Defect 2 — the combined notebook's Shelly path

Not carried across; see section 5.

---

## 4. The one output that is presented differently

`summary_energy` sums a daily average profile across three tariff windows.
Where a window holds no measurements, the sum is `0` and the table reports
`0 kWh` — indistinguishable, on a customer's report, from a measured zero.

The calculation is untouched. `AnalysisResult.energy_summary` holds exactly
what the notebook produces. A second frame,
`AnalysisResult.energy_summary_annotated`, replaces the figure with
`not measured` for any window below `MIN_WINDOW_COVERAGE` (default 50%), and
that is what the app and the exports display. Coverage is computed per hour of
day from the timestamps that exist.

The real Shelly sample this was built against has no data between 20:00 and
04:00 and only 20% coverage overall, and the original code reports Peak
consumption as `0 kWh/day`.

---

## 4a. Rows that exist but hold no measurement

Added after a real Econ export was tested.

`Econ Measurement_Rwera MCC_2026.08.20` holds 14,400 rows, one a minute for
ten days, **with no timestamp gaps whatsoever**. 12,329 of them (85.6%) carry
status `Code` 256 and zero in every measurement column: the logger was
powered, writing rows, and not measuring.

Coverage based on timestamps called that file 100% complete and raised no
warning. `summary_energy` averaged real zeros into the night hours and
reported 11,315 kWh/year, for a site whose supply was actually observed for
about three hours a day between 09:00 and 15:00.

The fix is a per-device `measuring_mask()`:

| Device | Idle row | Test |
|---|---|---|
| Econ | status `Code` 256, all values zero | `Code == 0`, falling back to any phase voltage above zero |
| Shelly | does not occur; the meter stops writing | any phase voltage above zero |

Coverage, the hourly and daily profiles, the tariff-window check and the axis
suggestions all run over the measuring rows. The analysis itself does not:
every row the file contains is passed to the plotting code exactly as the
notebook received it. A file with no measuring rows at all is a blocking
error.

This matters more than the Shelly gap case, because nothing about the file
looks wrong.

## 4b. Implausible readings

The same export holds 13 to 14 rows per phase with voltage THD above 100%,
peaking at 2,387%, all within measuring rows and clustered around the supply
cutting in and out. Left alone, they set the suggested THD axis to 0–2500 and
flattened every real reading (median 1.9%) onto the baseline.

`implausible_values()` reports them, per phase and per kind, including power
factor above 1. The values stay in the data and in the charts. They are
excluded only from the axis suggestion, where the sane maximum is used — not a
quantile, because THD on these sites is bimodal: a tight band near 2% with a
thin tail into the tens that a quantile would clip off the chart.

## 4c. Workbook uploads

Logger exports arrive as `.xlsx` when someone opens the CSV in Excel and
saves it. Two shapes occur, and `xlsx_to_csv_bytes` handles both:

- **One column holding whole delimited rows.** Excel opened a
  semicolon-separated file on a machine whose list separator is a comma and
  never split it. The cells already are the CSV, so they are joined back
  together. This is what the Rwera file was.
- **One column per field**, written back out with `;`.

A test asserts the CSV and the workbook produce identical energy and PV
summaries.

## 5. Why the combined notebook was not used

`Combined code (Not approved).ipynb` was inspected and set aside. Its
`configure_device()` idea — one config dictionary per device — is sound, and
the adapter layer here is a stricter version of it. The implementation had
three problems:

1. **Shelly power is 60 times too small.** `read_measurement_data` renames
   `a_total_act_energy` to `L1 Pactive avg [kW]` and never applies the
   conversion. Energy in watt-hours is then treated as power in kilowatts.
2. **Wrong encoding for Shelly.** Both devices are read with
   `encoding='ansi'`; Shelly exports are UTF-8.
3. **Figures lost.** It has 37 savefig targets against Econ's 43 and Shelly's
   32: the Econ max-apparent-power (3.4, 6.4–6.6) and max-current (6.7–6.10)
   sets are gone, as are the Shelly max-current charts.

Taking Econ and Shelly as the two sources of truth and putting the differences
in adapters keeps both outputs exactly as the engineers who signed them off
expect.

---

## 6. Format differences, for reference

| | Econ | Shelly |
|---|---|---|
| Separator | `;` | `,` |
| Encoding | cp1252 | UTF-8 |
| Time | `Time`, `DD/MM/YYYY HH:MM:SS` | `timestamp`, epoch seconds |
| Phases | L1 / L2 / L3 | a / b / c |
| Power | measured, kW | derived from energy, W |
| `Yformat` | `1` | `1e-3` |
| Apparent power | `sqrt(P²+Q²)`, an average | sum of `max_aprt_power`, a maximum |
| Power factor | measured column | `max_act_power / max_aprt_power` |
| THD, frequency | measured | not measured |
| Figures | 43 | 32 |

Chart numbering collides: `3.1` is *average* apparent power for Econ and
*maximum* apparent power for Shelly. Both were kept as they are, because the
filenames go into reports that already exist.

---

## 7. Architecture

```
app.py                     five pages, no analysis logic
src/config.py              business constants; AnalysisConfig
src/file_detection.py      encoding, delimiter, device identification
src/validation.py          inspects and reports; changes nothing
src/adapters/              the only code that knows a column name
src/plots/                 GENERATED; the notebooks' own figure code
src/analysis.py            orchestration, session folders
src/sizing.py              placeholder ranking, heavily caveated
src/reporting.py           ZIP, XLSX, PDF
tools/                     the generator
tests/                     64 tests, synthetic fixtures
```

Two constraints worth knowing about:

**The plotting modules hold state in module globals**, as the notebooks did.
Two analyses cannot run at once in one process, so `app.py` serialises them
with a lock and a second user simply queues.

**The measurement file is read twice** — once by the validator, once by the
plotting code, which opens the path itself as the notebook did. On files of a
few megabytes the cost is a fraction of a second, and the alternative is
patching the notebook's own reading logic, which is exactly the code this
project exists to leave alone.

---

## 8. Test coverage

64 tests, about 70 seconds.

| Module | Covers |
|---|---|
| `test_file_detection.py` | encodings, BOM, delimiters, device identification, rejection of empty, binary, single-column and ambiguous files |
| `test_validation.py` | required columns, timestamps, duplicates, gaps, coverage, non-numeric values, and that the frame is never modified |
| `test_econ_adapter.py` | column spec, axis suggestions, blackout handling, the PF-typo switch |
| `test_shelly_adapter.py` | the Wh-to-W conversion against the meter's own power columns, at 1 and 5 minute rates |
| `test_analysis.py` | full runs of both devices, missing columns, date range, session isolation and sweeping, all three export formats |
| `test_sizing.py` | ranking, the measured/assumed split, and that no output ever claims approval |

All fixtures are synthetic, built from the column specification. No customer
file is in the repository.

Both device paths have now been run against real exports:

| File | Rows | Result |
|---|---|---|
| Shelly `emdata_3CE90E7066B8` | 2,845 over 9.7 days | 31 figures, no errors, 44 s |
| Econ `Rwera MCC 2026.08.20` (.xlsx) | 14,400 over 10 days | 43 figures, no errors, 90 s |

Neither file is in the repository.
