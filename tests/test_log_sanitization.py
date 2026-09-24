"""Sanitización de logs: secretos redactados, operación visible."""

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import mydevelon


class FakeResponse:
    def __init__(self):
        self.status_code = 200
        self.headers = {
            "Content-Type": "application/xml",
            "Set-Cookie": "JSESSIONID=super-secreto",
            "Authorization": "Bearer token-secreto",
            "X-Custom": "visible",
        }
        self.text = "<Fleet/>"

    def raise_for_status(self):
        pass


def capture(call):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        call()
    return buffer.getvalue()


class LogSanitizationTests(unittest.TestCase):
    def setUp(self):
        self.getter = patch.object(
            mydevelon.requests, "get", return_value=FakeResponse()
        )
        self.getter.start()

    def tearDown(self):
        self.getter.stop()

    def assert_sanitized(self, out):
        for secret in ("super-secreto", "token-secreto"):
            self.assertNotIn(secret, out)
        self.assertIn("[REDACTED]", out)

    def assert_operational(self, out):
        for visible in ("200", "X-Custom", "visible", "<Fleet/>"):
            self.assertIn(visible, out)

    def test_fleet_response_sanitized(self):
        out = capture(lambda: mydevelon.get_fleet_xml("tok"))

        self.assert_sanitized(out)
        self.assert_operational(out)

    def test_snapshot_response_sanitized(self):
        out = capture(
            lambda: mydevelon.get_equipment_snapshot_xml(
                token="tok", make_code="M", model="O", serial_number="S"
            )
        )

        self.assert_sanitized(out)
        self.assert_operational(out)


if __name__ == "__main__":
    unittest.main()
