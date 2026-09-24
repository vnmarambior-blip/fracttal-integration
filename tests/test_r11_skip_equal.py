"""R11: SKIP_EQUAL solo con fecha igual Y valor normalizado igual."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import api


SERIAL = "DHKCEBACPJ0021470"
MOMENT = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
EQUIPMENT = {"id": 100, "code": "MH12", "field_4": SERIAL}
CLASSIF = {
    "asset_type": "A",
    "group_1": "G1",
    "group_2": "G2",
    "classified": True,
}
CONFIG = {"sync_enabled": True, "action_policy": "AUTO"}


def current_result(value):
    return {
        "meter": {"id": 127874, "serial": SERIAL},
        "value": value,
        "last_reading_datetime": MOMENT,
    }


class SkipEqualSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.saved = []
        self.current_value = 100.0

    def call_process(self, new_value):
        patches = [
            patch.object(api, "get_equipment_by_serial",
                         return_value=EQUIPMENT),
            patch.object(api, "get_asset_type", return_value=CLASSIF),
            patch.object(api, "upsert_machinery",
                         return_value={"id": 200}),
            patch.object(api, "get_telemetry_sync_config",
                         return_value=CONFIG),
            patch.object(api, "get_current_hourmeter",
                         return_value=current_result(self.current_value)),
            patch.object(api, "save_horometer_update",
                         side_effect=lambda **kw: self.saved.append(kw)),
        ]
        for item in patches:
            item.start()
        try:
            return api.process_equipment(
                token="t", serial=SERIAL, new_value=new_value,
                dry_run=True, reading_datetime=MOMENT,
                retrieved_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
            )
        finally:
            for item in reversed(patches):
                item.stop()

    def test_same_date_same_value_is_skip(self):
        result = self.call_process(100.0)

        self.assertEqual(result["status"], "SKIP_EQUAL")
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0]["decision"], "SKIP_EQUAL")

    def test_same_date_normalized_difference_is_update(self):
        result = self.call_process(105.0)

        self.assertEqual(result["status"], "WOULD_UPDATE")
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0]["status"], "WOULD_UPDATE")

    def test_same_date_str_vs_float_is_skip(self):
        self.current_value = "9.00"
        result = self.call_process(9.0)

        self.assertEqual(result["status"], "SKIP_EQUAL")
        self.assertEqual(len(self.saved), 1)

    def test_same_date_sub_precision_is_skip(self):
        self.current_value = 100.0
        result = self.call_process(100.004)

        self.assertEqual(result["status"], "SKIP_EQUAL")
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0]["decision"], "SKIP_EQUAL")

    def test_old_date_same_value_is_not_skip(self):
        with patch.object(api, "get_current_hourmeter",
                          return_value=current_result(50.0)):
            patches = [
                patch.object(api, "get_equipment_by_serial",
                             return_value=EQUIPMENT),
                patch.object(api, "get_asset_type", return_value=CLASSIF),
                patch.object(api, "upsert_machinery",
                             return_value={"id": 200}),
                patch.object(api, "get_telemetry_sync_config",
                             return_value=CONFIG),
                patch.object(api, "save_horometer_update",
                             side_effect=lambda **kw: self.saved.append(kw)),
            ]
            for item in patches:
                item.start()
            try:
                result = api.process_equipment(
                    token="t", serial=SERIAL, new_value=50.0,
                    dry_run=True,
                    reading_datetime=datetime(
                        2022, 11, 30, tzinfo=timezone.utc),
                    retrieved_at=datetime(
                        2026, 9, 23, tzinfo=timezone.utc),
                )
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertNotEqual(result["status"], "SKIP_EQUAL")
        self.assertEqual(
            self.saved[0]["decision"], "REVIEW_OLD_SOURCE"
        )

    def test_old_date_different_value_review(self):
        with patch.object(api, "get_current_hourmeter",
                          return_value=current_result(4318.0)):
            patches = [
                patch.object(api, "get_equipment_by_serial",
                             return_value=EQUIPMENT),
                patch.object(api, "get_asset_type", return_value=CLASSIF),
                patch.object(api, "upsert_machinery",
                             return_value={"id": 200}),
                patch.object(api, "get_telemetry_sync_config",
                             return_value=CONFIG),
                patch.object(api, "save_horometer_update",
                             side_effect=lambda **kw: self.saved.append(kw)),
            ]
            for item in patches:
                item.start()
            try:
                result = api.process_equipment(
                    token="t", serial=SERIAL, new_value=1437.67,
                    dry_run=True,
                    reading_datetime=datetime(
                        2022, 11, 30, tzinfo=timezone.utc),
                    retrieved_at=datetime(
                        2026, 9, 23, tzinfo=timezone.utc),
                )
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertNotEqual(result["status"], "SKIP_EQUAL")
        self.assertEqual(
            self.saved[0]["decision"], "REVIEW_OLD_SOURCE"
        )

    def test_non_normalizable_never_skip(self):
        # "N/A" no puede construir key (float falla antes del gate
        # temporal): nunca termina en SKIP, pero levanta en voz alta.
        # El flujo real lo filtra antes (parse → ERROR_SOURCE_HOURS).
        with self.assertRaises(ValueError):
            self.call_process("N/A")

        self.assertEqual(
            [row["status"] for row in self.saved
             if row.get("status") == "SKIP_EQUAL"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
