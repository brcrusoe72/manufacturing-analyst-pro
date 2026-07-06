from __future__ import annotations

import importlib
import tomllib
import unittest
from pathlib import Path


class PackagingTest(unittest.TestCase):
    def test_agent_skill_package_modules_are_importable(self) -> None:
        for module_name in [
            "agent_skill.agent_wrapper",
            "agent_skill.harness",
            "agent_skill.mcp_tool",
            "agent_skill.remote_mcp_gateway",
            "agent_skill.standalone_agent",
        ]:
            with self.subTest(module_name=module_name):
                module = importlib.import_module(module_name)
                self.assertIsNotNone(module)

    def test_mcp_console_scripts_are_registered(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text())
        scripts = pyproject["project"]["scripts"]

        self.assertEqual(scripts["mfg-mcp-tool"], "agent_skill.mcp_tool:main")
        self.assertEqual(scripts["mfg-mcp-gateway"], "agent_skill.remote_mcp_gateway:main")

    def test_agent_skill_package_is_included_by_setuptools(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text())
        includes = pyproject["tool"]["setuptools"]["packages"]["find"]["include"]

        self.assertIn("agent_skill*", includes)


if __name__ == "__main__":
    unittest.main()