"""Fase 0 / R4 (H1): intención con id válido o fallo explícito.

Sin red, sin SQL real: conexiones mockeadas.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import api
import database


READING_DATETIME = datetime(2026, 9, 15, 15, 25, 16, tzinfo=timezone.utc)
RETRIEVED_AT = datetime(2026, 9, 16, 14, 0, 0, tzinfo=timezone.utc)
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


class FakeCursor:
    def __init__(self, results, rowcount=1):
        self._results = list(results)
        self.rowcount = rowcount
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append(sql)

    def fetchone(self):
        if not self._results:
            return None
        return self._results.pop(0)

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = 0
        self.rolled_back = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        pass


def intent_kwargs():
    return {
        "machinery_id": 200,
        "meter_id": 127874,
        "meter_serial": "DHKCEBACPJ0021470",
        "old_value": 7595.0,
        "new_value": 7915.7,
        "source": "MyDevelon",
        "reading_date": RETRIEVED_AT,
        "idempotency_key": "KEY-1",
        "source_reading_datetime": READING_DATETIME,
        "source_value": 7915.7,
        "decision": "UPDATE",
    }


def reread_row(event_id):
    return tuple([event_id] + [None] * 22)


class CreateIntentTests(unittest.TestCase):
    def run_create(self, results, rowcount=1):
        cursor = FakeCursor(results, rowcount=rowcount)
        connection = FakeConnection(cursor)
        with patch.object(
            database, "get_connection", return_value=connection
        ):
            event_id = database.create_horometer_write_intent(
                **intent_kwargs()
            )
        return event_id, cursor, connection

    def test_happy_path_returns_inserted_id(self):
        event_id, cursor, connection = self.run_create([(42,)])

        self.assertEqual(event_id, 42)
        self.assertEqual(connection.committed, 1)
        inserts = [
            s for s in cursor.statements if "INSERT INTO" in s
        ]
        self.assertEqual(len(inserts), 1)
        self.assertIn("OUTPUT INSERTED", inserts[0])

    def test_none_id_recovers_by_key_without_second_insert(self):
        event_id, cursor, connection = self.run_create(
            [None, reread_row(7)]
        )

        self.assertEqual(event_id, 7)
        inserts = [
            s for s in cursor.statements if "INSERT INTO" in s
        ]
        self.assertEqual(len(inserts), 1)

    def test_none_id_without_row_raises_and_rolls_back(self):
        with self.assertRaises(database.PersistenceError):
            self.run_create([None, None])

    def test_none_id_with_two_rows_raises_and_rolls_back(self):
        with self.assertRaises(database.PersistenceError):
            self.run_create(
                [None, reread_row(7), reread_row(8)]
            )


class MarkInProgressTests(unittest.TestCase):
    def run_mark(self, rowcount):
        cursor = FakeCursor([], rowcount=rowcount)
        connection = FakeConnection(cursor)
        with patch.object(
            database, "get_connection", return_value=connection
        ):
            database.mark_horometer_write_in_progress(42)
        return connection

    def test_rowcount_one_commits(self):
        connection = self.run_mark(rowcount=1)

        self.assertEqual(connection.committed, 1)

    def test_mark_never_nulls_processed_at(self):
        cursor = FakeCursor([], rowcount=1)
        connection = FakeConnection(cursor)
        with patch.object(
            database, "get_connection", return_value=connection
        ):
            database.mark_horometer_write_in_progress(42)

        updates = [s for s in cursor.statements if "UPDATE" in s]
        self.assertEqual(len(updates), 1)
        self.assertNotIn("processed_at", updates[0])

    def test_rowcount_zero_rolls_back_and_raises(self):
        with self.assertRaises(RuntimeError):
            self.run_mark(rowcount=0)


class ApplyGuardTests(unittest.TestCase):
    def test_none_event_id_blocks_put(self):
        put_calls = []
        mark_calls = []

        def fake_current(*args, **kwargs):
            return {
                "meter": METER,
                "value": 7595.0,
                "last_reading_datetime": datetime(
                    2026, 9, 14, 15, 25, 16, tzinfo=timezone.utc
                ),
            }

        def fake_insert(**kwargs):
            put_calls.append(kwargs)
            raise AssertionError("PUT no debe ejecutarse")

        patches = [
            patch.object(
                api, "get_equipment_by_serial", return_value=EQUIPMENT
            ),
            patch.object(
                api, "get_machinery_by_id", return_value=MACHINERY
            ),
            patch.object(
                api,
                "get_telemetry_sync_config",
                return_value=CONFIG,
            ),
            patch.object(
                api, "get_current_hourmeter", side_effect=fake_current
            ),
            patch.object(
                api,
                "get_horometer_update_by_idempotency_key",
                return_value=None,
            ),
            patch.object(
                api, "create_horometer_write_intent", return_value=None
            ),
            patch.object(
                api,
                "mark_horometer_write_in_progress",
                side_effect=lambda eid: mark_calls.append(eid),
            ),
            patch.object(api, "insert_meter_reading", side_effect=fake_insert),
        ]
        for item in patches:
            item.start()
        try:
            with self.assertRaises(database.PersistenceError):
                api.apply_meter_reading(
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
        finally:
            for item in reversed(patches):
                item.stop()

        self.assertEqual(put_calls, [])
        self.assertEqual(mark_calls, [])


if __name__ == "__main__":
    unittest.main()
