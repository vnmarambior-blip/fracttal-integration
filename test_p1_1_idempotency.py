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
    "field_4": "DHKCEBACPJ0021470"
}
METER = {
    "id": 127874,
    "active": True,
    "serial": "DHKCEBACPJ0021470",
    "description": "HOROMETRO",
    "units_code": "HRS",
    "is_counter": True,
    "counter_value": 7595.0,
    "last_data": {"value": 7595.0}
}
MACHINERY = {"id": 200, "serial": "DHKCEBACPJ0021470"}
CONFIG = {"sync_enabled": True, "action_policy": "AUTO"}


class P11IdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.events = {}
        self.put_calls = []
        self.event_counter = 0

        def create_intent(**kwargs):
            self.event_counter += 1
            event_id = self.event_counter
            self.events[kwargs["idempotency_key"]] = {
                "id": event_id,
                "write_status": "INTENT_RECORDED",
                "status": "INTENT_RECORDED"
            }
            return event_id

        def update_result(event_id, **kwargs):
            for event in self.events.values():
                if event["id"] == event_id:
                    event.update(kwargs)
                    return
            raise AssertionError("event not found")

        def fake_insert(**kwargs):
            self.put_calls.append(kwargs)
            return {
                "payload": {
                    "data": {
                        "id_meters_readings": 9000,
                        "is_duplicate": False
                    }
                },
                "http_status": 200
            }

        def fake_current_hourmeter(*args, **kwargs):
            if self.put_calls:
                return {"meter": METER, "value": 7915.7}
            return {"meter": METER, "value": 7595.0}

        self.patches = [
            patch.object(api, "get_equipment_by_serial", return_value=EQUIPMENT),
            patch.object(api, "get_machinery_by_id", return_value=MACHINERY),
            patch.object(api, "get_telemetry_sync_config", return_value=CONFIG),
            patch.object(api, "get_current_hourmeter", side_effect=fake_current_hourmeter),
            patch.object(
                api,
                "get_horometer_update_by_idempotency_key",
                side_effect=lambda key: self.events.get(key)
            ),
            patch.object(api, "create_horometer_write_intent", side_effect=create_intent),
            patch.object(api, "mark_horometer_write_in_progress"),
            patch.object(api, "update_horometer_write_result", side_effect=update_result),
            patch.object(api, "insert_meter_reading", side_effect=fake_insert),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def call_apply(self, value=7915.7, reading_datetime=READING_DATETIME):
        return api.apply_meter_reading(
            token="mock-token",
            code="MH12",
            value=value,
            serial=EQUIPMENT["field_4"],
            reading_datetime=reading_datetime,
            retrieved_at=RETRIEVED_AT,
            decision="UPDATE",
            dry_run=False,
            equipment=EQUIPMENT,
            machinery_id=MACHINERY["id"]
        )

    def test_first_reading_verifies_and_allows_one_put(self):
        result = self.call_apply()
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(len(self.put_calls), 1)

    def test_verified_rerun_is_blocked_without_put(self):
        self.call_apply()
        result = self.call_apply()
        self.assertEqual(result["status"], "ALREADY_PROCESSED")
        self.assertEqual(len(self.put_calls), 1)

    def test_ambiguous_rerun_is_blocked_without_put(self):
        key = api.build_idempotency_key(
            "MYDEVELON", EQUIPMENT["field_4"], METER["id"],
            READING_DATETIME, 7915.7
        )
        self.events[key] = {
            "id": 5,
            "write_status": "WRITE_AMBIGUOUS",
            "status": "WRITE_AMBIGUOUS"
        }
        with self.assertRaisesRegex(ValueError, "REEXECUTION_BLOCKED"):
            self.call_apply()
        self.assertEqual(len(self.put_calls), 0)

    def test_same_value_different_timestamp_has_different_key(self):
        first = api.build_idempotency_key(
            "MYDEVELON", EQUIPMENT["field_4"], METER["id"],
            READING_DATETIME, 7915.7
        )
        second = api.build_idempotency_key(
            "MYDEVELON", EQUIPMENT["field_4"], METER["id"],
            READING_DATETIME.replace(second=17), 7915.7
        )
        self.assertNotEqual(first, second)

    def test_key_conflict_does_not_put_again(self):
        key = api.build_idempotency_key(
            "MYDEVELON", EQUIPMENT["field_4"], METER["id"],
            READING_DATETIME, 7915.7
        )
        self.events[key] = {
            "id": 6,
            "write_status": "INTENT_RECORDED",
            "status": "INTENT_RECORDED"
        }
        with self.assertRaisesRegex(ValueError, "REEXECUTION_BLOCKED"):
            self.call_apply()
        self.assertEqual(len(self.put_calls), 0)

    def test_timeout_marks_ambiguous_and_does_not_retry(self):
        with patch.object(
            api,
            "insert_meter_reading",
            side_effect=requests.exceptions.Timeout("mock timeout")
        ):
            with self.assertRaisesRegex(ValueError, "WRITE_AMBIGUOUS"):
                self.call_apply()

        self.assertEqual(len(self.put_calls), 0)
        event = next(iter(self.events.values()))
        self.assertEqual(event["write_status"], "WRITE_AMBIGUOUS")

    def test_pre_send_error_is_retryable(self):
        with patch.object(
            api,
            "insert_meter_reading",
            side_effect=api.RetryableWriteError("mock preparation failure")
        ):
            with self.assertRaisesRegex(ValueError, "ERROR_RETRYABLE"):
                self.call_apply()

        event = next(iter(self.events.values()))
        self.assertEqual(event["write_status"], "ERROR_RETRYABLE")
        self.assertEqual(len(self.put_calls), 0)

    def test_write_in_progress_rerun_is_blocked(self):
        key = api.build_idempotency_key(
            "MYDEVELON", EQUIPMENT["field_4"], METER["id"],
            READING_DATETIME, 7915.7
        )
        self.events[key] = {
            "id": 7,
            "write_status": "WRITE_IN_PROGRESS",
            "status": "WRITE_IN_PROGRESS"
        }
        with self.assertRaisesRegex(ValueError, "REEXECUTION_BLOCKED"):
            self.call_apply()
        self.assertEqual(len(self.put_calls), 0)

    def test_skip_equal_remains_separate_from_idempotency(self):
        with self.assertRaisesRegex(ValueError, "SKIP_EQUAL"):
            self.call_apply(value=7595.0)
        self.assertEqual(len(self.put_calls), 0)


if __name__ == "__main__":
    unittest.main()
