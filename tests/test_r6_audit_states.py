"""R6: todo resultado relevante reconstruible desde SQL. Mocks."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import api
import run_mydevelon_sync


SERIAL = "DHKCEBACPJ0021470"
READING_DATETIME = datetime(2026, 9, 15, 15, 25, 16, tzinfo=timezone.utc)
RETRIEVED_AT = datetime(2026, 9, 16, 14, 0, 0, tzinfo=timezone.utc)
EQUIPMENT = {"id": 100, "code": "MH12", "field_4": SERIAL}
CLASSIF = {
    "asset_type": "A",
    "group_1": "G1",
    "group_2": "G2",
    "classified": True,
}


def base_process_patches(saved, extra=None):
    patches = [
        patch.object(
            api, "get_equipment_by_serial", return_value=EQUIPMENT
        ),
        patch.object(api, "get_asset_type", return_value=CLASSIF),
        patch.object(api, "upsert_machinery", return_value={"id": 200}),
        patch.object(
            api, "save_horometer_update",
            side_effect=lambda **kw: saved.append(kw),
        ),
    ]
    return patches + list(extra or [])


class NoPinSourceHoursTests(unittest.TestCase):
    def setUp(self):
        self.saved = []
        self.process_calls = []

    def run_main(self, items):
        patches = [
            patch.object(
                run_mydevelon_sync, "resolve_fleet_xml_text",
                return_value="<fleet/>",
            ),
            patch.object(
                run_mydevelon_sync, "parse_fleet_xml", return_value=items
            ),
            patch.object(
                run_mydevelon_sync, "get_mydevelon_access_token",
                return_value="t",
            ),
            patch.object(
                run_mydevelon_sync, "get_fracttal_access_token",
                return_value="t",
            ),
            patch.object(
                run_mydevelon_sync, "process_equipment",
                side_effect=lambda **kw: self.process_calls.append(kw),
            ),
            patch.object(
                run_mydevelon_sync, "save_horometer_update",
                side_effect=lambda **kw: self.saved.append(kw),
                create=True,
            ),
        ]
        for item in patches:
            item.start()
        try:
            run_mydevelon_sync.main([])
        finally:
            for item in reversed(patches):
                item.stop()

    def test_error_no_pin_persists_single_nullable_row(self):
        self.run_main([{"pin": "", "oem_name": "DEVELON",
                        "operating_hours": 10.0,
                        "operating_hours_datetime": READING_DATETIME}])

        self.assertEqual(len(self.saved), 1)
        row = self.saved[0]
        self.assertIsNone(row["machinery_id"])
        self.assertIsNone(row["meter_id"])
        self.assertEqual(row["status"], "ERROR_NO_PIN")
        self.assertEqual(row["error_code"], "ERROR_NO_PIN")
        self.assertIsNone(row["idempotency_key"])
        self.assertEqual(self.process_calls, [])

    def test_error_source_hours_persists_single_nullable_row(self):
        self.run_main([{"pin": SERIAL, "oem_name": "DEVELON",
                        "operating_hours": None,
                        "operating_hours_datetime": READING_DATETIME}])

        self.assertEqual(len(self.saved), 1)
        row = self.saved[0]
        self.assertIsNone(row["machinery_id"])
        self.assertIsNone(row["meter_id"])
        self.assertEqual(row["meter_serial"], SERIAL)
        self.assertEqual(row["status"], "ERROR_SOURCE_HOURS")
        self.assertEqual(row["error_code"], "ERROR_SOURCE_HOURS")
        self.assertIsNone(row["new_value"])
        self.assertEqual(self.process_calls, [])


class EarlyReturnConfigTests(unittest.TestCase):
    def setUp(self):
        self.saved = []

    def call_process(self, extra, reading=READING_DATETIME):
        patches = base_process_patches(self.saved, extra)
        for item in patches:
            item.start()
        try:
            return api.process_equipment(
                token="mock-token",
                serial=SERIAL,
                new_value=7915.7,
                dry_run=True,
                reading_datetime=reading,
                retrieved_at=RETRIEVED_AT,
            )
        finally:
            for item in reversed(patches):
                item.stop()

    def test_review_source_date_early_return_persists(self):
        result = self.call_process([], reading=None)

        self.assertEqual(result["status"], "REVIEW_SOURCE_DATE")
        self.assertEqual(len(self.saved), 1)
        row = self.saved[0]
        self.assertIsNone(row["machinery_id"])
        self.assertIsNone(row["meter_id"])
        self.assertEqual(row["meter_serial"], SERIAL)
        self.assertEqual(row["decision"], "REVIEW_SOURCE_DATE")
        self.assertIsNone(row["idempotency_key"])

    def test_config_missing_persists(self):
        result = self.call_process(
            [patch.object(api, "get_telemetry_sync_config",
                          return_value=None)]
        )

        self.assertEqual(result["status"], "CONFIG_MISSING")
        self.assertEqual(len(self.saved), 1)
        row = self.saved[0]
        self.assertEqual(row["machinery_id"], 200)
        self.assertIsNone(row["meter_id"])
        self.assertEqual(row["status"], "REVIEW")
        self.assertEqual(row["error_code"], "CONFIG_MISSING")

    def test_sync_disabled_persists(self):
        result = self.call_process(
            [patch.object(api, "get_telemetry_sync_config",
                          return_value={"sync_enabled": False,
                                        "action_policy": "AUTO"})]
        )

        self.assertEqual(result["status"], "SYNC_DISABLED")
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0]["status"], "REVIEW")
        self.assertEqual(self.saved[0]["error_code"], "SYNC_DISABLED")

    def test_config_review_persists(self):
        result = self.call_process(
            [patch.object(api, "get_telemetry_sync_config",
                          return_value={"sync_enabled": True,
                                        "action_policy": "REVIEW"})]
        )

        self.assertEqual(result["status"], "CONFIG_REVIEW")
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0]["status"], "REVIEW")
        self.assertEqual(self.saved[0]["error_code"], "CONFIG_REVIEW")

    def test_config_multiple_persists(self):
        result = self.call_process(
            [patch.object(api, "get_telemetry_sync_config",
                          side_effect=ValueError("duplicada"))]
        )

        self.assertEqual(result["status"], "CONFIG_MULTIPLE")
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0]["status"], "REVIEW")
        self.assertEqual(self.saved[0]["error_code"], "CONFIG_MULTIPLE")

    def test_old_reading_returns_review_not_skip(self):
        old_reading = datetime(2022, 11, 30, tzinfo=timezone.utc)
        result = self.call_process(
            [patch.object(api, "get_telemetry_sync_config",
                          return_value={"sync_enabled": True,
                                        "action_policy": "AUTO"}),
             patch.object(api, "get_current_hourmeter",
                          return_value={
                              "meter": {"id": 127874,
                                        "serial": SERIAL},
                              "value": 4318.0,
                              "last_reading_datetime": datetime(
                                  2026, 7, 13, tzinfo=timezone.utc),
                          })],
            reading=old_reading,
        )

        self.assertEqual(result["status"], "REVIEW")
        self.assertNotEqual(result["status"], "SKIP_EQUAL")
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(
            self.saved[0]["decision"], "REVIEW_OLD_SOURCE"
        )
        self.assertEqual(self.saved[0]["status"], "REVIEW")
        self.assertEqual(self.saved[0]["write_status"], "BLOCKED")


class LiveAbortTests(unittest.TestCase):
    """Modo --live aborta ante cuota o flota vacia. Sin fallback a fixture."""

    def run_live_main(self, resolve_side_effect):
        process_calls = []

        patches = [
            patch.object(
                run_mydevelon_sync, "get_cached_token",
                return_value="t",
            ),
            patch.object(
                run_mydevelon_sync, "resolve_fleet_xml_text",
                side_effect=resolve_side_effect,
            ),
            patch.object(
                run_mydevelon_sync, "parse_fleet_xml",
                return_value=[{
                    "pin": SERIAL, "oem_name": "DEVELON",
                    "operating_hours": 10.0,
                    "operating_hours_datetime": READING_DATETIME,
                }],
            ),
            patch.object(
                run_mydevelon_sync, "get_mydevelon_access_token",
                return_value="t",
            ),
            patch.object(
                run_mydevelon_sync, "get_fracttal_access_token",
                return_value="t",
            ),
            patch.object(
                run_mydevelon_sync, "process_equipment",
                side_effect=lambda **kw: process_calls.append(kw)
                or {"status": "REVIEW", "serial": kw["serial"]},
            ),
        ]
        for item in patches:
            item.start()
        try:
            with self.assertRaises(RuntimeError):
                run_mydevelon_sync.main(["--live"])
        finally:
            for item in reversed(patches):
                item.stop()

        return process_calls

    def test_live_empty_aborts_without_fixture(self):
        def fake_resolve(**kwargs):
            assert kwargs.get("mode") == "live"
            return ""

        process_calls = self.run_live_main(fake_resolve)

        self.assertEqual(process_calls, [])

    def test_live_quota_aborts_without_fixture(self):
        import mydevelon

        def fake_resolve(**kwargs):
            assert kwargs.get("mode") == "live"
            raise mydevelon.QuotaExceededError("cuota")

        process_calls = self.run_live_main(fake_resolve)

        self.assertEqual(process_calls, [])

    def test_file_mode_still_uses_fixture(self):
        process_calls = []

        patches = [
            patch.object(
                run_mydevelon_sync, "resolve_fleet_xml_text",
                return_value="<fleet/>",
            ),
            patch.object(
                run_mydevelon_sync, "parse_fleet_xml",
                return_value=[{
                    "pin": SERIAL, "oem_name": "DEVELON",
                    "operating_hours": 10.0,
                    "operating_hours_datetime": READING_DATETIME,
                }],
            ),
            patch.object(
                run_mydevelon_sync, "get_fracttal_access_token",
                return_value="t",
            ),
            patch.object(
                run_mydevelon_sync, "process_equipment",
                side_effect=lambda **kw: process_calls.append(kw)
                or {"status": "REVIEW", "serial": kw["serial"]},
            ),
        ]
        for item in patches:
            item.start()
        try:
            run_mydevelon_sync.main([])
        finally:
            for item in reversed(patches):
                item.stop()

        self.assertEqual(len(process_calls), 1)
        self.assertEqual(process_calls[0]["serial"], SERIAL)


if __name__ == "__main__":
    unittest.main()
