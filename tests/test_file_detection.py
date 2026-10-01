"""Encoding, delimiter and device detection."""

import pytest

from src import file_detection as fd


def test_econ_profile(econ_bytes):
    prof = fd.profile_file(econ_bytes, "econ.csv")
    assert prof.ok
    assert prof.delimiter == ";"
    assert prof.device == "econ"
    assert prof.device_confidence == "certain"
    assert "Pactive total avg [kW]" in prof.columns


def test_shelly_profile(shelly_bytes):
    prof = fd.profile_file(shelly_bytes, "shelly.csv")
    assert prof.ok
    assert prof.delimiter == ","
    assert prof.device == "shelly"
    assert prof.device_confidence == "certain"
    assert "a_total_act_energy" in prof.columns


def test_empty_file_is_rejected():
    prof = fd.profile_file(b"", "empty.csv")
    assert not prof.ok
    assert "empty" in prof.error.lower()


def test_whitespace_only_file_is_rejected():
    prof = fd.profile_file(b"   \n\n  \n", "blank.csv")
    assert not prof.ok


def test_binary_file_is_rejected():
    # a PNG header: decodable by latin-1, but it has no delimiter
    prof = fd.profile_file(b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4,
                           "image.png")
    assert not prof.ok


def test_single_column_file_is_rejected():
    prof = fd.profile_file(b"OnlyColumn\n1\n2\n3\n", "one.csv")
    assert not prof.ok


def test_unknown_columns_give_no_device():
    data = b"alpha,beta,gamma\n1,2,3\n4,5,6\n"
    prof = fd.profile_file(data, "mystery.csv")
    assert prof.ok
    assert prof.device is None
    assert prof.device_confidence == "none"


def test_mixed_signatures_refuse_to_guess():
    device, confidence, reason = fd.identify_device(
        ["Time", "Pactive total avg [kW]", "L1 Urms avg [V]",
         "timestamp", "a_total_act_energy", "a_avg_voltage"])
    assert device is None
    assert confidence == "none"
    assert "both" in reason


def test_partial_match_is_likely_not_certain():
    device, confidence, _ = fd.identify_device(["timestamp",
                                                "a_total_act_energy"])
    assert device == "shelly"
    assert confidence == "likely"


@pytest.mark.parametrize("device", ["econ", "shelly"])
def test_missing_columns_are_listed(device, econ_bytes, shelly_bytes):
    data = econ_bytes if device == "econ" else shelly_bytes
    prof = fd.profile_file(data, "f.csv")
    assert fd.missing_columns(prof.columns, device) == []
    # drop one and it must be reported
    trimmed = [c for c in prof.columns
               if c != fd.REQUIRED_COLUMNS[device][2]]
    assert fd.REQUIRED_COLUMNS[device][2] in fd.missing_columns(trimmed, device)


def test_bom_is_consumed_not_glued_to_the_first_column():
    data = "﻿Time;Pactive total avg [kW]\n01/04/2026 00:00:00;1.0\n" \
        .encode("utf-8")
    prof = fd.profile_file(data, "bom.csv")
    assert prof.ok
    assert prof.columns[0] == "Time"


def test_read_full_does_not_alter_values(shelly_bytes):
    prof = fd.profile_file(shelly_bytes, "s.csv")
    df = fd.read_full(shelly_bytes, prof.delimiter, prof.encoding)
    # every row survives; nothing is coerced or dropped
    assert len(df) == shelly_bytes.decode().strip().count("\n")
    assert df["a_total_act_energy"].notna().all()


# ---------------------------------------------------------------------------
# Workbook uploads
#
# Logger exports reach staff as .xlsx more often than anyone would like,
# because someone opened the CSV in Excel and pressed save.
# ---------------------------------------------------------------------------

def test_single_column_workbook_is_flattened(econ_workbook_bytes):
    """Excel does not split a ';' file, so the whole row sits in one cell."""
    prof = fd.profile_file(econ_workbook_bytes, "export.xlsx")
    assert prof.ok
    assert prof.from_workbook
    assert prof.delimiter == ";"
    assert prof.device == "econ"
    assert fd.missing_columns(prof.columns, "econ") == []
    assert "one column" in prof.workbook_note


def test_multi_column_workbook_is_flattened(econ_bytes):
    from conftest import make_workbook
    data = make_workbook(econ_bytes, single_column=False)
    prof = fd.profile_file(data, "export.xlsx")
    assert prof.ok
    assert prof.from_workbook
    assert prof.device == "econ"


def test_workbook_values_survive_the_round_trip(econ_bytes,
                                                econ_workbook_bytes):
    import io
    import pandas as pd
    original = pd.read_csv(io.BytesIO(econ_bytes), sep=";", encoding="cp1252")
    prepared = fd.prepared_bytes(econ_workbook_bytes, "export.xlsx")
    restored = fd.read_full(prepared, ";", "utf-8")
    assert list(restored.columns) == [c.strip() for c in original.columns]
    assert len(restored) == len(original)
    pd.testing.assert_series_equal(
        restored["Pactive total avg [kW]"].astype(float),
        original["Pactive total avg [kW]"].astype(float),
        check_names=False)


def test_a_csv_passes_through_prepared_bytes_untouched(econ_bytes):
    assert fd.prepared_bytes(econ_bytes, "export.csv") is econ_bytes


def test_corrupt_workbook_is_rejected_with_advice():
    prof = fd.profile_file(b"PK\x03\x04not really a zip", "broken.xlsx")
    assert not prof.ok
    assert "logger" in prof.error.lower()
