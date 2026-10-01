# Sample data

## What is here

| File | Source | Why it is safe to commit |
|---|---|---|
| `irradiation_kampala.csv` | PVGIS, Kampala | Public irradiance data. No customer in it. |
| `irradiation_mbale.csv` | PVGIS, Mbale | Public irradiance data. No customer in it. |

Both are the shape the analysis expects: one row per hour, `Time,G [W/m²]`,
plus a closing `23:59` row.

## What is deliberately not here

**No measurement file.** Econ and Shelly exports are customer data — a load
profile shows when a site is occupied, when it shuts down, and how much plant
is running. None is committed, and `.gitignore` blocks `*.csv` outside this
folder so one cannot be added by accident.

The tests do not need one. `tests/conftest.py` builds synthetic Econ and
Shelly files from the column specification in `src/file_detection.py`, with a
realistic daily load shape and the option of punching gaps in them. That keeps
the suite runnable on a clean checkout.

## Testing with a real file

Put it anywhere outside the repository and upload it through the app. If you
must keep one nearby, use a folder that git ignores, and never `git add -f`
it.
