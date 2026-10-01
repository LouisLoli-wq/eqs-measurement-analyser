"""
Work out what an uploaded file is before trying to analyse it.

Three questions, answered independently so a failure in one is still
informative: what encoding is it, what separates the fields, and which logger
produced it. Nothing here modifies the file or the parsed values.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field

import pandas as pd

#: Tried in order. utf-8-sig first so a BOM is consumed rather than glued to
#: the first column name; cp1252 is what Windows means by "ansi".
ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")

#: Columns that identify a device beyond reasonable doubt.
ECON_SIGNATURE = ("Time", "Pactive total avg [kW]", "L1 Urms avg [V]")
SHELLY_SIGNATURE = ("timestamp", "a_total_act_energy", "a_avg_voltage")

#: Everything the analysis actually reads, per device.
ECON_REQUIRED = (
    "Time",
    "Frequency [Hz]",
    "Pactive total avg [kW]",
    "Qreactive total avg [kvar]",
) + tuple(
    "%s %s" % (ln, col)
    for ln in ("L1", "L2", "L3")
    for col in ("Urms avg [V]", "Urms max [V]", "Irms avg [A]",
                "Irms max [A]", "Pactive avg [kW]", "U THD avg [%]",
                "PF avg [-]")
)

SHELLY_REQUIRED = ("timestamp",) + tuple(
    "%s_%s" % (ph, col)
    for ph in ("a", "b", "c")
    for col in ("avg_voltage", "avg_current", "max_current",
                "total_act_energy", "max_act_power", "max_aprt_power")
)

REQUIRED_COLUMNS = {"econ": ECON_REQUIRED, "shelly": SHELLY_REQUIRED}


#: Workbooks arrive when someone opens a logger export in Excel and saves it.
#: Excel does not split a semicolon-delimited file into columns, so the whole
#: row lands in one cell and the sheet has a single column. Both shapes are
#: handled; see xlsx_to_csv_bytes.
XLSX_MAGIC = b"PK\x03\x04"


@dataclass
class FileProfile:
    """What we could work out about a file without interpreting its numbers."""

    name: str = ""
    size_bytes: int = 0
    from_workbook: bool = False
    encoding: str | None = None
    delimiter: str | None = None
    columns: list = field(default_factory=list)
    n_data_rows: int | None = None
    device: str | None = None            # "econ" | "shelly" | None
    device_confidence: str = "none"      # "certain" | "likely" | "none"
    device_reason: str = ""
    readable: bool = True
    error: str = ""
    workbook_note: str = ""

    @property
    def ok(self) -> bool:
        return self.readable and not self.error


def looks_like_workbook(data: bytes, name: str = "") -> bool:
    """An .xlsx is a zip whose first bytes are the zip magic number."""
    return data[:4] == XLSX_MAGIC or name.lower().endswith((".xlsx", ".xlsm"))


def xlsx_to_csv_bytes(data: bytes) -> tuple[bytes, str]:
    """Flatten a workbook back into delimited text.

    Two shapes turn up:

      * one column per field, because the file was pasted or imported
        properly. Written back out with ';'.
      * a single column holding whole delimited rows, because Excel opened a
        semicolon-separated export on a machine whose list separator is a
        comma and never split it. The cell contents are already the CSV, so
        they are simply joined back together.

    Returns (csv bytes, note) where the note describes what was done, for the
    validation page. Nothing is parsed or coerced here.
    """
    frame = pd.read_excel(io.BytesIO(data), sheet_name=0, header=None,
                          dtype=str)
    frame = frame.dropna(how="all")
    if frame.empty:
        raise ValueError("the first sheet of that workbook is empty")

    if frame.shape[1] == 1:
        lines = [str(v) for v in frame.iloc[:, 0].tolist() if str(v) != "nan"]
        text = "\n".join(lines)
        note = ("the workbook held one column of whole delimited rows, so it "
                "was read back as the text file it started as")
    else:
        text = frame.to_csv(index=False, header=False, sep=";")
        note = ("the workbook's %d columns were written back out as "
                "semicolon-separated text" % frame.shape[1])
    return (text + "\n").encode("utf-8"), note


def detect_encoding(raw: bytes) -> tuple[str | None, str]:
    """First encoding that decodes the sample cleanly, and the decoded text."""
    for enc in ENCODINGS:
        try:
            return enc, raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None, ""


def detect_delimiter(text: str) -> str | None:
    """Sniff the field separator from the header and first rows.

    csv.Sniffer first; if it cannot decide, fall back to whichever candidate
    appears most consistently across the first few lines, which is what
    actually distinguishes an Econ export (';') from a Shelly one (',').
    """
    sample = "\n".join(text.splitlines()[:20])
    if not sample.strip():
        return None
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        pass
    lines = [ln for ln in text.splitlines()[:10] if ln.strip()]
    best, best_score = None, 0
    for cand in (";", ",", "\t", "|"):
        counts = [ln.count(cand) for ln in lines]
        if not counts or min(counts) == 0:
            continue
        # consistent count across lines is the signal, not raw frequency
        score = min(counts) * (1 if len(set(counts)) == 1 else 0.5)
        if score > best_score:
            best, best_score = cand, score
    return best


def identify_device(columns) -> tuple[str | None, str, str]:
    """Which logger produced a file with these columns.

    Returns (device, confidence, reason). Confidence is "certain" when the
    signature columns are all present and the other device's are not.
    """
    cols = {str(c).strip() for c in columns}
    econ_hits = [c for c in ECON_SIGNATURE if c in cols]
    shelly_hits = [c for c in SHELLY_SIGNATURE if c in cols]

    if len(econ_hits) == len(ECON_SIGNATURE) and not shelly_hits:
        return "econ", "certain", "all Econ signature columns present"
    if len(shelly_hits) == len(SHELLY_SIGNATURE) and not econ_hits:
        return "shelly", "certain", "all Shelly signature columns present"

    if econ_hits and not shelly_hits:
        return "econ", "likely", "Econ columns found: %s" % ", ".join(econ_hits)
    if shelly_hits and not econ_hits:
        return "shelly", "likely", ("Shelly columns found: %s"
                                    % ", ".join(shelly_hits))
    if econ_hits and shelly_hits:
        return None, "none", ("columns from both formats present "
                              "(Econ: %s; Shelly: %s)"
                              % (", ".join(econ_hits), ", ".join(shelly_hits)))
    return None, "none", "no recognised Econ or Shelly columns"


def profile_file(data: bytes, name: str = "") -> FileProfile:
    """Everything detect-able about an uploaded file, without judging it.

    A workbook is flattened to text first; use `prepared_bytes` to get what
    was actually profiled, since that is what the rest of the pipeline must
    read.
    """
    prof = FileProfile(name=name, size_bytes=len(data))

    if not data or not data.strip():
        prof.readable = False
        prof.error = "The file is empty."
        return prof

    if looks_like_workbook(data, name):
        try:
            data, note = xlsx_to_csv_bytes(data)
        except zipfile.BadZipFile:
            prof.readable = False
            prof.error = ("That looks like a workbook but could not be "
                          "opened. Export the measurement again from the "
                          "logger, as a CSV.")
            return prof
        except Exception as exc:                          # noqa: BLE001
            prof.readable = False
            prof.error = "Could not read that workbook: %s" % exc
            return prof
        prof.from_workbook = True
        prof.workbook_note = note

    enc, text = detect_encoding(data[:200_000])
    if enc is None:
        prof.readable = False
        prof.error = ("Could not decode the file as text. It may be a "
                      "spreadsheet or an archive rather than a CSV.")
        return prof
    prof.encoding = enc

    delim = detect_delimiter(text)
    if delim is None:
        prof.readable = False
        prof.error = ("Could not find a field separator. A CSV needs commas "
                      "or semicolons between values.")
        return prof
    prof.delimiter = delim

    try:
        head = pd.read_csv(io.BytesIO(data), sep=delim, encoding=enc,
                           engine="python", nrows=5)
    except Exception as exc:                              # noqa: BLE001
        prof.readable = False
        prof.error = "Could not parse the file as CSV: %s" % exc
        return prof

    if head.shape[1] < 2:
        prof.readable = False
        prof.error = ("Only one column was found using '%s' as the separator. "
                      "The file may use a different separator." % delim)
        return prof

    prof.columns = [str(c).strip() for c in head.columns]
    prof.device, prof.device_confidence, prof.device_reason = identify_device(
        prof.columns)
    # counting rows is cheap next to reading them and is worth reporting early
    prof.n_data_rows = max(text.count("\n") - 1, 0) if len(data) < 200_000 \
        else None
    return prof


def prepared_bytes(data: bytes, name: str = "") -> bytes:
    """The delimited text the rest of the pipeline should read.

    Identical to the upload for a CSV; the flattened sheet for a workbook.
    """
    if looks_like_workbook(data, name):
        return xlsx_to_csv_bytes(data)[0]
    return data


def missing_columns(columns, device: str) -> list:
    """Required columns for a device that the file does not have."""
    have = {str(c).strip() for c in columns}
    return [c for c in REQUIRED_COLUMNS[device] if c not in have]


def read_full(data: bytes, delimiter: str, encoding: str) -> pd.DataFrame:
    """Read a whole uploaded file with settings already established.

    Deliberately does no cleaning: no dropping, no coercion, no filling. The
    validator inspects what is actually there and reports it.
    """
    df = pd.read_csv(io.BytesIO(data), sep=delimiter, encoding=encoding,
                     engine="python")
    df.columns = [str(c).strip() for c in df.columns]
    return df
