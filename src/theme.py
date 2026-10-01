"""
House style.

The look comes from the Equator Solar "Site Visit & Data Capture" form, so
the two tools read as one set. The palette and shapes live in
assets/theme.css; this module loads it and gives the matplotlib charts the
same colours when that is switched on.

Keeping it in one place means a brand change is one file, not a hunt through
the interface code.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Tokens, from the form's [data-theme="day"] / :root blocks
# ---------------------------------------------------------------------------

DAY = {
    "base": "#EFF3F0", "panel": "#FFFFFF", "panel2": "#F5F9F6",
    "line": "#D3DBD6", "ink": "#0E1A14", "mute": "#5C6B64",
    "accent": "#188B44", "accent_dark": "#0F6431",
    "warn": "#C96E1E", "danger": "#C2362F",
}

NIGHT = {
    "base": "#000000", "panel": "#080A09", "panel2": "#111513",
    "line": "#222C26", "ink": "#F1F5F2", "mute": "#93A099",
    "accent": "#2FBF6B", "accent_dark": "#188B44",
    "warn": "#F0903C", "danger": "#FF6B6B",
}

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "assets")

CSS_PATH = os.path.join(_ASSETS, "theme.css")

#: Equator Solar wordmark, transparent background so it sits on either theme.
LOGO_PATH = os.path.join(_ASSETS, "equator-solar-logo.png")

#: The ring from SOLAR, square, for the browser tab.
FAVICON_PATH = os.path.join(_ASSETS, "favicon.png")


def logo_path() -> str | None:
    """The wordmark, or None if the file is missing."""
    return LOGO_PATH if os.path.exists(LOGO_PATH) else None


def favicon():
    """Something st.set_page_config can use as page_icon.

    The ring if it is there, a lightning bolt if it is not -- a missing image
    should never stop the app loading.
    """
    return FAVICON_PATH if os.path.exists(FAVICON_PATH) else "\N{HIGH VOLTAGE SIGN}"


def apply(st) -> None:
    """Load the stylesheet and put the wordmark above the sidebar nav."""
    try:
        with open(CSS_PATH, encoding="utf-8") as fh:
            css = fh.read()
        st.markdown("<style>%s</style>" % css, unsafe_allow_html=True)
    except OSError:
        pass                         # styling is a nicety, never a blocker

    path = logo_path()
    if path is None:
        return
    try:
        # Streamlit 1.35+ puts this above the sidebar properly
        st.logo(path, size="large")
    except Exception:                                      # noqa: BLE001
        with st.sidebar:
            st.image(path, use_container_width=True)


# ---------------------------------------------------------------------------
# Chart colours
#
# OFF by default. The notebooks' own colour lists are what every report issued
# so far was drawn with, and a chart that changes colour between one report
# and the next invites the question of what else changed. Turn it on in the
# optional settings when you want new reports in house colours.
# ---------------------------------------------------------------------------

#: Three shades per quantity, light to dark, as the notebooks expect. Built
#: around the house green with enough separation to tell three phases apart
#: in print and on screen.
CHART_COLOURS = {
    # active power -- the house green
    "colorP": ["#5FC98C", "#188B44", "#0F6431"],
    # voltage -- warm, so it never reads as power
    "colorU": ["#E8A763", "#C96E1E", "#8A4A12"],
    # power factor -- cool teal
    "colorPF": ["#7FD4CE", "#2A9D8F", "#176B61"],
    # frequency -- muted sand
    "colorF": ["#D9C9A3", "#B89B5E", "#7E6835"],
    # apparent power -- olive, distinct from active power
    "colorA": ["#B9C97A", "#7E9A32", "#4E651B"],
    # current -- blue, the one quantity the house palette has no claim on
    "colorI": ["#7FA8D9", "#3B6FA8", "#1F4468"],
    # THD -- amber through to the danger red
    "colorTHD": ["#E3B23C", "#C96E1E", "#C2362F"],
}


def chart_settings(enabled: bool) -> dict:
    """Colour arguments for the plotting modules' configure().

    An empty dict leaves the notebooks' original colours in place.
    """
    return dict(CHART_COLOURS) if enabled else {}
