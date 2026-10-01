"""Device adapters. See base.py for the interface a device must provide."""

from . import econ, shelly

#: Every supported logger, keyed by the name used throughout the app.
ADAPTERS = {
    econ.NAME: econ,
    shelly.NAME: shelly,
}


def get(device: str):
    """The adapter for a device name."""
    try:
        return ADAPTERS[device]
    except KeyError:
        raise KeyError("unknown device %r (known: %s)"
                       % (device, ", ".join(sorted(ADAPTERS)))) from None


def choices():
    """(name, label) for every adapter, for the interface."""
    return [(name, mod.LABEL) for name, mod in sorted(ADAPTERS.items())]
