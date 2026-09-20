from __future__ import annotations

import base64
import os
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path("agent-skill").resolve()))
import agent_wrapper  # type: ignore


class AgentWrapperSecurityTest(unittest.TestCase):
    def test_base64_filename_is_sanitized(self) -> None:
        data_dir = agent_wrapper._resolve_data({
            "data_base64": base64.b64encode(b"date,equipment,duration\n").decode("ascii"),
            "filename": "../../plant-data.csv",
        })

        self.assertTrue((data_dir / "plant-data.csv").is_file())
        self.assertFalse((data_dir.parent / "plant-data.csv").exists())

    def test_data_url_rejects_localhost(self) -> None:
        with self.assertRaisesRegex(ValueError, "localhost"):
            agent_wrapper._validate_download_url("http://localhost:8080/data.csv")

    def test_data_url_rejects_non_http_scheme(self) -> None:
        with self.assertRaisesRegex(ValueError, "http or https"):
            agent_wrapper._validate_download_url("file:///etc/hosts")

    def test_base64_rejects_inputs_over_configured_limit(self) -> None:
        old = os.environ.get("MFG_AGENT_MAX_INPUT_BYTES")
        os.environ["MFG_AGENT_MAX_INPUT_BYTES"] = "4"
        try:
            with self.assertRaisesRegex(ValueError, "too large"):
                agent_wrapper._resolve_data({
                    "data_base64": base64.b64encode(b"date,equipment,duration\n").decode("ascii"),
                    "filename": "plant-data.csv",
                })
        finally:
            if old is None:
                os.environ.pop("MFG_AGENT_MAX_INPUT_BYTES", None)
            else:
                os.environ["MFG_AGENT_MAX_INPUT_BYTES"] = old

    def test_base64_rejects_unsupported_filename_extension(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported data file extension"):
            agent_wrapper._resolve_data({
                "data_base64": base64.b64encode(b"hello").decode("ascii"),
                "filename": "plant-data.txt",
            })

    def test_run_analysis_errors_are_sanitized_by_default(self) -> None:
        old_debug = os.environ.get("MFG_AGENT_DEBUG")
        os.environ.pop("MFG_AGENT_DEBUG", None)
        try:
            result = agent_wrapper.run_analysis({"data_file": "/etc/hosts"})
        finally:
            self._restore_env("MFG_AGENT_DEBUG", old_debug)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "path_outside_allowed_roots")
        self.assertNotIn("traceback", result)
        self.assertNotIn("/etc/hosts", result["error"])

    def test_run_analysis_debug_traceback_is_opt_in(self) -> None:
        old_debug = os.environ.get("MFG_AGENT_DEBUG")
        os.environ["MFG_AGENT_DEBUG"] = "1"
        try:
            result = agent_wrapper.run_analysis({"data_file": "/etc/hosts"})
        finally:
            self._restore_env("MFG_AGENT_DEBUG", old_debug)

        self.assertEqual(result["status"], "error")
        self.assertIn("debug", result)
        self.assertIn("Traceback", result["debug"])

    def test_explicit_data_roots_do_not_implicitly_allow_project_root(self) -> None:
        sample = Path("samples/line_review_short_stops.csv").resolve()
        old_roots = os.environ.get("MFG_AGENT_ALLOWED_ROOTS")
        os.environ["MFG_AGENT_ALLOWED_ROOTS"] = "/nonexistent"
        try:
            with self.assertRaisesRegex(ValueError, "allowed read root"):
                agent_wrapper._resolve_data({"data_file": str(sample)})
        finally:
            self._restore_env("MFG_AGENT_ALLOWED_ROOTS", old_roots)

    @staticmethod
    def _restore_env(name: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


if __name__ == "__main__":
    unittest.main()