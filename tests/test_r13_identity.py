"""R13: sin remapeo silencioso por equipment_code. Mocks."""

import unittest
from unittest.mock import patch

import database


class FakeCursor:
    def __init__(self, reads):
        self._reads = list(reads)
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))

    def fetchone(self):
        if not self._reads:
            return None
        return self._reads.pop(0)

    def fetchall(self):
        return []

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


def run_upsert(reads, serial="NEWPIN", code="MH99"):
    cursor = FakeCursor(reads)
    connection = FakeConnection(cursor)
    with patch.object(
        database, "get_connection", return_value=connection
    ), patch.object(
        database, "get_machinery_by_serial",
        return_value={"id": 7, "serial": serial},
    ):
        result = database.upsert_machinery(
            serial=serial, equipment_code=code
        )
    return result, cursor, connection


def updates_of(cursor):
    return [(s, p) for s, p in cursor.statements
            if "UPDATE machinery" in s]


class IdentityTests(unittest.TestCase):
    def test_same_serial_updates_attrs(self):
        result, cursor, connection = run_upsert(
            [(7,)], serial="PIN-A", code="MH12"
        )

        self.assertEqual(result["serial"], "PIN-A")
        self.assertEqual(len(updates_of(cursor)), 1)
        self.assertEqual(connection.committed, 1)

    def test_code_match_other_serial_blocks(self):
        with self.assertRaises(database.IdentityConflictError):
            run_upsert([None, (7, "OLDPIN")],
                       serial="NEWPIN", code="MH99")

    def test_blocked_remap_writes_nothing(self):
        cursor = FakeCursor([None, (7, "OLDPIN")])
        connection = FakeConnection(cursor)
        with patch.object(
            database, "get_connection", return_value=connection
        ), patch.object(
            database, "get_machinery_by_serial",
            return_value={"id": 7, "serial": "NEWPIN"},
        ):
            try:
                database.upsert_machinery(
                    serial="NEWPIN", equipment_code="MH99"
                )
            except database.IdentityConflictError:
                pass

        self.assertEqual(updates_of(cursor), [])
        self.assertEqual(connection.committed, 0)

    def test_conflict_message_preserves_evidence(self):
        try:
            run_upsert([None, (7, "OLDPIN")],
                       serial="NEWPIN", code="MH99")
            self.fail("debió lanzar")
        except database.IdentityConflictError as error:
            text = str(error)
            self.assertIn("OLDPIN", text)
            self.assertIn("NEWPIN", text)
            self.assertIn("MH99", text)

    def test_blank_old_serial_is_filled_not_remapped(self):
        result, cursor, connection = run_upsert(
            [None, (7, None)], serial="NEWPIN", code="MH99"
        )

        self.assertEqual(len(updates_of(cursor)), 1)
        params = updates_of(cursor)[0][1]
        self.assertIn("NEWPIN", params)

    def test_unknown_identity_inserts_once(self):
        cursor = FakeCursor([None, None])
        connection = FakeConnection(cursor)
        with patch.object(
            database, "get_connection", return_value=connection
        ), patch.object(
            database, "get_machinery_by_serial",
            return_value={"id": 9, "serial": "NEWPIN"},
        ):
            database.upsert_machinery(
                serial="NEWPIN", equipment_code="MH99"
            )

        inserts = [s for s, _ in cursor.statements
                   if "INSERT INTO" in s]
        self.assertEqual(len(inserts), 1)


if __name__ == "__main__":
    unittest.main()
