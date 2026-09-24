"""R10: política temporal de tres ramas, sin flags muertos."""

import unittest
from datetime import datetime, timezone
from pathlib import Path

import api


def dt(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


class TemporalPolicyTests(unittest.TestCase):
    def test_newer_means_update_candidate(self):
        self.assertIsNone(
            api.validate_reading_is_newer(dt(2026, 9, 23), dt(2026, 9, 22))
        )
        self.assertEqual(
            api.validate_hourmeter_update(6466.0, 6472.34), "UPDATE"
        )

    def test_equal_datetime_means_skip(self):
        moment = dt(2026, 9, 22)
        self.assertEqual(
            api.validate_reading_is_newer(moment, moment), "SKIP_EQUAL"
        )

    def test_older_means_review_old_source(self):
        self.assertEqual(
            api.validate_reading_is_newer(dt(2022, 11, 30), dt(2026, 7, 13)),
            "REVIEW_OLD_SOURCE",
        )

    def test_no_dead_age_flags_in_write_path(self):
        self.assertFalse(hasattr(api, "MAX_SOURCE_AGE_HOURS"))
        self.assertFalse(hasattr(api, "ALLOW_OLD_SOURCE_UPDATES"))

    def test_no_dead_flag_in_env_example(self):
        text = Path(".env.example").read_text(encoding="utf-8")
        self.assertNotIn("ALLOW_OLD_SOURCE_UPDATES", text)
        self.assertNotIn("MAX_SOURCE_AGE_HOURS", text)

    def test_no_dead_age_flags_in_audit_module(self):
        import audit_mydevelon_fleet

        self.assertFalse(hasattr(audit_mydevelon_fleet, "MAX_SOURCE_AGE_HOURS"))
        self.assertFalse(
            hasattr(audit_mydevelon_fleet, "ALLOW_OLD_SOURCE_UPDATES")
        )

    def test_old_but_ordered_reading_updates(self):
        import audit_mydevelon_fleet
        from datetime import timedelta

        old = datetime.now(timezone.utc) - timedelta(hours=100)
        self.assertEqual(
            audit_mydevelon_fleet.decide_action(200.0, old, 100.0),
            "UPDATE",
        )


if __name__ == "__main__":
    unittest.main()
