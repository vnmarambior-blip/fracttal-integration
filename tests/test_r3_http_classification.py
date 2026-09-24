"""R3: 4xx terminal, resto ambiguo salvo pre-envío. Mocks + traducción."""

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

_REAL_INSERT = api.insert_meter_reading


class HttpClassificationTests(unittest.TestCase):
    def setUp(self):
        self.events = {}
        self.put_calls = []
        self.updates = []
        self.saves = []
        self.event_counter = 0
        self.http_status = 500

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
            return {
                "meter": METER,
                "value": 7595.0,
                "last_reading_datetime": datetime(
                    2026, 9, 14, 15, 25, 16, tzinfo=timezone.utc
                ),
            }

        def fake_insert(**kwargs):
            self.put_calls.append(kwargs)
            raise api.FracttalResponseError(
                self.http_status, {"error": "mock"}, "mock http"
            )

        def fake_update(event_id, **kwargs):
            self.updates.append((event_id, kwargs))
            for event in self.events.values():
                if event["id"] == event_id:
                    event.update(kwargs)

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
                api, "save_horometer_update",
                side_effect=lambda **kw: self.saves.append(kw),
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

    def assert_single_event(self, status, expected_http=None):
        event = next(iter(self.events.values()))
        self.assertEqual(event["write_status"], status)
        self.assertEqual(event["status"], status)
        self.assertEqual(self.event_counter, 1)
        self.assertEqual(len(self.put_calls), 1)
        self.assertEqual(self.saves, [])
        update = [
            kw for eid, kw in self.updates if eid == event["id"]
        ]
        self.assertTrue(update)
        if expected_http is None:
            expected_http = self.http_status
        self.assertEqual(update[-1]["http_status"], expected_http)
        return event

    def test_400_is_terminal_error(self):
        self.http_status = 400

        with self.assertRaisesRegex(ValueError, "^ERROR:"):
            self.call_apply()

        event = self.assert_single_event("ERROR")
        self.assertEqual(event["status"], "ERROR")

    def test_404_is_terminal_error(self):
        self.http_status = 404

        with self.assertRaisesRegex(ValueError, "^ERROR:"):
            self.call_apply()

        self.assert_single_event("ERROR")

    def test_422_is_terminal_error(self):
        self.http_status = 422

        with self.assertRaisesRegex(ValueError, "^ERROR:"):
            self.call_apply()

        self.assert_single_event("ERROR")

    def test_408_is_ambiguous(self):
        self.http_status = 408

        with self.assertRaisesRegex(ValueError, "WRITE_AMBIGUOUS"):
            self.call_apply()

        self.assert_single_event("WRITE_AMBIGUOUS")

    def test_429_is_ambiguous(self):
        self.http_status = 429

        with self.assertRaisesRegex(ValueError, "WRITE_AMBIGUOUS"):
            self.call_apply()

        self.assert_single_event("WRITE_AMBIGUOUS")

    def test_500_with_response_is_ambiguous(self):
        self.http_status = 500

        with self.assertRaisesRegex(ValueError, "WRITE_AMBIGUOUS"):
            self.call_apply()

        self.assert_single_event("WRITE_AMBIGUOUS")

    def test_503_with_response_is_ambiguous(self):
        self.http_status = 503

        with self.assertRaisesRegex(ValueError, "WRITE_AMBIGUOUS"):
            self.call_apply()

        self.assert_single_event("WRITE_AMBIGUOUS")

    def test_timeout_keeps_ambiguous(self):
        def timeout_insert(**kwargs):
            self.put_calls.append(kwargs)
            raise requests.exceptions.ConnectTimeout("mock")

        with patch.object(api, "insert_meter_reading",
                          side_effect=timeout_insert):
            with self.assertRaisesRegex(ValueError, "WRITE_AMBIGUOUS"):
                self.call_apply()

        event = next(iter(self.events.values()))
        self.assertEqual(event["write_status"], "WRITE_AMBIGUOUS")
        self.assertEqual(event["status"], "WRITE_AMBIGUOUS")
        self.assertEqual(self.event_counter, 1)
        self.assertEqual(len(self.put_calls), 1)
        self.assertEqual(self.saves, [])
        return event

    def test_translation_from_http_status(self):
        class FakeResponse:
            def __init__(self, status_code):
                self.status_code = status_code
                self.text = '{"ok": false}'

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise requests.exceptions.HTTPError("mock http")

            def json(self):
                return {"ok": False}

        for status_code, expected in ((400, "ERROR"), (500, "WRITE_AMBIGUOUS")):
            self.events.clear()
            self.updates.clear()
            self.put_calls.clear()
            self.event_counter = 0

            def passthrough(**kwargs):
                self.put_calls.append(kwargs)
                return _REAL_INSERT(**kwargs)

            with patch.object(
                api.requests, "put",
                return_value=FakeResponse(status_code),
            ):
                with patch.object(
                    api, "insert_meter_reading", side_effect=passthrough
                ):
                    with self.assertRaises(ValueError):
                        self.call_apply()
            event = next(iter(self.events.values()))
            self.assertEqual(event["write_status"], expected)


if __name__ == "__main__":
    unittest.main()
