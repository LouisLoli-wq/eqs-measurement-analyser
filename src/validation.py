"""
Check an uploaded measurement file and report what is wrong with it.

The governing rule is that nothing here changes the data. Every function
inspects and reports; the caller decides whether to proceed. A problem the
validator cannot see is a problem that reaches the customer's report, so the
checks are deliberately blunt: say what is missing, say how much, say where.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as cfg
from . import file_detection as fd


@dataclass
class Issue:
    """One finding. Severity decides how the app presents it."""

    severity: str            # "error" | "warning" | "info"
    title: str
    detail: str = ""

    def __str__(self) -> str:
        return "%s: %s%s" % (self.severity.upper(), self.title,
                             " -- " + self.detail if self.detail else "")


@dataclass
class ValidationReport:
    device: str = ""
    n_rows: int = 0
    n_columns: int = 0
    first_timestamp: object = None
    last_timestamp: object = None
    span_days: float = 0.0
    median_interval_min: float | None = None
    n_duplicate_timestamps: int = 0
    n_unparseable_timestamps: int = 0
    n_idle_rows: int = 0                 # present, but the logger was idle
    idle_share: float = 0.0
    expected_samples: int = 0
    actual_samples: int = 0
    overall_coverage: float = 0.0
    gaps: list = field(default_factory=list)          # (start, end, hours)
    hour_coverage: dict = field(default_factory=dict)  # hour -> 0..1
    day_coverage: dict = field(default_factory=dict)   # date -> 0..1
    window_coverage: dict = field(default_factory=dict)  # label -> 0..1
    non_numeric: dict = field(default_factory=dict)    # column -> count
    null_counts: dict = field(default_factory=dict)    # column -> count
    implausible: dict = field(default_factory=dict)    # description -> count
    issues: list = field(default_factory=list)

    # -- convenience ------------------------------------------------------
    @property
    def errors(self):
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self):
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def can_proceed(self) -> bool:
        return not self.errors

    @property
    def unmeasured_windows(self) -> list:
        """Tariff windows too sparsely covered to report a number for."""
        return [w for w, c in self.window_coverage.items()
                if c < cfg.MIN_WINDOW_COVERAGE]

    def add(self, severity, title, detail=""):
        self.issues.append(Issue(severity, title, detail))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _timestamps(df: pd.DataFrame, device: str) -> pd.Series:
    """Parse the timestamp column without touching anything else.

    Unparseable values become NaT and are counted; they are never dropped
    here, because the count is the finding.
    """
    if device == "shelly":
        raw = pd.to_numeric(df["timestamp"], errors="coerce")
        return pd.to_datetime(raw, unit="s", errors="coerce")
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
                "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S"):
        parsed = pd.to_datetime(df["Time"], format=fmt, errors="coerce")
        if parsed.notna().any():
            return parsed
    return pd.to_datetime(df["Time"], dayfirst=True, errors="coerce")


def _measurement_columns(device: str) -> list:
    """Required columns that hold numbers (i.e. all but the timestamp)."""
    skip = {"timestamp", "Time"}
    return [c for c in fd.REQUIRED_COLUMNS[device] if c not in skip]


# ---------------------------------------------------------------------------
# the checks
# ---------------------------------------------------------------------------

def validate(df: pd.DataFrame, device: str,
             rate_min: int | None = None) -> ValidationReport:
    """Inspect a measurement dataframe. Returns findings; changes nothing.

    Coverage is measured over the rows where the logger was actually
    measuring, not over the rows that exist. The two are the same for a meter
    that stops writing when it goes offline, and very different for one that
    keeps writing zeros -- which is the case that would otherwise pass
    validation while most of the period held no measurement at all.
    """
    rep = ValidationReport(device=device, n_rows=len(df),
                           n_columns=df.shape[1])

    if len(df) == 0:
        rep.add("error", "The file has no data rows",
                "Only a header was found.")
        return rep

    # --- required columns ------------------------------------------------
    missing = fd.missing_columns(df.columns, device)
    if missing:
        rep.add("error",
                "%d required column%s missing" % (len(missing),
                                                  "" if len(missing) == 1 else "s"),
                "The analysis needs: " + ", ".join(missing))
        # without a timestamp column nothing else can be checked
        ts_col = "timestamp" if device == "shelly" else "Time"
        if ts_col in missing:
            return rep

    # --- timestamps -------------------------------------------------------
    ts = _timestamps(df, device)
    rep.n_unparseable_timestamps = int(ts.isna().sum())
    if rep.n_unparseable_timestamps:
        share = rep.n_unparseable_timestamps / len(df)
        rep.add("error" if share > 0.5 else "warning",
                "%d timestamp%s could not be read"
                % (rep.n_unparseable_timestamps,
                   "" if rep.n_unparseable_timestamps == 1 else "s"),
                "%.1f%% of rows. They are kept in the file but cannot be "
                "placed on a time axis." % (100 * share))

    # --- rows that exist but hold no measurement ------------------------
    try:
        from . import adapters
        adapter = adapters.get(device)
        measuring = adapter.measuring_mask(df).reindex(df.index, fill_value=True)
        rep.implausible = adapter.implausible_values(df)
    except Exception:                                     # noqa: BLE001
        measuring = pd.Series(True, index=df.index)

    rep.n_idle_rows = int((~measuring).sum())
    rep.idle_share = rep.n_idle_rows / len(df) if len(df) else 0.0
    if rep.n_idle_rows:
        rep.add("warning",
                "%d of %d rows hold no measurement"
                % (rep.n_idle_rows, len(df)),
                "%.0f%% of the file. %s These rows carry real timestamps, so "
                "the file looks complete, but every value in them is zero. "
                "They stay in the data and the analysis treats them exactly "
                "as it always has; coverage below is measured over the "
                "%d rows that do hold readings."
                % (100 * rep.idle_share, adapter.describe_idle(),
                   int(measuring.sum())))

    # from here on, coverage means coverage by actual measurements
    ts = ts.where(measuring)

    good = ts.dropna()
    if good.empty:
        rep.add("error", "No usable measurements",
                "Either every timestamp failed to parse, or no row in the "
                "file holds a reading.")
        return rep

    rep.first_timestamp = good.min()
    rep.last_timestamp = good.max()
    span = rep.last_timestamp - rep.first_timestamp
    rep.span_days = span.total_seconds() / 86400.0

    rep.n_duplicate_timestamps = int(good.duplicated().sum())
    if rep.n_duplicate_timestamps:
        rep.add("warning",
                "%d duplicate timestamp%s"
                % (rep.n_duplicate_timestamps,
                   "" if rep.n_duplicate_timestamps == 1 else "s"),
                "Resampling averages rows that share a timestamp, so these "
                "are combined rather than lost.")

    if not good.is_monotonic_increasing:
        rep.add("warning", "Rows are not in time order",
                "Resampling sorts them, so results are unaffected, but the "
                "export may have been assembled from several files.")

    # --- sample interval and coverage ------------------------------------
    deltas = good.sort_values().diff().dropna().dt.total_seconds() / 60.0
    if len(deltas):
        rep.median_interval_min = float(deltas.median())
    step = float(rate_min or rep.median_interval_min or 1)
    if step <= 0:
        step = 1.0

    rep.actual_samples = int(len(good))
    rep.expected_samples = int(round(span.total_seconds() / 60.0 / step)) + 1
    rep.overall_coverage = (rep.actual_samples / rep.expected_samples
                            if rep.expected_samples else 0.0)

    gap_threshold = step * 2
    for t_prev, d in zip(good.sort_values()[:-1], deltas):
        if d > gap_threshold:
            rep.gaps.append((t_prev, t_prev + pd.Timedelta(minutes=d),
                             d / 60.0))
    rep.gaps.sort(key=lambda g: g[2], reverse=True)

    # per hour of day, per calendar day, per tariff window
    frame = pd.DataFrame({"t": good})
    frame["hour"] = frame["t"].dt.hour
    frame["date"] = frame["t"].dt.date
    n_days = max(frame["date"].nunique(), 1)
    per_hour_max = 60.0 / step
    counts = frame.groupby("hour").size()
    rep.hour_coverage = {h: float(min(counts.get(h, 0)
                                      / (per_hour_max * n_days), 1.0))
                         for h in range(24)}
    per_day_max = 1440.0 / step
    rep.day_coverage = {d: float(min(n / per_day_max, 1.0))
                        for d, n in frame.groupby("date").size().items()}

    for label, h0, h1 in cfg.TARIFF_WINDOWS:
        hours = list(range(h0, h1))
        rep.window_coverage[label] = (
            float(np.mean([rep.hour_coverage[h] for h in hours]))
            if hours else 0.0)

    if rep.overall_coverage < cfg.MIN_OVERALL_COVERAGE:
        rep.add("warning",
                "Only %.0f%% of the measurement period was recorded"
                % (100 * rep.overall_coverage),
                "%d measurements over an expected %d intervals, in %d "
                "stretch%s totalling %.0f hours with nothing recorded. "
                "Energy figures are averages over the data that exists, not "
                "over the whole period."
                % (rep.actual_samples, rep.expected_samples, len(rep.gaps),
                   "" if len(rep.gaps) == 1 else "es",
                   sum(g[2] for g in rep.gaps)))

    for label in rep.unmeasured_windows:
        rep.add("warning",
                "The %s window has almost no data" % label,
                "%.0f%% of its hours were measured. The original code "
                "reports such a window as 0 kWh, which reads as a measured "
                "zero. It is shown as “not measured” instead."
                % (100 * rep.window_coverage[label]))

    empty_days = [str(d) for d, c in rep.day_coverage.items() if c == 0]
    if empty_days:
        rep.add("info", "%d day%s with no data" % (len(empty_days),
                                                   "" if len(empty_days) == 1
                                                   else "s"),
                ", ".join(empty_days[:10]))

    # --- values ----------------------------------------------------------
    for col in _measurement_columns(device):
        if col not in df.columns:
            continue
        raw = df[col]
        num = pd.to_numeric(raw, errors="coerce")
        bad = int((num.isna() & raw.notna()).sum())
        if bad:
            rep.non_numeric[col] = bad
        nulls = int(raw.isna().sum())
        if nulls:
            rep.null_counts[col] = nulls

    if rep.non_numeric:
        worst = sorted(rep.non_numeric.items(), key=lambda kv: -kv[1])[:5]
        rep.add("warning",
                "Non-numeric values in %d measurement column%s"
                % (len(rep.non_numeric),
                   "" if len(rep.non_numeric) == 1 else "s"),
                "; ".join("%s: %d" % (c, n) for c, n in worst)
                + ". These become blanks when the data is resampled.")

    if rep.null_counts:
        worst = sorted(rep.null_counts.items(), key=lambda kv: -kv[1])[:5]
        rep.add("info",
                "Blank values in %d column%s" % (len(rep.null_counts),
                                                 "" if len(rep.null_counts) == 1
                                                 else "s"),
                "; ".join("%s: %d" % (c, n) for c, n in worst))

    if rep.implausible:
        rep.add("warning",
                "Physically implausible readings in %d place%s"
                % (len(rep.implausible),
                   "" if len(rep.implausible) == 1 else "s"),
                "; ".join("%s: %d row%s" % (k, n, "" if n == 1 else "s")
                          for k, n in sorted(rep.implausible.items()))
                + ". Left in the data unchanged; they are excluded from the "
                  "suggested axis ranges so they cannot flatten a chart.")

    if rep.span_days < 1:
        rep.add("warning", "Less than a full day of measurements",
                "A daily average profile needs at least one complete day to "
                "be meaningful, and a PV simulation built on it will not be "
                "representative.")
    elif rep.span_days < 7:
        rep.add("info", "Measurement period is %.1f days" % rep.span_days,
                "A full week captures the weekday and weekend pattern.")

    return rep


def coverage_frame(rep: ValidationReport) -> pd.DataFrame:
    """Hour-of-day coverage as a table, for the app and the report."""
    return pd.DataFrame({
        "Hour": ["%02d:00" % h for h in range(24)],
        "Coverage %": [round(100 * rep.hour_coverage.get(h, 0.0), 1)
                       for h in range(24)],
    })


def day_frame(rep: ValidationReport) -> pd.DataFrame:
    """Per-day coverage as a table."""
    items = sorted(rep.day_coverage.items())
    return pd.DataFrame({
        "Date": [str(d) for d, _ in items],
        "Coverage %": [round(100 * c, 1) for _, c in items],
    })
