import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import oracledb

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "check_environment", ROOT / "scripts" / "check_environment.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CheckEnvironmentTests(unittest.TestCase):
    def run_check(self):
        output = io.StringIO()
        with (
            patch("oracledb.connect", side_effect=AssertionError("Unexpected database connection")),
            patch("oracledb.create_pool", side_effect=AssertionError("Unexpected pool creation")),
            patch("socket.socket.connect", side_effect=AssertionError("Unexpected network access")),
            contextlib.redirect_stdout(output),
        ):
            result = MODULE.main()
        return result, json.loads(output.getvalue())

    def test_installed_environment_passes_without_database(self):
        result, report = self.run_check()
        self.assertEqual(result, 0)
        self.assertTrue(report["ok"])
        self.assertTrue(all(report["checks"].values()))
        self.assertFalse(report["database_connection_tested"])

    def test_python_version_mismatch_fails(self):
        with patch("platform.python_version", return_value="0.0.0"):
            result, report = self.run_check()
        self.assertEqual(result, 1)
        self.assertFalse(report["checks"]["python_version"])

    def test_non_thin_mode_fails(self):
        with patch.object(oracledb, "is_thin_mode", return_value=False):
            result, report = self.run_check()
        self.assertEqual(result, 1)
        self.assertFalse(report["checks"]["thin_mode"])

    def test_wrong_virtualenv_fails(self):
        with patch("sys.prefix", str(ROOT / "not-the-project-venv")):
            result, report = self.run_check()
        self.assertEqual(result, 1)
        self.assertFalse(report["checks"]["project_virtualenv"])


if __name__ == "__main__":
    unittest.main()
