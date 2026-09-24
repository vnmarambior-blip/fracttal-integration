"""R15: concurrencia e attempt_count. Sin red ni SQL real."""

import unittest
from unittest.mock import patch

import database


class FakeCursor:
    def __init__(self, reads, rowcount=1, insert_error=None):
        self._reads = list(reads)
        self.rowcount = rowcount
        self._insert_error = insert_error
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append(sql)
        if "INSERT INTO" in sql and self._insert_error is not None:
            raise self._insert_error

    def fetchone(self):
        if not self._reads:
            return None
        return self._reads.pop(0)

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


UNIQUE_ERROR = Exception(
    "Violation of UNIQUE KEY constraint "
    "'UX_horometer_updates_idempotency_key'. "
    "Cannot insert duplicate key."
)


def save_kwargs(key="KEY-R15"):
    return {
        "machinery_id": 200,
        "meter_id": 127874,
        "meter_serial": "DHKCEBACPJ0021470",
        "old_value": 7595.0,
        "new_value": 7915.7,
        "status": "REVIEW",
        "idempotency_key": key,
    }


def run_save(cursor):
    connection = FakeConnection(cursor)
    with patch.object(
        database, "get_connection", return_value=connection
    ):
        result = database.save_horometer_update(**save_kwargs())
    return result, cursor, connection


class ConcurrencyTests(unittest.TestCase):
    def test_normal_creation_inserts_once_and_commits(self):
        result, cursor, connection = run_save(FakeCursor([None]))

        inserts = [s for s in cursor.statements if "INSERT INTO" in s]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(connection.committed, 1)
        self.assertEqual(connection.rolled_back, 0)

    def test_existing_key_short_circuits_without_insert(self):
        result, cursor, connection = run_save(FakeCursor([(9,)]))

        self.assertEqual(result, 9)
        inserts = [s for s in cursor.statements if "INSERT INTO" in s]
        self.assertEqual(len(inserts), 0)

    def test_race_returns_existing_without_aborting(self):
        result, cursor, connection = run_save(
            FakeCursor([None, (9,)], insert_error=UNIQUE_ERROR)
        )

        self.assertEqual(result, 9)
        self.assertEqual(connection.rolled_back, 1)
        inserts = [s for s in cursor.statements if "INSERT INTO" in s]
        self.assertEqual(len(inserts), 1)

    def test_conflict_without_row_raises_idempotency(self):
        with self.assertRaises(database.IdempotencyConflictError):
            run_save(FakeCursor([None, None], insert_error=UNIQUE_ERROR))

    def test_non_unique_error_propagates(self):
        with self.assertRaisesRegex(Exception, "timeout"):
            run_save(
                FakeCursor(
                    [None], insert_error=Exception("timeout")
                )
            )


class AttemptCountTests(unittest.TestCase):
    def run_update(self, rowcount=1):
        cursor = FakeCursor([], rowcount=rowcount)
        connection = FakeConnection(cursor)
        with patch.object(
            database, "get_connection", return_value=connection
        ):
            database.update_horometer_write_result(
                42, status="VERIFIED", write_status="VERIFIED"
            )
        return cursor, connection

    def test_attempt_count_increments_in_sql(self):
        cursor, connection = self.run_update()

        updates = [s for s in cursor.statements if "UPDATE" in s]
        self.assertEqual(len(updates), 1)
        self.assertIn("attempt_count = attempt_count + 1", updates[0])
        self.assertNotIn("attempt_count = ?", updates[0])
        self.assertEqual(connection.committed, 1)


if __name__ == "__main__":
    unittest.main()
