"""R0: reconciliación de huérfanas INTENT_RECORDED. TDD-RED.

Solo lectura + cierre con evidencia sobre la MISMA fila.
Prohibido: PUT (insert_meter_reading), filas nuevas (save_horometer_update),
reintento automático.
"""

import unittest
from unittest.mock import patch

import reconcile


def intent(
    event_id=1,
    old=7595.0,
    new=7915.7,
    key="KEY-1",
    machinery_id=200,
    meter_id=127874,
):
    return {
        "id": event_id,
        "machinery_id": machinery_id,
        "meter_id": meter_id,
        "old_value": old,
        "new_value": new,
        "idempotency_key": key,
    }


MACHINERY = {"id": 200, "serial": "DHKCEBACPJ0021470"}
EQUIPMENT = {"id": 100, "code": "MH12"}


def current_as(value):
    return {
        "meter": {"id": 127874, "serial": "DHKCEBACPJ0021470"},
        "value": value,
    }


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.updates = []
        self.put_calls = []
        self.saved = []

    def run_reconcile(self, rows, current=None, fail_get=False,
                      dry_run=False, machinery=MACHINERY,
                      equipment=EQUIPMENT):
        def fake_get_current(*args, **kwargs):
            if fail_get:
                raise TimeoutError("mock GET timeout")
            return current

        def fake_update(event_id, **kwargs):
            self.updates.append((event_id, kwargs))

        patches = [
            patch.object(
                reconcile, "list_horometer_write_intents",
                return_value=list(rows),
            ),
            patch.object(
                reconcile, "get_machinery_by_id", return_value=machinery
            ),
            patch.object(
                reconcile, "get_equipment_by_serial",
                return_value=equipment,
            ),
            patch.object(
                reconcile, "get_current_hourmeter",
                side_effect=fake_get_current,
            ),
            patch.object(
                reconcile, "update_horometer_write_result",
                side_effect=fake_update,
            ),
            patch.object(
                reconcile, "insert_meter_reading",
                side_effect=lambda **kw: self.put_calls.append(kw),
            ),
            patch.object(
                reconcile, "save_horometer_update",
                side_effect=lambda **kw: self.saved.append(kw),
            ),
        ]
        for item in patches:
            item.start()
        try:
            return reconcile.reconcile_orphan_intents(
                token="t", dry_run=dry_run
            )
        finally:
            for item in reversed(patches):
                item.stop()

    def assert_no_side_writes(self):
        self.assertEqual(self.put_calls, [])
        self.assertEqual(self.saved, [])

    def test_applied_put_closes_verified(self):
        summary = self.run_reconcile(
            [intent()], current=current_as(7915.7)
        )

        self.assertEqual(summary["VERIFIED"], 1)
        event_id, kwargs = self.updates[0]
        self.assertEqual(event_id, 1)
        self.assertEqual(kwargs["write_status"], "VERIFIED")
        self.assertEqual(kwargs["verification_status"], "PASS")
        self.assert_no_side_writes()

    def test_third_value_closes_ambiguous(self):
        summary = self.run_reconcile(
            [intent()], current=current_as(8000.0)
        )

        self.assertEqual(summary["WRITE_AMBIGUOUS"], 1)
        _, kwargs = self.updates[0]
        self.assertEqual(kwargs["write_status"], "WRITE_AMBIGUOUS")
        self.assert_no_side_writes()

    def test_never_applied_closes_terminal_error(self):
        summary = self.run_reconcile(
            [intent()], current=current_as(7595.0)
        )

        self.assertEqual(summary["ERROR"], 1)
        _, kwargs = self.updates[0]
        self.assertEqual(kwargs["write_status"], "ERROR")
        self.assertIn("NOT_APPLIED", kwargs.get("error_code", ""))
        self.assert_no_side_writes()

    def test_missing_meter_closes_error(self):
        summary = self.run_reconcile([intent()], current=None)

        self.assertEqual(summary["ERROR"], 1)
        _, kwargs = self.updates[0]
        self.assertEqual(kwargs["write_status"], "ERROR")
        self.assertIn("NO_VALID_METER", kwargs.get("error_code", ""))
        self.assert_no_side_writes()

    def test_missing_machinery_closes_error(self):
        summary = self.run_reconcile([intent()], machinery=None)

        self.assertEqual(summary["ERROR"], 1)
        _, kwargs = self.updates[0]
        self.assertIn("MACHINERY_NOT_FOUND", kwargs.get("error_code", ""))
        self.assert_no_side_writes()

    def test_missing_equipment_closes_error(self):
        summary = self.run_reconcile([intent()], equipment=None)

        self.assertEqual(summary["ERROR"], 1)
        _, kwargs = self.updates[0]
        self.assertIn("EQUIPMENT_NOT_FOUND", kwargs.get("error_code", ""))
        self.assert_no_side_writes()

    def test_meter_identity_mismatch_never_verifies(self):
        other_meter = {
            "meter": {"id": 999999, "serial": "DHKCEBACPJ0021470"},
            "value": 7915.7,
        }
        summary = self.run_reconcile([intent()], current=other_meter)

        self.assertEqual(summary.get("VERIFIED", 0), 0)
        self.assertEqual(summary["ERROR"], 1)
        _, kwargs = self.updates[0]
        self.assertIn("METER_MISMATCH", kwargs.get("error_code", ""))
        self.assert_no_side_writes()

    def test_meter_id_str_matches_int(self):
        rows = [intent(meter_id="127874")]
        summary = self.run_reconcile(
            rows, current=current_as(7915.7)
        )

        self.assertEqual(summary["VERIFIED"], 1)
        self.assert_no_side_writes()

    def test_get_failure_closes_ambiguous(self):
        summary = self.run_reconcile([intent()], fail_get=True)

        self.assertEqual(summary["WRITE_AMBIGUOUS"], 1)
        self.assert_no_side_writes()

    def test_dry_run_reports_without_writing(self):
        summary = self.run_reconcile(
            [intent()], current=current_as(7915.7), dry_run=True
        )

        self.assertEqual(summary["VERIFIED"], 1)
        self.assertEqual(self.updates, [])
        self.assert_no_side_writes()


if __name__ == "__main__":
    unittest.main()
