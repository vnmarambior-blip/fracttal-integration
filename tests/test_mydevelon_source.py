"""Modo fixture + guardián de cuota MyDevelon (1 consulta / 15 min).

Cero red: todo contra archivos temporales.
"""

from datetime import datetime, timezone
from unittest import TestCase

from mydevelon import (
    FleetEmptyError,
    QuotaExceededError,
    get_cached_token,
    is_fetch_allowed,
    load_fleet_xml_from_file,
    parse_equipment_snapshot_xml,
    parse_fleet_xml,
    record_fetch,
    resolve_fleet_xml_text,
    save_fleet_xml_snapshot,
)

SAMPLE_XML = """<?xml version="1.0"?>
<Fleet><Equipment><PIN>ABC123</PIN></Equipment></Fleet>
"""


def test_load_fleet_xml_from_file_returns_text(tmp_path):
    fixture = tmp_path / "fleet.xml"
    fixture.write_text(SAMPLE_XML, encoding="utf-8")

    assert load_fleet_xml_from_file(str(fixture)) == SAMPLE_XML


def test_save_and_load_fleet_xml_roundtrip(tmp_path):
    path = str(tmp_path / "snapshot.xml")

    saved = save_fleet_xml_snapshot(SAMPLE_XML, path)

    assert saved == path
    assert load_fleet_xml_from_file(path) == SAMPLE_XML


def test_fetch_allowed_without_previous_state(tmp_path):
    state = str(tmp_path / "last_fetch.txt")

    assert is_fetch_allowed(state) is True


def test_fetch_blocked_within_interval(tmp_path):
    state = str(tmp_path / "last_fetch.txt")
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    record_fetch(state, now=now)

    assert is_fetch_allowed(state, now=now) is False


def test_fetch_allowed_after_interval(tmp_path):
    state = str(tmp_path / "last_fetch.txt")
    before = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    after = datetime(2026, 9, 22, 12, 16, tzinfo=timezone.utc)
    record_fetch(state, now=before)

    assert is_fetch_allowed(state, min_interval_seconds=900, now=after) is True


def test_cached_token_reused_without_fetch(tmp_path):
    cache = str(tmp_path / "token.txt")
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    calls = []

    def fetcher():
        calls.append(1)
        return "live-token"

    first = get_cached_token(cache, ttl_seconds=1800, fetcher=fetcher, now=now)
    second = get_cached_token(cache, ttl_seconds=1800, fetcher=fetcher, now=now)

    assert (first, second) == ("live-token", "live-token")
    assert len(calls) == 1


def test_expired_token_triggers_refetch(tmp_path):
    cache = str(tmp_path / "token.txt")
    before = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    after = datetime(2026, 9, 22, 13, 0, tzinfo=timezone.utc)
    tokens = ["old-token", "new-token"]

    def fetcher():
        return tokens.pop(0)

    assert get_cached_token(cache, ttl_seconds=1800, fetcher=fetcher, now=before) == "old-token"
    assert get_cached_token(cache, ttl_seconds=1800, fetcher=fetcher, now=after) == "new-token"


def test_resolve_fleet_xml_in_file_mode_uses_no_network(tmp_path):
    fixture = tmp_path / "fleet.xml"
    fixture.write_text(SAMPLE_XML, encoding="utf-8")
    calls = []

    def fetcher():
        calls.append(1)
        return "live"

    text = resolve_fleet_xml_text(
        mode="file",
        fleet_xml_path=str(fixture),
        state_path=str(tmp_path / "last_fetch.txt"),
        fetcher=fetcher,
    )

    assert text == SAMPLE_XML
    assert calls == []


def test_resolve_fleet_xml_live_blocked_within_quota(tmp_path):
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    state = str(tmp_path / "last_fetch.txt")
    record_fetch(state, now=now)
    calls = []

    def fetcher():
        calls.append(1)
        return "live"

    try:
        resolve_fleet_xml_text(
            mode="live",
            fleet_xml_path="unused.xml",
            state_path=state,
            fetcher=fetcher,
            now=now,
        )
        blocked = False
    except QuotaExceededError:
        blocked = True

    assert blocked is True
    assert calls == []


def test_resolve_fleet_xml_live_records_and_saves_snapshot(tmp_path):
    state = str(tmp_path / "last_fetch.txt")
    snapshot = str(tmp_path / "snapshot.xml")
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)

    def fetcher():
        return SAMPLE_XML

    text = resolve_fleet_xml_text(
        mode="live",
        fleet_xml_path="unused.xml",
        state_path=state,
        fetcher=fetcher,
        record_path=snapshot,
        now=now,
    )

    assert text == SAMPLE_XML
    assert is_fetch_allowed(state, now=now) is False
    assert load_fleet_xml_from_file(snapshot) == SAMPLE_XML


SNAPSHOT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Equipment xmlns="http://standards.iso.org/iso/15143/-3">
  <EquipmentHeader>
    <OEMName>DEVELON</OEMName>
    <Model>DX225LCA</Model>
    <EquipmentID>CEBDX-001085</EquipmentID>
    <SerialNumber>CEBDX-001085</SerialNumber>
    <PIN>DHKCEBDXCK0001085</PIN>
  </EquipmentHeader>
  <CumulativeOperatingHours datetime="2026-09-21T10:00:00Z">
    <Hour>6466.00</Hour>
  </CumulativeOperatingHours>
</Equipment>
"""


def test_parse_snapshot_with_equipment_root():
    equipment = parse_equipment_snapshot_xml(SNAPSHOT_XML)

    assert equipment["pin"] == "DHKCEBDXCK0001085"
    assert equipment["serial_number"] == "CEBDX-001085"
    assert equipment["oem"] == "DEVELON"
    assert equipment["oem_name"] == "DEVELON"
    assert equipment["model"] == "DX225LCA"
    assert equipment["equipment_id"] == "CEBDX-001085"
    assert equipment["operating_hours"] == 6466.00
    assert equipment["retrieved_at"] is not None


def test_parse_snapshot_with_wrapper_root():
    inner = SNAPSHOT_XML.split("<EquipmentHeader>", 1)[1].rsplit(
        "</Equipment>", 1
    )[0]
    wrapped = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Fleet xmlns="http://standards.iso.org/iso/15143/-3"'
        ' snapshotTime="2026-09-21T12:00:00Z">'
        "<Equipment><EquipmentHeader>"
        + inner
        + "</Equipment></Fleet>"
    )

    equipment = parse_equipment_snapshot_xml(wrapped)

    assert equipment is not None
    assert equipment["pin"] == "DHKCEBDXCK0001085"


def test_parse_snapshot_without_equipment_returns_none():
    empty = """<?xml version="1.0"?><Fleet xmlns="http://standards.iso.org/iso/15143/-3"/>"""

    assert parse_equipment_snapshot_xml(empty) is None


NS = "http://standards.iso.org/iso/15143/-3"


def _fleet_doc(*bodies):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Fleet xmlns="{NS}" snapshotTime="2026-09-22T12:00:00Z">'
        + "".join(bodies)
        + "</Fleet>"
    )


def _equipment(pin, hour, hour_dt):
    return (
        "<Equipment>"
        "<EquipmentHeader>"
        f"<OEMName>DEVELON</OEMName><Model>DX225LCA</Model>"
        f"<EquipmentID>{pin}-ID</EquipmentID>"
        f"<SerialNumber>{pin}-SN</SerialNumber>"
        f"<PIN>{pin}</PIN>"
        "</EquipmentHeader>"
        f'<CumulativeOperatingHours datetime="{hour_dt}">'
        f"<Hour>{hour}</Hour>"
        "</CumulativeOperatingHours>"
        "</Equipment>"
    )


def test_mixed_fleet_isolates_bad_item():
    doc = _fleet_doc(
        _equipment("PIN-A", "100.50", "2026-09-22T10:00:00Z"),
        _equipment("PIN-B", "N/A", "2026-09-22T10:00:00Z"),
        _equipment("PIN-C", "200.00", "not-a-date"),
    )

    fleet = parse_fleet_xml(doc)

    assert len(fleet) == 3
    assert fleet[0]["pin"] == "PIN-A"
    assert fleet[0]["operating_hours"] == 100.50
    assert fleet[0].get("_parse_error") is None
    assert fleet[1]["pin"] == "PIN-B"
    assert fleet[1]["operating_hours"] is None
    assert fleet[1].get("_parse_error") is not None
    assert fleet[2]["pin"] == "PIN-C"
    assert fleet[2].get("_parse_error") is not None


def test_missing_header_kept_as_error_not_dropped():
    doc = _fleet_doc("<Equipment></Equipment>")

    fleet = parse_fleet_xml(doc)

    assert len(fleet) == 1
    assert fleet[0].get("_parse_error") is not None


def test_empty_fleet_raises_explicit():
    doc = (f'<?xml version="1.0"?><Fleet xmlns="{NS}"'
           f' snapshotTime="2026-09-22T12:00:00Z"/>')

    try:
        parse_fleet_xml(doc)
        raised = False
    except FleetEmptyError:
        raised = True

    assert raised is True


def test_blank_input_raises_explicit():
    try:
        parse_fleet_xml("   ")
        raised = False
    except FleetEmptyError:
        raised = True

    assert raised is True


class MH18RegressionTests(TestCase):
    def test_old_reading_never_skip_equal(self):
        from api import validate_reading_is_newer

        old = datetime(2022, 11, 30, tzinfo=timezone.utc)
        last = datetime(2026, 7, 13, tzinfo=timezone.utc)

        self.assertNotEqual(
            validate_reading_is_newer(old, last), "SKIP_EQUAL"
        )

    def test_old_reading_signals_stale(self):
        from api import validate_reading_is_newer

        old = datetime(2022, 11, 30, tzinfo=timezone.utc)
        last = datetime(2026, 7, 13, tzinfo=timezone.utc)

        self.assertEqual(
            validate_reading_is_newer(old, last), "REVIEW_OLD_SOURCE"
        )

    def test_equal_timestamp_keeps_skip_equal(self):
        from api import validate_reading_is_newer

        moment = datetime(2026, 7, 13, tzinfo=timezone.utc)

        self.assertEqual(
            validate_reading_is_newer(moment, moment), "SKIP_EQUAL"
        )
