# Changelog

All notable changes to this project are recorded here. Dates are ISO.

## [1.2.0] - 2026-10-01

### Added

- House style, taken from the Equator Solar "Site Visit & Data Capture" form
  so the two tools read as one set: the green `#188B44`, the `#EFF3F0` page on
  `#FFFFFF` cards, 16px cards and 12px inputs, the 1.5px field border and the
  form's left-rule callout for every message. Light and dark both follow the
  form's own `day` / `night` palettes. Tokens in `assets/theme.css`, loaded by
  `src/theme.py`; Streamlit's own keys in `.streamlit/config.toml`.
- The Equator Solar wordmark, above the sidebar navigation on every page and
  on the PDF report's cover. The ring from SOLAR, cropped square, is the
  browser-tab icon. Both are in `assets/`; a missing file falls back rather
  than stopping the app.
- Optional switch to draw the charts in house colours. Off by default: every
  report issued so far used the notebooks' colours, and a chart that changes
  colour between reports invites the question of what else changed.

### Changed

- Required inputs cut to four: measurement file, irradiation file, client
  name, five system sizes. Sample rate, power unit, clock offset and every
  chart scale are read from the file; the optional panel states what it found
  rather than asking for it.
- Chart scales are automatic per family, each with an Auto tick that can be
  cleared to fix a scale by hand. The ladder is finer and the headroom 5%
  rather than 10%, so an axis sits just above the data instead of at the next
  power of ten.
- The five size boxes start from measured peak demand instead of a hard-coded
  list, which offered 150-300 kWp on a site peaking at 10 kW. Candidates to
  simulate, not a recommendation.

### Fixed

- The irradiation uploader was disabled until a hidden "Upload my own" option
  was picked, with nothing on screen saying so. It is always active now, and
  an uploaded file simply wins over the bundled profile.

## [1.1.0] - 2026-10-01

Changes prompted by the first real Econ export, `Rwera MCC 2026.08.20`.

### Added

- **Idle-row detection.** The Econ writes a row every interval whether or not
  it is measuring: status `Code` 256, every value zero. The Rwera file has
  14,400 rows, no timestamp gaps, and 12,329 idle rows. Coverage, the hourly
  and daily profiles and the tariff-window check now count rows that hold a
  reading, through a per-device `measuring_mask()`. The rows themselves are
  untouched and still reach the analysis.
- **Implausible-value reporting.** Voltage THD above 100% and power factor
  above 1 are counted per phase and reported. They stay in the data and in the
  charts, and are excluded only from the suggested axis ranges.
- **Workbook uploads.** `.xlsx` and `.xlsm` are accepted, including the
  single-column shape Excel produces when it opens a semicolon-separated file
  without splitting it. A test asserts the CSV and the workbook give identical
  summaries.
- 21 further tests, 85 in total.

### Fixed

- Axis suggestions were computed over every row, so a file full of idle zeros
  put the voltage floor at zero and 13 bad THD readings put the THD ceiling at
  2500%. Suggestions now use measuring rows only and ignore implausible
  values.
- A file where no row holds a measurement is now a blocking error instead of
  an analysis of nothing.

## [1.0.0] - 2026-09-30

First release. Converts the Econ and Shelly analysis notebooks into a web
application without changing what they calculate.

### Added

- Streamlit application with five pages: Home, Upload and configuration, Data
  validation, Analysis results, Downloads.
- Device adapters for the Econ power-quality logger and the Shelly energy
  meter, each owning its own column names, units and derived quantities.
- Automatic device detection from the file's columns, with a confidence level
  and a manual override.
- File validation: encoding and delimiter detection, required-column check,
  timestamp parsing, duplicate and out-of-order detection, gap measurement,
  coverage per hour of day, per calendar day and per tariff window, and
  non-numeric value counts. Nothing is altered or discarded.
- Coverage-aware energy summary. A tariff window with less than 50% of its
  hours measured is reported as "not measured" instead of the 0 kWh the
  original code produced, alongside the untouched original figure.
- Preliminary system-size guidance, ranking the sizes entered against the
  direct-use share and load share the existing analysis already computes.
  Thresholds are placeholders and are labelled as such.
- Downloads: ZIP of all figures plus the settings used, XLSX of every summary
  table with the validation findings, and a PDF report with a cover, the
  basis, the caveats and every figure.
- Optional date-range filter, applied to the analysis only.
- Per-session temporary folders, deleted on request and swept after six hours.
- 64 tests across six modules, using synthetic fixtures.
- `tools/generate_plot_modules.py`, which regenerates the plotting modules
  from the original notebooks so they never have to be hand-edited.

### Changed from the original notebooks

- The "Manual Input" cell became the interface. No customer name, file path or
  axis limit is hard-coded anywhere.
- Axis limits that lived inside the plotting functions (voltage, current, THD,
  power factor, frequency, Shelly apparent power) became settings, so the app
  can propose them from the uploaded file. Defaults equal the original
  literals.
- Data loading no longer uses the Windows-only `ansi` codec and tolerates
  several timestamp layouts.
- Compatibility with current pandas and matplotlib: `DatetimeIndex.week`,
  `tick_params(labelbottom='off')`, strict datetime format strings, implicit
  `numeric_only`.

### Fixed

- Econ graph 4.1 divided L3 active power by L2's power factor. Graphs 4.2 and
  4.3 used L3 correctly, so 4.1 was the outlier. Revert with
  `PRESERVE_LEGACY_PF_TYPO = True` in `src/config.py`.
- Shelly power used a hard-coded `x60`, correct only at a one-minute sample
  rate. Now `60 / RateMin`, which is identical at one minute. Revert with
  `PRESERVE_LEGACY_X60 = True`.

### Not included

- The combined notebook was not used. On the Shelly path it renamed the energy
  columns to power columns without applying the conversion, making Shelly
  power 60 times too small, and it dropped the Econ max-current and
  max-apparent-power figures. TECHNICAL_NOTES.md sets this out.
- No approved sizing rule, because none exists in the source material.
