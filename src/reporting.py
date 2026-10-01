"""
Turn an analysis into things a person can keep: a ZIP of the figures, a
spreadsheet of the summary tables, and a PDF report.

None of these recompute anything. They format what analysis.run produced.
"""

from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from . import config as cfg


# ---------------------------------------------------------------------------
# ZIP
# ---------------------------------------------------------------------------

def build_zip(result) -> bytes:
    """Every figure and data file from one run, in a single archive."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in result.figures + result.data_files:
            zf.write(path, os.path.basename(path))
        zf.writestr("analysis_settings.txt", _settings_text(result))
    return buffer.getvalue()


def _settings_text(result) -> str:
    """The audit trail: what produced these figures."""
    c = result.config
    lines = [
        "EQS Measurement Analyser",
        "Generated %s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
        "",
        "Customer:        %s" % c.customer,
        "Location:        %s" % (c.location or "-"),
        "Project ref:     %s" % (c.project_reference or "-"),
        "Device:          %s" % result.device,
        "",
        "Sample rate:     %s min" % c.RateMin,
        "Time offset:     %s h" % c.deltatime,
        "Power unit:      %s" % ("kW" if c.Yformat == 1 else "W"),
        "PV sizes:        %s kWp" % ", ".join(str(s) for s in c.PPV),
        "EtaPV:           %s" % c.EtaPV,
        "Offset:          %s" % c.Offset,
        "",
        "Corrections applied to the original notebook code:",
        "  Econ graph 4.1 L3/L2 power-factor typo: %s"
        % ("left as in the notebook" if cfg.PRESERVE_LEGACY_PF_TYPO
           else "corrected"),
        "  Shelly Wh-to-W conversion: %s"
        % ("literal x60" if cfg.PRESERVE_LEGACY_X60 else "60 / RateMin"),
    ]
    if result.validation is not None:
        v = result.validation
        lines += [
            "",
            "Measurement period: %s to %s" % (v.first_timestamp,
                                              v.last_timestamp),
            "Period recorded:    %.1f%%" % (100 * v.overall_coverage),
        ]
        if v.unmeasured_windows:
            lines.append("Windows not measured: %s"
                         % ", ".join(v.unmeasured_windows))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Spreadsheet
# ---------------------------------------------------------------------------

def build_xlsx(result) -> bytes:
    """Summary tables, validation findings and settings, one sheet each."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        _sheet(writer, "Energy summary", result.energy_summary_annotated
               if result.energy_summary_annotated is not None
               else result.energy_summary)
        _sheet(writer, "PV yield", result.pv_yield)
        _sheet(writer, "PV detail", result.pv_detail)

        if result.sizing is not None:
            _sheet(writer, "Size assessment", result.sizing.table, index=False)
            rows = [{"Kind": "Measured", "Item": k, "Value": v}
                    for k, v in result.sizing.measured_inputs.items()]
            rows += [{"Kind": "User assumption", "Item": k, "Value": v}
                     for k, v in result.sizing.user_assumptions.items()]
            rows += [{"Kind": "Caveat", "Item": "", "Value": c}
                     for c in result.sizing.caveats]
            _sheet(writer, "Basis and caveats", pd.DataFrame(rows), index=False)

        if result.validation is not None:
            v = result.validation
            _sheet(writer, "Validation", pd.DataFrame(
                [{"Severity": i.severity, "Finding": i.title,
                  "Detail": i.detail} for i in v.issues]), index=False)
            _sheet(writer, "Coverage by hour", pd.DataFrame({
                "Hour": ["%02d:00" % h for h in range(24)],
                "Coverage %": [round(100 * v.hour_coverage.get(h, 0), 1)
                               for h in range(24)]}), index=False)

        _sheet(writer, "Settings", pd.DataFrame(
            {"Line": _settings_text(result).splitlines()}), index=False)
    return buffer.getvalue()


def _sheet(writer, name, frame, index=True):
    if frame is None:
        frame = pd.DataFrame({"": ["not produced"]})
        index = False
    if isinstance(frame, pd.Series):
        frame = frame.to_frame()
    frame.to_excel(writer, sheet_name=name[:31], index=index)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def build_pdf(result, max_figures: int | None = None) -> bytes:
    """A report: cover, basis, caveats, then every figure in order.

    Built with matplotlib's own PDF backend, so it adds no dependency and
    touches none of the calculations -- the figures are the PNGs already
    written to disk, placed on pages.
    """
    buffer = io.BytesIO()
    figures = result.figures[:max_figures] if max_figures else result.figures

    with PdfPages(buffer) as pdf:
        _pdf_cover(pdf, result)
        _pdf_tables(pdf, result)
        for path in figures:
            _pdf_image(pdf, path)
    return buffer.getvalue()


def _new_page(size=(8.27, 11.69)):        # A4 portrait
    fig = plt.figure(figsize=size, facecolor="white")
    fig.subplots_adjust(left=0.08, right=0.92, top=0.92, bottom=0.08)
    return fig


def _pdf_cover(pdf, result):
    c = result.config
    fig = _new_page()
    y = 0.94

    fig.text(0.08, y, "Electricity measurement analysis",
             fontsize=20, weight="bold", va="top")
    y -= 0.05
    fig.text(0.08, y, c.customer, fontsize=15, va="top")
    y -= 0.045
    subtitle = " | ".join(x for x in (c.location, c.project_reference) if x)
    if subtitle:
        fig.text(0.08, y, subtitle, fontsize=10, color="0.35", va="top")
        y -= 0.03
    fig.text(0.08, y, "Generated %s" % datetime.now().strftime("%d %B %Y"),
             fontsize=9, color="0.45", va="top")
    y -= 0.05

    v = result.validation
    if v is not None:
        block = [
            "Device: %s" % result.device,
            "Measurement period: %s to %s" % (
                str(v.first_timestamp)[:16], str(v.last_timestamp)[:16]),
            "Span: %.1f days, of which %.0f%% was actually recorded"
            % (v.span_days, 100 * v.overall_coverage),
            "Samples: %d of an expected %d" % (v.actual_samples,
                                               v.expected_samples),
        ]
        for line in block:
            fig.text(0.08, y, line, fontsize=10, va="top")
            y -= 0.025
        y -= 0.015

        if v.unmeasured_windows:
            fig.text(0.08, y, "Windows with too little data to report",
                     fontsize=11, weight="bold", va="top", color="#8a5312")
            y -= 0.028
            for w in v.unmeasured_windows:
                fig.text(0.10, y, "%s -- %.0f%% of its hours measured"
                         % (w, 100 * v.window_coverage[w]),
                         fontsize=9.5, va="top", color="#8a5312")
                y -= 0.022
            y -= 0.015

    s = result.sizing
    if s is not None:
        fig.text(0.08, y, "Preliminary size guidance", fontsize=13,
                 weight="bold", va="top")
        y -= 0.032
        from . import sizing as _sz
        for line in _wrap(_sz.headline(s), 92):
            fig.text(0.08, y, line, fontsize=10, va="top")
            y -= 0.022
        y -= 0.012
        fig.text(0.08, y, "Requires engineering review. Not an approved "
                          "system size.", fontsize=9.5, style="italic",
                 color="#8a5312", va="top")
        y -= 0.035

        for heading, items in (("From the measurements", s.measured_inputs),
                               ("Assumptions entered", s.user_assumptions)):
            fig.text(0.08, y, heading, fontsize=10.5, weight="bold", va="top")
            y -= 0.026
            for k, val in items.items():
                fig.text(0.10, y, "%s: %s" % (k, val), fontsize=9, va="top")
                y -= 0.02
            y -= 0.012

    pdf.savefig(fig)
    plt.close(fig)

    # caveats get their own page; there are usually several
    if s is not None and s.caveats:
        fig = _new_page()
        y = 0.94
        fig.text(0.08, y, "Caveats", fontsize=16, weight="bold", va="top")
        y -= 0.05
        for i, caveat in enumerate(s.caveats, 1):
            for j, line in enumerate(_wrap(caveat, 88)):
                prefix = "%d. " % i if j == 0 else "   "
                fig.text(0.08, y, prefix + line, fontsize=9.5, va="top")
                y -= 0.021
            y -= 0.012
            if y < 0.08:
                pdf.savefig(fig)
                plt.close(fig)
                fig = _new_page()
                y = 0.94
        pdf.savefig(fig)
        plt.close(fig)


def _pdf_tables(pdf, result):
    tables = [
        ("Electricity consumption", result.energy_summary_annotated
         if result.energy_summary_annotated is not None
         else result.energy_summary, True),
        ("Maximum PV yield", result.pv_yield, True),
        ("Direct PV consumption and share", result.pv_detail, True),
        ("Candidate size assessment",
         result.sizing.table if result.sizing else None, False),
    ]
    fig = _new_page()
    y = 0.94
    fig.text(0.08, y, "Summary tables", fontsize=16, weight="bold", va="top")
    y -= 0.055

    for title, frame, with_index in tables:
        if frame is None or (hasattr(frame, "empty") and frame.empty):
            continue
        if y < 0.25:
            pdf.savefig(fig)
            plt.close(fig)
            fig = _new_page()
            y = 0.94
        fig.text(0.08, y, title, fontsize=11, weight="bold", va="top")
        y -= 0.03
        height = _table(fig, frame, y, with_index)
        y -= height + 0.04

    pdf.savefig(fig)
    plt.close(fig)


def _table(fig, frame, top, with_index):
    """Draw a dataframe as a matplotlib table. Returns the height used."""
    data = frame.reset_index() if with_index else frame
    cells = [[_fmt(v) for v in row] for row in data.values]
    cols = [str(c) for c in data.columns]
    n_rows = len(cells) + 1
    height = min(0.028 * n_rows, 0.32)

    ax = fig.add_axes([0.08, top - height, 0.84, height])
    ax.axis("off")
    tbl = ax.table(cellText=cells, colLabels=cols, loc="upper center",
                   cellLoc="right", colLoc="right")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7.5)
    tbl.scale(1, 1.25)
    for (r, _), cell in tbl.get_celld().items():
        cell.set_linewidth(0.3)
        cell.set_edgecolor("0.75")
        if r == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#eef2f1")
    return height


def _fmt(value):
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return "{:,.0f}".format(value) if abs(value) >= 1000 else "%.1f" % value
    if isinstance(value, int):
        return "{:,}".format(value)
    return str(value)


def _pdf_image(pdf, path):
    img = plt.imread(path)
    h, w = img.shape[0], img.shape[1]
    landscape = w >= h
    size = (11.69, 8.27) if landscape else (8.27, 11.69)
    fig = plt.figure(figsize=size, facecolor="white")
    ax = fig.add_axes([0.04, 0.06, 0.92, 0.88])
    ax.imshow(img)
    ax.axis("off")
    fig.text(0.04, 0.025, os.path.basename(path), fontsize=7, color="0.45")
    pdf.savefig(fig)
    plt.close(fig)


def _wrap(text, width):
    words, lines, line = str(text).split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        lines.append(line)
    return lines or [""]
