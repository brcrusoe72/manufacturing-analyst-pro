"""Compatibility wrapper for repo-local MCP stdio execution.

The installable implementation lives in :mod:`agent_skill.mcp_tool`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_skill import mcp_tool as _impl  # noqa: E402

globals().update({name: getattr(_impl, name) for name in dir(_impl) if not name.startswith("__")})


if __name__ == "__main__":
    main()