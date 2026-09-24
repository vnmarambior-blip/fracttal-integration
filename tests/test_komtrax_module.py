"""Komtrax reusable module: import-safe, paged, normalized, read-only."""

import importlib
from unittest.mock import Mock

import pytest
import requests


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = text

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._payload


def _block(*args, **kwargs):
    raise AssertionError("efecto lateral al importar")


def test_komtrax_imports_without_side_effects(monkeypatch, capsys):
    import mssql_python

    monkeypatch.setattr(mssql_python, "connect", _block)
    monkeypatch.setattr(requests, "post", _block)
    monkeypatch.setattr(requests, "get", _block)

    import komtrax
    importlib.reload(komtrax)

    out, _ = capsys.readouterr()
    assert out == ""
    for name in (
        "KomtraxFleetError",
        "get_komtrax_token",
        "get_komtrax_token_cached",
        "get_komtrax_fleet",
        "get_komtrax_fleet_all",
        "parse_komtrax_hours",
        "classify_komtrax_gap",
        "normalize_unit",
        "decide_comparison",
    ):
        assert callable(getattr(komtrax, name, None)), name


def test_fleet_all_follows_next_link(monkeypatch, tmp_path):
    import komtrax

    ns = "http://www.jcmanet.or.jp/english2017/ISO/15143/-3/20190501"

    def page(serial, hour, nxt=None):
        links = (
            f"<Links><rel>next</rel><href>{nxt}</href></Links>" if nxt else ""
        )
        return (
            '<?xml version="1.0"?>'
            f'<Fleet xmlns="{ns}" snapshotTime="2026-09-24T00:00:00Z">'
            f"{links}"
            "<Equipment><EquipmentHeader>"
            "<OEMName>KOMATSU</OEMName><Model>SYNTH</Model>"
            f"<EquipmentID>UNIT-{serial}</EquipmentID>"
            f"<SerialNumber>{serial}</SerialNumber>"
            "</EquipmentHeader>"
            '<CumulativeOperatingHours datetime="2026-09-24T00:00:00Z">'
            f"<Hour>{hour}</Hour></CumulativeOperatingHours>"
            "</Equipment></Fleet>"
        )

    get = Mock(
        side_effect=[
            FakeResponse(200, text=page("SN-P1", "10.0", "https://fleet.test/Fleet/2")),
            FakeResponse(200, text=page("SN-P2", "20.0")),
        ]
    )
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(
        komtrax, "KOMTRAX_FLEET_STATE", str(tmp_path / "fleet.state")
    )

    pages = komtrax.get_komtrax_fleet_all("test-token")

    assert get.call_count == 2
    merged = {}
    for xml in pages:
        merged.update(komtrax.parse_komtrax_hours(xml))
    assert merged["SN-P1"]["hours"] == 10.0
    assert merged["SN-P2"]["hours"] == 20.0


def test_rate_limited_makes_single_request(monkeypatch, tmp_path):
    import komtrax

    get = Mock(
        return_value=FakeResponse(
            429, {"message": "Try again in 293 seconds."}
        )
    )
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(
        komtrax, "KOMTRAX_FLEET_STATE", str(tmp_path / "fleet.state")
    )

    with pytest.raises(komtrax.KomtraxFleetError, match="RATE_LIMITED"):
        komtrax.get_komtrax_fleet("test-token")

    assert get.call_count == 1


def test_gap_states_are_distinct():
    import komtrax

    assert komtrax.classify_komtrax_gap(None) == "ABSENT"
    assert (
        komtrax.classify_komtrax_gap({"hours": None, "datetime": None})
        == "NO_HOURS"
    )
    assert (
        komtrax.classify_komtrax_gap(
            {"hours": None, "datetime": None, "_parse_error": "x"}
        )
        == "PARSE_ERROR"
    )
    assert komtrax.classify_komtrax_gap({"hours": 1.0, "datetime": "x"}) == "OK"


def test_normalize_unit_removes_inner_spaces():
    import komtrax

    assert komtrax.normalize_unit("CF 01") == "CF01"
    assert komtrax.normalize_unit("CF01") == "CF01"
    assert komtrax.normalize_unit("  mh 02 ") == "MH02"


def test_serial_remains_primary_identity():
    import komtrax

    ns = "http://www.jcmanet.or.jp/english2017/ISO/15143/-3/20190501"
    doc = (
        '<?xml version="1.0"?>'
        f'<Fleet xmlns="{ns}" snapshotTime="2026-09-24T00:00:00Z">'
        "<Equipment><EquipmentHeader>"
        "<OEMName>KOMATSU</OEMName><Model>SYNTH</Model>"
        "<EquipmentID>CF 01</EquipmentID><SerialNumber>73180</SerialNumber>"
        "</EquipmentHeader>"
        '<CumulativeOperatingHours datetime="2026-09-24T00:00:00Z">'
        "<Hour>5.0</Hour></CumulativeOperatingHours>"
        "</Equipment></Fleet>"
    )

    parsed = komtrax.parse_komtrax_hours(doc)

    assert "73180" in parsed
    assert parsed["73180"]["hours"] == 5.0


def test_compare_hours_reexports_komtrax_helpers():
    import importlib

    import komtrax
    import _compare_hours

    importlib.reload(komtrax)
    importlib.reload(_compare_hours)

    for name in (
        "get_komtrax_token_cached",
        "get_komtrax_fleet_all",
        "parse_komtrax_hours",
        "classify_komtrax_gap",
        "normalize_unit",
        "decide_comparison",
        "KomtraxFleetError",
    ):
        assert getattr(_compare_hours, name) is getattr(komtrax, name), name


def test_hourmeter_lookup_normalizes_unit_code(monkeypatch):
    import _compare_hours

    meter = {
        "description": "HOROMETER",
        "last_data": {"value": 10.0, "date": "2026-09-24T00:00:00"},
    }
    monkeypatch.setattr(
        _compare_hours, "get_valid_hourmeter", lambda token, eq: meter
    )

    assert _compare_hours.get_fracttal_hourmeter(
        "t", "CF 01", [{"code": "CF01"}]
    ) == {"value": 10.0, "date": "2026-09-24T00:00:00"}
