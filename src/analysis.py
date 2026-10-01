"""
Run an analysis end to end.

This module is the only thing that drives the generated plotting modules. It
prepares a private working folder, hands the plotting code its configuration,
runs the notebook's own steps in the notebook's own order, and collects what
comes back.

It adds nothing to the calculations. Where it qualifies a result -- a tariff
window with no measurements behind it -- it does so alongside the original
number, never in place of it.
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field

import pandas as pd

from . import adapters, config as cfg, file_detection as fd, sizing, validation


@dataclass
class AnalysisResult:
    device: str = ""
    config: object = None
    workdir: str = ""
    figures: list = field(default_factory=list)
    data_files: list = field(default_factory=list)
    energy_summary: pd.DataFrame | None = None            # exactly as computed
    energy_summary_annotated: pd.DataFrame | None = None  # unmeasured marked
    pv_yield: pd.DataFrame | None = None
    pv_detail: pd.DataFrame | None = None
    sizing: sizing.SizingResult | None = None
    validation: validation.ValidationReport | None = None
    plot_config: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    step_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


class Session:
    """A private working folder for one analysis, cleaned up on close.

    Each run gets its own directory so two people using a shared instance
    never see each other's files.
    """

    PREFIX = "eqs-analysis-"

    #: Folders older than this are swept up on the next app start, so a run
    #: that was abandoned halfway does not leave customer data on disk.
    STALE_AFTER_HOURS = 6

    def __init__(self, root: str | None = None):
        self.id = uuid.uuid4().hex[:12]
        base = root or tempfile.gettempdir()
        self.path = os.path.join(base, self.PREFIX + self.id)
        os.makedirs(self.path, exist_ok=True)
        self.outputs = os.path.join(self.path, "outputs")
        os.makedirs(self.outputs, exist_ok=True)

    @classmethod
    def sweep_stale(cls, root: str | None = None) -> int:
        """Delete working folders left behind by earlier sessions."""
        import time

        base = root or tempfile.gettempdir()
        cutoff = time.time() - cls.STALE_AFTER_HOURS * 3600
        removed = 0
        try:
            names = os.listdir(base)
        except OSError:
            return 0
        for name in names:
            if not name.startswith(cls.PREFIX):
                continue
            path = os.path.join(base, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
        return removed

    def write(self, name: str, data: bytes) -> str:
        safe = os.path.basename(name).replace(os.sep, "_") or "upload.csv"
        path = os.path.join(self.path, safe)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def close(self):
        shutil.rmtree(self.path, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False        # the caller decides when to clean up


# ---------------------------------------------------------------------------

def _filter_by_date(df: pd.DataFrame, device: str, date_from, date_to):
    """Restrict a dataframe to a date range, keeping the original columns.

    Rows outside the range are excluded from the analysis, not altered. The
    count removed is reported so the user can see what the range cost them.
    """
    if date_from is None and date_to is None:
        return df, 0

    ts_col = "timestamp" if device == "shelly" else "Time"
    if device == "shelly":
        ts = pd.to_datetime(pd.to_numeric(df[ts_col], errors="coerce"),
                            unit="s", errors="coerce")
    else:
        ts = pd.to_datetime(df[ts_col], dayfirst=True, errors="coerce")

    keep = pd.Series(True, index=df.index)
    if date_from is not None:
        keep &= ts.dt.date >= date_from
    if date_to is not None:
        keep &= ts.dt.date <= date_to
    return df[keep].copy(), int((~keep).sum())


def _annotate_energy_summary(dfEd: pd.DataFrame, report) -> pd.DataFrame:
    """Mark tariff windows with too little data behind them.

    summary_energy sums a daily average profile. Where a window has no
    measurements the sum is zero, which on the page reads as "we measured
    nothing being used" rather than "we did not measure". This replaces the
    number with a label and leaves every other cell untouched.
    """
    if dfEd is None or dfEd.empty or report is None:
        return dfEd
    out = dfEd.astype(object).copy()
    for window in report.unmeasured_windows:
        if window in out.columns:
            out[window] = "not measured"
    # If the period as a whole is too sparse, the total is no more meaningful
    # than the windows it is made of.
    if "Total" in out.columns and report.overall_coverage < cfg.MIN_WINDOW_COVERAGE:
        out["Total"] = "not measured"
    return out


def run(config, measurement_bytes: bytes, measurement_name: str,
        irradiation_bytes: bytes, irradiation_name: str,
        session: Session | None = None,
        progress=None, colours: dict | None = None) -> AnalysisResult:
    """Validate, then run every figure and summary the device supports."""
    device = config.device
    adapter = adapters.get(device)
    session = session or Session()
    result = AnalysisResult(device=device, config=config,
                            workdir=session.outputs)

    # --- read and validate, without changing anything --------------------
    profile = fd.profile_file(measurement_bytes, measurement_name)
    if not profile.ok:
        result.errors.append(("Reading the measurement file", profile.error))
        return result

    # a workbook upload is flattened back to delimited text; a CSV passes
    # through untouched
    measurement_bytes = fd.prepared_bytes(measurement_bytes, measurement_name)
    if profile.from_workbook:
        measurement_name = os.path.splitext(measurement_name)[0] + ".csv"

    df = fd.read_full(measurement_bytes, profile.delimiter, profile.encoding)
    df, n_excluded = _filter_by_date(df, device, config.date_from,
                                     config.date_to)
    if df.empty:
        result.errors.append(("Date range",
                              "No rows fall inside the selected dates."))
        return result

    report = validation.validate(df, device, rate_min=config.RateMin)
    result.validation = report
    if n_excluded:
        report.add("info", "%d rows outside the selected date range"
                   % n_excluded, "They are excluded from this analysis only; "
                                 "the uploaded file is unchanged.")
    if not report.can_proceed:
        result.errors.extend((i.title, i.detail) for i in report.errors)
        return result

    # --- stage the inputs the plotting code will read ---------------------
    # A date range means the plotting code must see the subset, so a filtered
    # copy is written to the session folder. Without one, the upload is staged
    # byte for byte.
    if n_excluded:
        measurement_path = os.path.join(session.path, "filtered_measurement.csv")
        df.to_csv(measurement_path, sep=profile.delimiter, index=False,
                  encoding="utf-8")
    else:
        measurement_path = session.write(measurement_name or "measurement.csv",
                                         measurement_bytes)
    irradiation_path = session.write(irradiation_name or "irradiation.csv",
                                     irradiation_bytes)

    # --- configure and run the notebook's own code ------------------------
    plots = adapter.plots_module()
    if device == "econ" and hasattr(plots, "set_legacy_pf_typo"):
        plots.set_legacy_pf_typo(cfg.PRESERVE_LEGACY_PF_TYPO)
    if device == "shelly" and hasattr(plots, "set_legacy_x60"):
        plots.set_legacy_x60(cfg.PRESERVE_LEGACY_X60)

    settings = config.plot_settings()
    settings.update(PathMeasurement=measurement_path,
                    PathRadiation=irradiation_path,
                    OUTDIR=session.outputs)
    if colours:
        # colour lists only; no figure, axis or calculation is touched
        settings.update({k: list(v) for k, v in colours.items()
                         if k in settings or k.startswith("color")})
    result.plot_config = plots.configure(**settings)

    result.step_count = len(plots.STEPS)
    run_out = plots.run_all(progress=progress)
    result.errors.extend(run_out["errors"])

    result.figures = [f for f in run_out["files"] if f.lower().endswith(".png")]
    result.data_files = [f for f in run_out["files"]
                         if not f.lower().endswith(".png")]

    # --- collect the summary tables the notebook builds -------------------
    result.energy_summary = getattr(plots, "dfEd", None)
    result.pv_yield = getattr(plots, "EPVmaxP", None)
    result.pv_detail = getattr(plots, "dfPVd", None)
    result.energy_summary_annotated = _annotate_energy_summary(
        result.energy_summary, report)

    # --- preliminary size guidance ---------------------------------------
    result.sizing = sizing.assess(result.pv_detail, config.PPV,
                                  validation=report,
                                  eta_pv=config.EtaPV, offset=config.Offset)
    return result


def suggest_settings(measurement_bytes: bytes, measurement_name: str,
                     device: str) -> tuple:
    """Axis limits and sample rate proposed from a file, plus its profile.

    Returns (profile, suggestions, dataframe). The dataframe is returned so
    the caller can validate without reading the file twice.
    """
    profile = fd.profile_file(measurement_bytes, measurement_name)
    if not profile.ok:
        return profile, {}, None
    prepared = fd.prepared_bytes(measurement_bytes, measurement_name)
    df = fd.read_full(prepared, profile.delimiter, profile.encoding)
    try:
        suggestions = adapters.get(device).suggest_limits(df)
    except Exception:                                      # noqa: BLE001
        suggestions = {}
    return profile, suggestions, df
