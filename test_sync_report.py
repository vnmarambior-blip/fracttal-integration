"""Reporte diario a archivo (--report). Sin red ni SQL real."""

import unittest
from unittest.mock import patch

import run_mydevelon_sync


class SyncReportTests(unittest.TestCase):
    def test_report_file_contains_header_and_results(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            report = str(Path(tmp) / "reporte.log")
            saved = []

            patches = [
                patch.object(
                    run_mydevelon_sync, "get_fracttal_access_token",
                    return_value="t",
                ),
                patch.object(
                    run_mydevelon_sync, "process_equipment",
                    return_value={"status": "SKIP_EQUAL", "serial": "X"},
                ),
                patch.object(
                    run_mydevelon_sync, "save_horometer_update",
                    side_effect=lambda **kw: saved.append(kw),
                    create=True,
                ),
            ]
            for item in patches:
                item.start()
            try:
                run_mydevelon_sync.main(
                    ["--fleet-xml", "mydevelon_fleet_minutes.xml",
                     "--report", report]
                )
            finally:
                for item in reversed(patches):
                    item.stop()

            text = Path(report).read_text(encoding="utf-8")

        self.assertIn("SINCRONIZACIÓN DIARIA", text)
        self.assertIn("Equipos DEVELON recibidos: 25", text)
        self.assertEqual(text.count("[RESULTADO]"), 25)
        self.assertIn("RESUMEN", text)


if __name__ == "__main__":
    unittest.main()
