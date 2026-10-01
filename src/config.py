"""
Configuration for the EQS Measurement Analyser.

Everything a user can set lives in AnalysisConfig. Everything the business has
decided lives in the module-level constants below. Nothing in here is read
from the environment or from a file the user cannot see.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# ---------------------------------------------------------------------------
# Business constants -- change these deliberately, not per analysis
# ---------------------------------------------------------------------------

#: Tariff windows used by summary_energy in the original notebooks, as
#: (label, start hour, end hour). Kept exactly as the notebooks had them.
TARIFF_WINDOWS = (
    ("Off-Peak", 0, 6),
    ("Shoulder", 6, 18),
    ("Peak", 18, 24),
)

#: A tariff window with less than this share of its minutes actually measured
#: is reported as "not measured" rather than as a number. The original code
#: reported 0 kWh for a window with no data at all, which reads as a real
#: measurement of nothing rather than as an absence of measurement.
MIN_WINDOW_COVERAGE = 0.50

#: Below this overall coverage the validation page raises a blocking-grade
#: warning. The analysis still runs; the user has to acknowledge it.
MIN_OVERALL_COVERAGE = 0.80

#: Days in a month and days in a year, as used by summary_energy.
DAYS_PER_MONTH = 30
DAYS_PER_YEAR = 365

#: Upload ceiling, mirrored in .streamlit/config.toml.
MAX_UPLOAD_MB = 200

#: Corrections to the original notebook code. See TECHNICAL_NOTES.md.
#: True reproduces the original behaviour, defect and all.
PRESERVE_LEGACY_PF_TYPO = False      # Econ graph 4.1: L3 divided by L2's PF
PRESERVE_LEGACY_X60 = False          # Shelly: bare x60 instead of 60/RateMin


# ---------------------------------------------------------------------------
# Per-analysis configuration
# ---------------------------------------------------------------------------

@dataclass
class AnalysisConfig:
    """Everything the user sets for one analysis run.

    Field names match the original notebooks' "Manual Input" cell wherever a
    corresponding variable existed, so the two can be read side by side.
    """

    # --- identification -----------------------------------------------------
    device: str = "econ"                  # "econ" | "shelly"
    customer: str = "Customer"            # titles and filenames
    location: str = ""                    # report metadata only
    project_reference: str = ""           # report metadata only
    notes: str = ""                       # report metadata only

    # --- measurement handling ----------------------------------------------
    RateMin: int = 1                      # sample interval, minutes
    deltatime: int = 0                    # clock offset correction, hours
    Yformat: float = 1.0                  # 1 -> kW, 1e-3 -> W
    date_from: Any = None                 # optional inclusive start (date)
    date_to: Any = None                   # optional inclusive end (date)

    # --- PV simulation ------------------------------------------------------
    PPV: list = field(default_factory=lambda: [150, 200, 250, 300])
    EtaPV: float = 0.80
    Offset: float = 0.0

    # --- axes ---------------------------------------------------------------
    Ymin: float = 0
    Ymax: float = 500
    Ydist: float = 50
    Amax: float = 50000                   # Shelly apparent-power axis
    Adist: float = 5000
    Umin: float = 150
    Umax: float = 300
    Udist: float = 20
    Imin: float = -5
    Imax: float = 100
    Idist: float = 10
    THDmin: float = 0
    THDmax: float = 40
    THDdist: float = 8
    PFmin: float = 0.0
    PFmax: float = 1.1
    PFdist: float = 0.1
    Fmin: float = 40
    Fmax: float = 60
    Fdist: float = 2

    def to_dict(self) -> dict:
        return asdict(self)

    def plot_settings(self) -> dict:
        """The subset the generated plot modules accept, per device.

        Each module validates its own keys, so anything the device does not
        have (THD limits on Shelly, the apparent-power axis on Econ) is
        filtered out here rather than raising.
        """
        common = dict(
            customer=self.customer,
            Ymin=self.Ymin, Ymax=self.Ymax, Ydist=self.Ydist,
            Umin=self.Umin, Umax=self.Umax, Udist=self.Udist,
            Imin=self.Imin, Imax=self.Imax, Idist=self.Idist,
            PFmin=self.PFmin, PFmax=self.PFmax, PFdist=self.PFdist,
            Yformat=self.Yformat, RateMin=int(self.RateMin),
            deltatime=int(self.deltatime),
            PPV=list(self.PPV), EtaPV=float(self.EtaPV),
            Offset=float(self.Offset),
        )
        if self.device == "econ":
            common.update(
                THDmin=self.THDmin, THDmax=self.THDmax, THDdist=self.THDdist,
                Fmin=self.Fmin, Fmax=self.Fmax, Fdist=self.Fdist,
            )
        else:
            common.update(Amax=self.Amax, Adist=self.Adist)
        return common


#: Sensible starting axes per device, used before a file has been read.
DEVICE_DEFAULTS = {
    "econ": dict(Yformat=1.0, Ymax=500, Ydist=50, Imax=100, Idist=10,
                 PPV=[150, 200, 250, 300]),
    "shelly": dict(Yformat=1e-3, Ymax=10000, Ydist=1000, Imax=50, Idist=10,
                   PPV=[10, 15, 18, 20]),
}
