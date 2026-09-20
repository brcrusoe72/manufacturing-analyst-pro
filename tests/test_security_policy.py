from __future__ import annotations

import os
import io
import tempfile
import unittest

from analyst import security
from analyst import web_loader
from analyst.parsers import smart_parser
from analyst.parsers import utils as parser_utils
from analyst.parsers._compat import ParseError


class SecurityPolicyTest(unittest.TestCase):
    def test_openai_key_requires_explicit_llm_egress(self) -> None:
        old_key = os.environ.get("OPENAI_API_KEY")
        old_global = os.environ.get("MFG_AGENT_ALLOW_LLM_EGRESS")
        old_feature = os.environ.get("MFG_AGENT_ALLOW_LLM_NARRATIVE")
        os.environ["OPENAI_API_KEY"] = "sk-test"
        os.environ.pop("MFG_AGENT_ALLOW_LLM_EGRESS", None)
        os.environ.pop("MFG_AGENT_ALLOW_LLM_NARRATIVE", None)
        try:
            self.assertIsNone(security.get_openai_api_key("narrative"))
            os.environ["MFG_AGENT_ALLOW_LLM_NARRATIVE"] = "1"
            self.assertEqual(security.get_openai_api_key("narrative"), "sk-test")
        finally:
            self._restore_env("OPENAI_API_KEY", old_key)
            self._restore_env("MFG_AGENT_ALLOW_LLM_EGRESS", old_global)
            self._restore_env("MFG_AGENT_ALLOW_LLM_NARRATIVE", old_feature)

    def test_smart_parser_refuses_llm_without_egress_flag(self) -> None:
        old_key = os.environ.get("OPENAI_API_KEY")
        old_flag = os.environ.get("MFG_AGENT_ALLOW_LLM_SMART_PARSER")
        os.environ["OPENAI_API_KEY"] = "sk-test"
        os.environ.pop("MFG_AGENT_ALLOW_LLM_SMART_PARSER", None)
        try:
            with self.assertRaises(ParseError):
                smart_parser._detect_schema(["Started", "Machine", "Minutes"], [["2026-01-01", "Caser", "5"]])
        finally:
            self._restore_env("OPENAI_API_KEY", old_key)
            self._restore_env("MFG_AGENT_ALLOW_LLM_SMART_PARSER", old_flag)

    def test_parser_cache_can_be_disabled(self) -> None:
        old_cache = os.environ.get("MFG_AGENT_CACHE")
        old_dir = os.environ.get("MFG_AGENT_CACHE_DIR")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MFG_AGENT_CACHE"] = "0"
            os.environ["MFG_AGENT_CACHE_DIR"] = tmp
            parser_utils._CACHE_DIR = None
            try:
                path = parser_utils.get_cache_dir() / "cache.json"
                parser_utils.write_cache(path, [{"x": 1}], 1, 123.0)
                self.assertFalse(path.exists())
                self.assertIsNone(parser_utils.read_cache(path, 1))
            finally:
                parser_utils._CACHE_DIR = None
                self._restore_env("MFG_AGENT_CACHE", old_cache)
                self._restore_env("MFG_AGENT_CACHE_DIR", old_dir)

    def test_uploaded_file_size_cap_runs_before_parsing(self) -> None:
        old_limit = os.environ.get("MFG_AGENT_MAX_UPLOAD_BYTES")
        os.environ["MFG_AGENT_MAX_UPLOAD_BYTES"] = "4"
        try:
            with self.assertRaisesRegex(ValueError, "too large"):
                web_loader.load_uploaded_file(io.BytesIO(b"too-large"), "events.csv")
        finally:
            self._restore_env("MFG_AGENT_MAX_UPLOAD_BYTES", old_limit)

    @staticmethod
    def _restore_env(name: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


if __name__ == "__main__":
    unittest.main()