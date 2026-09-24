"""R9: normalizador canónico único y decisiones normalizadas."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import api
import reconcile


class CanonicalNormalizerTests(unittest.TestCase):
    def test_float_finite_rounds_2dec(self):
        self.assertEqual(api.normalize_comparison_value(7915.7), 7915.7)
        self.assertEqual(api.normalize_comparison_value(2.675), 2.67)

    def test_numeric_string_matches_float(self):
        self.assertEqual(
            api.normalize_comparison_value("6472.34"),
            api.normalize_comparison_value(6472.34),
        )
        self.assertEqual(api.normalize_comparison_value("9.00"), 9.0)

    def test_none_is_not_normalizable(self):
        self.assertIsNone(api.normalize_comparison_value(None))

    def test_nan_is_not_normalizable(self):
        self.assertIsNone(api.normalize_comparison_value(float("nan")))
        self.assertIsNone(api.normalize_comparison_value("nan"))

    def test_inf_is_not_normalizable(self):
        self.assertIsNone(api.normalize_comparison_value(float("inf")))
        self.assertIsNone(api.normalize_comparison_value("-inf"))

    def test_non_numeric_is_not_normalizable(self):
        self.assertIsNone(api.normalize_comparison_value("N/A"))
        self.assertIsNone(api.normalize_comparison_value(""))

    def test_reconcile_reuses_canonical(self):
        self.assertIs(
            reconcile.normalize_comparison_value,
            api.normalize_comparison_value,
        )


class NormalizedDecisionsTests(unittest.TestCase):
    def test_str_equals_float_is_skip(self):
        self.assertEqual(
            api.validate_hourmeter_update("9.00", 9.0), "SKIP_EQUAL"
        )

    def test_nan_goes_to_review(self):
        self.assertEqual(
            api.validate_hourmeter_update(float("nan"), 5.0),
            "REVIEW_INCONSISTENCY",
        )
        self.assertEqual(
            api.validate_hourmeter_update(5.0, float("nan")),
            "REVIEW_INCONSISTENCY",
        )

    def test_apply_rejects_non_finite(self):
        put_calls = []
        equipment = {"id": 100, "code": "MH12",
                     "field_3": "DX", "field_4": "PIN-1"}
        meter = {"id": 1, "serial": "PIN-1"}

        def fake_current(*args, **kwargs):
            return {"meter": meter, "value": 5.0,
                    "last_reading_datetime": datetime(
                        2026, 9, 14, tzinfo=timezone.utc)}

        patches = [
            patch.object(api, "get_equipment_by_serial",
                         return_value=equipment),
            patch.object(api, "get_machinery_by_id",
                         return_value={"id": 1, "serial": "PIN-1"}),
            patch.object(api, "get_telemetry_sync_config",
                         return_value={"sync_enabled": True,
                                       "action_policy": "AUTO"}),
            patch.object(api, "get_current_hourmeter",
                         side_effect=fake_current),
            patch.object(api, "get_horometer_update_by_idempotency_key",
                         return_value=None),
            patch.object(api, "create_horometer_write_intent",
                         return_value=99),
            patch.object(api, "mark_horometer_write_in_progress"),
            patch.object(api, "update_horometer_write_result"),
            patch.object(api, "insert_meter_reading",
                         side_effect=lambda **kw: put_calls.append(kw)),
        ]
        for item in patches:
            item.start()
        try:
            with self.assertRaises(ValueError):
                api.apply_meter_reading(
                    token="t", code="MH12", value=float("nan"),
                    serial="PIN-1",
                    reading_datetime=datetime(
                        2026, 9, 15, tzinfo=timezone.utc),
                    retrieved_at=datetime(
                        2026, 9, 16, tzinfo=timezone.utc),
                    decision="UPDATE", dry_run=False,
                    equipment=equipment, machinery_id=1,
                )
        finally:
            for item in reversed(patches):
                item.stop()

        self.assertEqual(put_calls, [])


    def test_apply_sub_precision_difference_skips(self):
        put_calls = []
        equipment = {"id": 100, "code": "MH12",
                     "field_3": "DX", "field_4": "PIN-1"}
        meter = {"id": 1, "serial": "PIN-1"}

        def fake_current(*args, **kwargs):
            return {"meter": meter, "value": 7915.70,
                    "last_reading_datetime": datetime(
                        2026, 9, 14, tzinfo=timezone.utc)}

        patches = [
            patch.object(api, "get_equipment_by_serial",
                         return_value=equipment),
            patch.object(api, "get_machinery_by_id",
                         return_value={"id": 1, "serial": "PIN-1"}),
            patch.object(api, "get_telemetry_sync_config",
                         return_value={"sync_enabled": True,
                                       "action_policy": "AUTO"}),
            patch.object(api, "get_current_hourmeter",
                         side_effect=fake_current),
            patch.object(api, "get_horometer_update_by_idempotency_key",
                         return_value=None),
            patch.object(api, "create_horometer_write_intent",
                         return_value=99),
            patch.object(api, "mark_horometer_write_in_progress"),
            patch.object(api, "update_horometer_write_result"),
            patch.object(api, "insert_meter_reading",
                         side_effect=lambda **kw: put_calls.append(kw)),
        ]
        for item in patches:
            item.start()
        try:
            with self.assertRaisesRegex(ValueError, "SKIP_EQUAL"):
                api.apply_meter_reading(
                    token="t", code="MH12", value=7915.6999999,
                    serial="PIN-1",
                    reading_datetime=datetime(
                        2026, 9, 15, tzinfo=timezone.utc),
                    retrieved_at=datetime(
                        2026, 9, 16, tzinfo=timezone.utc),
                    decision="UPDATE", dry_run=False,
                    equipment=equipment, machinery_id=1,
                )
        finally:
            for item in reversed(patches):
                item.stop()

        self.assertEqual(put_calls, [])


if __name__ == "__main__":
    unittest.main()
