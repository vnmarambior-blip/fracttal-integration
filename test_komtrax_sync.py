from datetime import datetime, timezone
from unittest.mock import patch
import hashlib

import pytest

import api
import run_komtrax_sync


def test_process_equipment_accepts_source_parameter():
    import inspect
    import api

    params = inspect.signature(api.process_equipment).parameters
    assert params["source"].default == "MyDevelon"


_KOMTRAX_SERIAL = "DHKCEBACPJ0021470"
_KOMTRAX_READING = datetime(2022, 11, 30, tzinfo=timezone.utc)
_KOMTRAX_RETRIEVED = datetime(2026, 9, 16, 14, 0, 0, tzinfo=timezone.utc)


def _call_process_with_komtrax_source(saved):
    patches = [
        patch.object(
            api, "get_equipment_by_serial",
            return_value={"id": 100, "code": "MH12",
                          "field_4": _KOMTRAX_SERIAL},
        ),
        patch.object(
            api, "get_asset_type",
            return_value={"asset_type": "A", "group_1": "G1",
                          "group_2": "G2", "classified": True},
        ),
        patch.object(
            api, "upsert_machinery", return_value={"id": 200}
        ),
        patch.object(
            api, "get_telemetry_sync_config",
            return_value={"sync_enabled": True,
                          "action_policy": "AUTO"},
        ),
        patch.object(
            api, "get_current_hourmeter",
            return_value={
                "meter": {"id": 127874, "serial": _KOMTRAX_SERIAL},
                "value": 4318.0,
                "last_reading_datetime": datetime(
                    2026, 7, 13, tzinfo=timezone.utc),
            },
        ),
        patch.object(
            api, "save_horometer_update",
            side_effect=lambda **kw: saved.append(kw),
        ),
    ]
    for item in patches:
        item.start()
    try:
        return api.process_equipment(
            token="mock-token",
            serial=_KOMTRAX_SERIAL,
            new_value=7915.7,
            dry_run=True,
            reading_datetime=_KOMTRAX_READING,
            retrieved_at=_KOMTRAX_RETRIEVED,
            source="Komtrax",
        )
    finally:
        for item in reversed(patches):
            item.stop()


def test_process_equipment_passes_source_through_to_audit():
    saved = []
    result = _call_process_with_komtrax_source(saved)

    assert result["status"] == "REVIEW"
    assert len(saved) == 1
    assert saved[0]["source"] == "Komtrax"


def test_process_equipment_audit_message_uses_source_name():
    saved = []
    result = _call_process_with_komtrax_source(saved)

    assert result["status"] == "REVIEW"
    assert len(saved) == 1
    message = saved[0]["message"]
    assert "Komtrax" in message
    assert "MyDevelon" not in message


# ============================================================
# Task 3 — run_komtrax_sync dry-run executor
# ============================================================

_KT_FIXTURE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Fleet version="1" snapshotTime="2026-09-20T12:00:00Z" xmlns="http://www.jcmanet.or.jp/english2017/ISO/15143/-3/20190501">
  <Equipment>
    <EquipmentHeader><OEMName>KOMATSU</OEMName><Model>GD675-5</Model><EquipmentID>EQ-55267</EquipmentID><SerialNumber>55267</SerialNumber><PIN>55267</PIN></EquipmentHeader>
    <CumulativeOperatingHours datetime="2026-09-20T12:00:00Z"><Hour>5000</Hour></CumulativeOperatingHours>
  </Equipment>
  <Equipment>
    <EquipmentHeader><OEMName>KOMATSU</OEMName><Model>PC200LC-8</Model><EquipmentID>EQ-354483</EquipmentID><SerialNumber>354483</SerialNumber><PIN>354483</PIN></EquipmentHeader>
    <CumulativeOperatingHours datetime="2026-09-20T12:00:00Z"><Hour>3000</Hour></CumulativeOperatingHours>
  </Equipment>
  <Equipment>
    <EquipmentHeader><OEMName>KOMATSU</OEMName><Model>PC200LC-8M0</Model><EquipmentID>EQ-400293</EquipmentID><SerialNumber>400293</SerialNumber><PIN>400293</PIN></EquipmentHeader>
  </Equipment>
</Fleet>
"""

_KT_FT_ITEMS = [{"code": "MN04"}, {"code": "MH02"}, {"code": "MH04"}]

_KT_FT_READINGS = {
    "MN04": {"value": 4000.0, "date": "2026-09-10T12:00:00+00:00"},
    "MH02": {"value": 3000.0, "date": "2026-09-20T12:00:00+00:00"},
    "MH04": {"value": 1000.0, "date": "2026-09-10T12:00:00+00:00"},
}


def _write_kt_fixture(tmp_path):
    path = tmp_path / "komtrax_fixture.xml"
    path.write_text(_KT_FIXTURE_XML, encoding="utf-8")
    return str(path)


_KT_MACHINES = [
    {"serial": "55267", "unit": "MN04", "model": "GD675-5"},
    {"serial": "354483", "unit": "MH02", "model": "PC200LC-8"},
    {"serial": "400293", "unit": "MH04", "model": "PC200LC-8M0"},
]


def _run_kt_file_mode(fixture_path, monkeypatch):
    monkeypatch.delenv("SYNC_DRY_RUN", raising=False)
    with (
        patch.object(run_komtrax_sync, "KOMTRAX_MACHINES",
                     list(_KT_MACHINES)),
        patch.object(run_komtrax_sync, "get_fracttal_access_token",
                     return_value="ft-test-token"),
        patch.object(run_komtrax_sync, "get_fracttal_items",
                     return_value=_KT_FT_ITEMS),
        patch.object(run_komtrax_sync, "get_fracttal_hourmeter",
                     side_effect=lambda tok, code, items: dict(
                         _KT_FT_READINGS[code])),
        patch.object(run_komtrax_sync, "process_equipment",
                     return_value={"status": "WOULD_UPDATE"}) as proc,
    ):
        counts = run_komtrax_sync.main(
            ["--fleet-xml", fixture_path])
    return counts, proc


def test_dry_run_sends_only_update_decisions(tmp_path, monkeypatch):
    fixture = _write_kt_fixture(tmp_path)
    counts, proc = _run_kt_file_mode(fixture, monkeypatch)

    assert counts == {"UPDATE": 1, "SKIP_EQUAL": 1, "REVIEW_OLD_SOURCE": 0,
                      "REVIEW_INCONSISTENCY": 1, "ERROR": 0}

    assert proc.call_count == 1
    _, kwargs = proc.call_args
    assert kwargs["dry_run"] is True
    assert kwargs["source"] == "Komtrax"
    assert kwargs["serial"] == "55267"
    assert kwargs["new_value"] == 5000.0


def test_file_mode_makes_zero_network_requests(tmp_path, monkeypatch):
    fixture = _write_kt_fixture(tmp_path)
    monkeypatch.delenv("SYNC_DRY_RUN", raising=False)

    def _forbidden(*args, **kwargs):
        raise AssertionError("network request forbidden in file mode")

    with (
        patch("requests.get", side_effect=_forbidden),
        patch("requests.post", side_effect=_forbidden),
        patch.object(run_komtrax_sync, "get_fracttal_access_token",
                     return_value="ft-test-token"),
        patch.object(run_komtrax_sync, "get_fracttal_items",
                     return_value=_KT_FT_ITEMS),
        patch.object(run_komtrax_sync, "get_fracttal_hourmeter",
                     side_effect=lambda tok, code, items: dict(
                         _KT_FT_READINGS[code])),
        patch.object(run_komtrax_sync, "process_equipment",
                     return_value={"status": "WOULD_UPDATE"}),
    ):
        counts = run_komtrax_sync.main(["--fleet-xml", fixture])

    assert counts["UPDATE"] == 1


def test_cf01_with_space_normalizes_before_match():
    assert run_komtrax_sync.normalize_unit("CF 01") == "CF01"
    assert run_komtrax_sync.normalize_unit("CF01") == "CF01"
    found = run_komtrax_sync.find_fracttal_item(
        "CF01", [{"code": "CF 01"}])
    assert found == {"code": "CF 01"}


def test_live_mode_restores_fleet_interval_constant(tmp_path, monkeypatch):
    import _compare_hours

    fixture = _write_kt_fixture(tmp_path)
    monkeypatch.delenv("SYNC_DRY_RUN", raising=False)
    before = _compare_hours.KOMTRAX_FLEET_MIN_INTERVAL_SECONDS
    flag = before + 7
    seen = {}

    def _fake_fleet(token):
        seen["interval"] = (
            _compare_hours.KOMTRAX_FLEET_MIN_INTERVAL_SECONDS
        )
        return _KT_FIXTURE_XML

    with (
        patch.object(run_komtrax_sync, "KOMTRAX_MACHINES",
                     list(_KT_MACHINES)),
        patch.object(run_komtrax_sync, "get_komtrax_token_cached",
                     return_value="kt-test-token"),
        patch.object(run_komtrax_sync, "get_komtrax_fleet",
                     side_effect=_fake_fleet),
        patch.object(run_komtrax_sync, "get_fracttal_access_token",
                     return_value="ft-test-token"),
        patch.object(run_komtrax_sync, "get_fracttal_items",
                     return_value=_KT_FT_ITEMS),
        patch.object(run_komtrax_sync, "get_fracttal_hourmeter",
                     side_effect=lambda tok, code, items: dict(
                         _KT_FT_READINGS[code])),
        patch.object(run_komtrax_sync, "process_equipment",
                     return_value={"status": "WOULD_UPDATE"}),
    ):
        counts = run_komtrax_sync.main(
            ["--live", "--fleet-xml", fixture,
             "--min-interval-seconds", str(flag)])

    assert counts["UPDATE"] == 1
    assert seen["interval"] == flag
    assert _compare_hours.KOMTRAX_FLEET_MIN_INTERVAL_SECONDS == before


def test_mydevelon_idempotency_key_byte_identical():
    reading = datetime(2026, 9, 1, tzinfo=timezone.utc)
    canonical = "MYDEVELON|55267|999|2026-09-01T00:00:00Z|5000.00"
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert api.build_idempotency_key(
        source="MyDevelon", serial="55267", meter_id=999,
        reading_datetime=reading, source_value=5000,
    ) == expected


def test_komtrax_idempotency_key_distinctly_namespaced():
    reading = datetime(2026, 9, 1, tzinfo=timezone.utc)
    canonical = "KOMTRAX|55267|999|2026-09-01T00:00:00Z|5000.00"
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    key_kt = api.build_idempotency_key(
        source="Komtrax", serial="55267", meter_id=999,
        reading_datetime=reading, source_value=5000,
    )
    key_md = api.build_idempotency_key(
        source="MyDevelon", serial="55267", meter_id=999,
        reading_datetime=reading, source_value=5000,
    )
    assert key_kt == expected
    assert key_kt != key_md
    assert run_komtrax_sync.KOMTRAX_SOURCE == "Komtrax"


_KT_PIN_SERIAL = "55267"
_KT_PIN_READING = datetime(2026, 9, 1, tzinfo=timezone.utc)
_KT_PIN_RETRIEVED = datetime(2026, 9, 16, 14, 0, 0, tzinfo=timezone.utc)


def _call_process_capture(saved, captured, source):
    def _fake_telemetry_config(**kwargs):
        captured.update(kwargs)
        return {"sync_enabled": True, "action_policy": "AUTO"}

    patches = [
        patch.object(
            api, "get_equipment_by_serial",
            return_value={"id": 100, "code": "MN04",
                          "field_4": _KT_PIN_SERIAL},
        ),
        patch.object(
            api, "get_asset_type",
            return_value={"asset_type": "A", "group_1": "G1",
                          "group_2": "G2", "classified": True},
        ),
        patch.object(
            api, "upsert_machinery", return_value={"id": 200}
        ),
        patch.object(
            api, "get_telemetry_sync_config",
            side_effect=_fake_telemetry_config,
        ),
        patch.object(
            api, "get_current_hourmeter",
            return_value={
                "meter": {"id": 999, "serial": _KT_PIN_SERIAL,
                          "description": "HOROMETER"},
                "value": 4000.0,
                "last_reading_datetime": datetime(
                    2026, 7, 13, tzinfo=timezone.utc),
            },
        ),
        patch.object(
            api, "save_horometer_update",
            side_effect=lambda **kw: saved.append(kw),
        ),
    ]
    for item in patches:
        item.start()
    try:
        return api.process_equipment(
            token="mock-token",
            serial=_KT_PIN_SERIAL,
            new_value=5000.0,
            dry_run=True,
            reading_datetime=_KT_PIN_READING,
            retrieved_at=_KT_PIN_RETRIEVED,
            source=source,
        )
    finally:
        for item in reversed(patches):
            item.stop()


def _call_process_capture_komtrax(saved, captured):
    return _call_process_capture(saved, captured, source="Komtrax")


def _call_process_capture_mydevelon(saved, captured):
    return _call_process_capture(saved, captured, source="MyDevelon")


def test_komtrax_telemetry_lookup_uses_komtrax_namespace():
    saved_kt, captured_kt = [], {}
    result_kt = _call_process_capture_komtrax(saved_kt, captured_kt)
    saved_md, captured_md = [], {}
    result_md = _call_process_capture_mydevelon(saved_md, captured_md)

    assert result_kt["status"] == "WOULD_UPDATE"
    assert result_md["status"] == "WOULD_UPDATE"
    assert captured_md.get("telemetry_source") == "MYDEVELON"
    assert captured_kt.get("telemetry_source") == "KOMTRAX"
    assert captured_kt.get("telemetry_source") != captured_md.get(
        "telemetry_source")


def test_komtrax_internal_idempotency_key_uses_komtrax_namespace():
    saved_kt, captured_kt = [], {}
    result_kt = _call_process_capture_komtrax(saved_kt, captured_kt)
    saved_md, captured_md = [], {}
    result_md = _call_process_capture_mydevelon(saved_md, captured_md)

    assert result_kt["status"] == "WOULD_UPDATE"
    assert result_md["status"] == "WOULD_UPDATE"
    assert len(saved_kt) == 1
    assert len(saved_md) == 1
    expected_md = api.build_idempotency_key(
        source="MyDevelon", serial=_KT_PIN_SERIAL, meter_id=999,
        reading_datetime=_KT_PIN_READING, source_value=5000.0,
    )
    expected_kt = api.build_idempotency_key(
        source="Komtrax", serial=_KT_PIN_SERIAL, meter_id=999,
        reading_datetime=_KT_PIN_READING, source_value=5000.0,
    )
    assert saved_md[0]["idempotency_key"] == expected_md
    assert saved_kt[0]["idempotency_key"] == expected_kt
    assert saved_kt[0]["idempotency_key"] != saved_md[0][
        "idempotency_key"]


# ============================================================
# Task 4 — productive gate on Regla 0 / H1
# ============================================================

def test_live_mode_refuses_when_gates_open(tmp_path, monkeypatch):
    import run_komtrax_sync

    fixture = tmp_path / "fleet.xml"
    fixture.write_text("<Fleet />", encoding="utf-8")
    monkeypatch.setattr(run_komtrax_sync, "gates_closed", lambda: False)
    monkeypatch.setenv("SYNC_DRY_RUN", "false")

    def _forbidden(*args, **kwargs):
        raise AssertionError("network request forbidden before gate refusal")

    with (
        patch("requests.get", side_effect=_forbidden),
        patch("requests.post", side_effect=_forbidden),
    ):
        with pytest.raises(SystemExit) as exc:
            run_komtrax_sync.main(["--live", "--fleet-xml", str(fixture)])

    assert exc.value.code == 2


def test_dry_run_never_consults_gates(tmp_path, monkeypatch):
    import run_komtrax_sync

    fixture = _write_kt_fixture(tmp_path)
    monkeypatch.delenv("SYNC_DRY_RUN", raising=False)

    def _forbidden_gate():
        raise AssertionError("gates must not be consulted in dry-run")

    with (
        patch.object(run_komtrax_sync, "gates_closed",
                     side_effect=_forbidden_gate),
        patch.object(run_komtrax_sync, "KOMTRAX_MACHINES",
                     list(_KT_MACHINES)),
        patch.object(run_komtrax_sync, "get_fracttal_access_token",
                     return_value="ft-test-token"),
        patch.object(run_komtrax_sync, "get_fracttal_items",
                     return_value=_KT_FT_ITEMS),
        patch.object(run_komtrax_sync, "get_fracttal_hourmeter",
                     side_effect=lambda tok, code, items: dict(
                         _KT_FT_READINGS[code])),
        patch.object(run_komtrax_sync, "process_equipment",
                     return_value={"status": "WOULD_UPDATE"}),
    ):
        counts = run_komtrax_sync.main(["--fleet-xml", fixture])

    assert counts["UPDATE"] == 1
