"""R5: PUT → GET → estado terminal, normalizado a 2 decimales."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import api
import requests


READING_DATETIME = datetime(
    2026, 9, 15, 15, 25, 16, tzinfo=timezone.utc
)
RETRIEVED_AT = datetime(
    2026, 9, 16, 14, 0, 0, tzinfo=timezone.utc
)
EQUIPMENT = {
    "id": 100,
    "code": "MH12",
    "field_3": "DX225LCA",
    "field_4": "DHKCEBACPJ0021470",
}
METER = {
    "id": 127874,
    "active": True,
    "serial": "DHKCEBACPJ0021470",
    "description": "HOROMETRO",
    "units_code": "HRS",
    "is_counter": True,
    "counter_value": 7595.0,
    "last_data": {
        "value": 7595.0,
        "date": "2026-09-14T15:25:16+00:00",
    },
}
MACHINERY = {"id": 200, "serial": "DHKCEBACPJ0021470"}
CONFIG = {"sync_enabled": True, "action_policy": "AUTO"}
PUT_OK = {
    "payload": {
        "data": {"id_meters_readings": 9000, "is_duplicate": False}
    },
    "http_status": 200,
}


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.events = {}
        self.put_calls = []
        self.updates = []
        self.saves = []
        self.event_counter = 0
        self.verified_value = 7915.7
        self.get_failure = None

        def create_intent(**kwargs):
            self.event_counter += 1
            event_id = self.event_counter
            self.events[kwargs["idempotency_key"]] = {
                "id": event_id,
                "write_status": "INTENT_RECORDED",
                "status": "INTENT_RECORDED",
            }
            return event_id

        def fake_current(*args, **kwargs):
            if self.put_calls:
                if self.get_failure is not None:
                    raise self.get_failure
                return {
                    "meter": METER,
                    "value": self.verified_value,
                    "last_reading_datetime": datetime(
                        2026, 9, 16, 15, 25, 16, tzinfo=timezone.utc
                    ),
                }
            return {
                "meter": METER,
                "value": 7595.0,
                "last_reading_datetime": datetime(
                    2026, 9, 14, 15, 25, 16, tzinfo=timezone.utc
                ),
            }

        def fake_insert(**kwargs):
            self.put_calls.append(kwargs)
            return PUT_OK

        def fake_update(event_id, **kwargs):
            self.updates.append((event_id, kwargs))
            for event in self.events.values():
                if event["id"] == event_id:
                    event.update(kwargs)

        def fake_save(**kwargs):
            self.saved_marker = kwargs
            self.saves.append(kwargs)

        self.saved_marker = None
        self.patches = [
            patch.object(
                api, "get_equipment_by_serial", return_value=EQUIPMENT
            ),
            patch.object(
                api, "get_machinery_by_id", return_value=MACHINERY
            ),
            patch.object(
                api, "get_telemetry_sync_config", return_value=CONFIG
            ),
            patch.object(
                api, "get_current_hourmeter", side_effect=fake_current
            ),
            patch.object(
                api,
                "get_horometer_update_by_idempotency_key",
                side_effect=lambda key: self.events.get(key),
            ),
            patch.object(
                api, "create_horometer_write_intent",
                side_effect=create_intent,
            ),
            patch.object(api, "mark_horometer_write_in_progress"),
            patch.object(
                api, "update_horometer_write_result",
                side_effect=fake_update,
            ),
            patch.object(
                api, "insert_meter_reading", side_effect=fake_insert
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

    def call_apply(self):
        return api.apply_meter_reading(
            token="mock-token",
            code="MH12",
            value=7915.7,
            serial=EQUIPMENT["field_4"],
            reading_datetime=READING_DATETIME,
            retrieved_at=RETRIEVED_AT,
            decision="UPDATE",
            dry_run=False,
            equipment=EQUIPMENT,
            machinery_id=MACHINERY["id"],
        )

    def key_of_last_event(self):
        return next(iter(self.events))

    def test_exact_match_verifies(self):
        result = self.call_apply()

        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["event_id"], 1)
        self.assertEqual(result["idempotency_key"], self.key_of_last_event())
        self.assertEqual(self.saves, [])
        self.assertEqual(len(self.put_calls), 1)

    def test_sub_precision_difference_verifies(self):
        self.verified_value = 7915.6999999

        result = self.call_apply()

        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["event_id"], 1)
        self.assertEqual(self.saves, [])

    def test_different_value_does_not_confirm(self):
        self.verified_value = 8000.0

        with self.assertRaisesRegex(ValueError, "WRITE_AMBIGUOUS"):
            self.call_apply()

        event = next(iter(self.events.values()))
        self.assertEqual(event["write_status"], "WRITE_AMBIGUOUS")
        self.assertEqual(self.event_counter, 1)
        self.assertEqual(self.saves, [])

    def test_failed_get_is_ambiguous(self):
        self.get_failure = requests.exceptions.ConnectionError("mock")

        with self.assertRaisesRegex(ValueError, "WRITE_AMBIGUOUS"):
            self.call_apply()

        event = next(iter(self.events.values()))
        self.assertEqual(event["write_status"], "WRITE_AMBIGUOUS")
        self.assertEqual(self.event_counter, 1)
        self.assertEqual(self.saves, [])

    def test_get_timeout_is_ambiguous(self):
        self.get_failure = requests.exceptions.Timeout("mock")

        with self.assertRaisesRegex(ValueError, "WRITE_AMBIGUOUS"):
            self.call_apply()

        event = next(iter(self.events.values()))
        self.assertEqual(event["write_status"], "WRITE_AMBIGUOUS")
        self.assertEqual(self.event_counter, 1)
        self.assertEqual(self.saves, [])


if __name__ == "__main__":
    unittest.main()
