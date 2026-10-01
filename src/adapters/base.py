"""
Device adapters.

An adapter is the only place that knows how one logger's files are shaped.
Everything downstream -- validation, analysis, sizing, reporting, the app --
talks to this interface and never to a column name.

Adding a third logger means adding a module here and registering it in
ADAPTERS at the bottom of __init__.py. Nothing else should need to change.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class DeviceAdapter(Protocol):
    """What every device module must provide."""

    #: "econ" | "shelly"
    NAME: str
    #: Shown in the interface
    LABEL: str
    #: Field separator the logger writes
    DELIMITER: str
    #: Columns the analysis reads
    REQUIRED_COLUMNS: tuple
    #: Figures this device produces, for the UI to promise honestly
    N_FIGURES: int
    #: Quantities this device does not measure at all
    NOT_MEASURED: tuple

    def plots_module(self):
        """The generated module holding this device's figure functions."""

    def suggest_limits(self, df: pd.DataFrame) -> dict:
        """Axis limits and sample rate read off a real file.

        Suggestions only. They are shown to the user, who can override every
        one of them before anything is plotted.
        """

    def describe_power(self) -> str:
        """One sentence on how total power is obtained, for the report."""

    def measuring_mask(self, df: pd.DataFrame) -> pd.Series:
        """True where a row holds a real measurement.

        Some loggers keep writing a row every interval while they are not
        actually measuring -- the Econ writes Code 256 with every value zero.
        Those rows are not gaps in the file, so counting timestamps says the
        period is fully covered when most of it is not. Coverage is computed
        from this mask instead.

        The rows are never removed. The analysis sees the file exactly as the
        notebook did; the mask only decides what gets reported.
        """

    def describe_idle(self) -> str:
        """One sentence on how this device marks a non-measuring row."""
