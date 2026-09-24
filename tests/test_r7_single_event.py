"""R7: una actualización lógica = una sola fila. Sin red ni SQL real."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import api


SERIAL = "DHKCEBACPJ0021470"
READING_DATETIME = datetime(2026, 9, 15, 15, 25, 16, tzinfo=timezone.utc)
RETRIEVED_AT = datetime(2026, 9, 16, 14, 0, 0, tzinfo=timezone.utc)
EQUIPMENT = {"id": 100, "code": "MH12", "field_4": SERIAL}
METER = {"id": 127874, "serial": SERIAL}
CURRENT = {
    "meter": METER,
    "value": 7595.0,
    "last_reading_datetime": datetime(
        2026, 9, 14, 15, 25, 16, tzinfo=timezone.utc
    ),
}
KEY = api.build_idempotency_key(
    source="MYDEVELON",
    serial=SERIAL,
    meter_id=METER["id"],
    reading_datetime=READING_DATETIME,
    source_value=7915.7,
)


class ProcessSingleEventTests(unittest.TestCase):
    def setUp(self):
        self.put_calls = []
        self.saved = []
        self.existing = None
        self.apply_behavior = ("verified", None)

        def fake_apply(**kwargs):
            self.put_calls.append(kwargs)
            mode, payload = self.apply_behavior
            if mode == "raise":
                raise payload
            return {
                "status": "VERIFIED",
                "idempotency_key": KEY,
                "event_id": 55,
                "http_status": 200,
                "response": {},
            }

        def fake_save(**kwargs):
            self.saved.append(kwargs)

        self.patches = [
            patch.object(
                api, "get_equipment_by_serial", return_value=EQUIPMENT
            ),
            patch.object(
                api,
                "get_asset_type",
                return_value={
                    "asset_type": "A",
                    "group_1": "G1",
                    "group_2": "G2",
                    "classified": True,
                },
            ),
            patch.object(
                api, "upsert_machinery", return_value={"id": 200}
            ),
            patch.object(
                api,
                "get_telemetry_sync_config",
                return_value={
                    "sync_enabled": True,
                    "action_policy": "AUTO",
                },
            ),
            patch.object(
                api, "get_current_hourmeter", return_value=CURRENT
            ),
            patch.object(
                api,
                "get_horometer_update_by_idempotency_key",
                side_effect=lambda key: self.existing,
            ),
            patch.object(
                api, "apply_meter_reading", side_effect=fake_apply
            ),
            patch.object(
                api, "save_horometer_update", side_effect=fake_save
            ),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def call_process(self, dry_run=False):
        return api.process_equipment(
            token="mock-token",
            serial=SERIAL,
            new_value=7915.7,
            dry_run=dry_run,
            reading_datetime=READING_DATETIME,
            retrieved_at=RETRIEVED_AT,
        )

    def test_success_writes_zero_rows(self):
        result = self.call_process()

        self.assertEqual(self.saved, [])
        self.assertEqual(len(self.put_calls), 1)
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["event_id"], 55)
        self.assertEqual(result["idempotency_key"], KEY)

    def test_rerun_creates_no_row(self):
        first = self.call_process()
        second = self.call_process()

        self.assertEqual(first["status"], "VERIFIED")
        self.assertEqual(second["status"], "VERIFIED")
        self.assertEqual(self.saved, [])
        self.assertEqual(len(self.put_calls), 2)

    def test_error_with_existing_intent_writes_nothing(self):
        self.existing = {
            "id": 55,
            "write_status": "WRITE_AMBIGUOUS",
            "status": "WRITE_AMBIGUOUS",
        }
        self.apply_behavior = (
            "raise",
            ValueError("WRITE_AMBIGUOUS: resultado incierto."),
        )

        result = self.call_process()

        self.assertEqual(self.saved, [])
        self.assertEqual(result["status"], "WRITE_AMBIGUOUS")

    def test_error_without_existing_writes_single_keyed_row(self):
        self.existing = None
        self.apply_behavior = (
            "raise",
            ValueError("ERROR: fallo antes de la intención."),
        )

        result = self.call_process()

        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0]["idempotency_key"], KEY)
        self.assertEqual(self.saved[0]["status"], "ERROR")
        self.assertIn("decision", self.saved[0])
        self.assertIn("write_status", self.saved[0])
        self.assertEqual(result["status"], "ERROR")

    def test_dry_run_writes_single_keyed_row(self):
        result = self.call_process(dry_run=True)

        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0]["idempotency_key"], KEY)
        self.assertEqual(self.saved[0]["status"], "WOULD_UPDATE")
        self.assertIn("decision", self.saved[0])
        self.assertIn("write_status", self.saved[0])
        self.assertEqual(result["status"], "WOULD_UPDATE")
        self.assertEqual(self.put_calls, [])


if __name__ == "__main__":
    unittest.main()
