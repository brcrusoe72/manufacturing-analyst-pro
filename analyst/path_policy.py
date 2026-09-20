"""Shared filesystem boundary policy for public agent entry points."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


READ_ROOT_ENV = "MFG_AGENT_ALLOWED_ROOTS"
DATA_ROOT_ENV = "MFG_AGENT_DATA_ROOTS"
BEHAVIOR_ROOT_ENV = "MFG_AGENT_BEHAVIOR_ROOTS"
WORKSPACE_ROOT_ENV = "MFG_AGENT_WORKSPACE_ROOTS"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_read_roots(roots: list[str | Path] | None = None) -> list[Path]:
    """Resolve roots allowed for caller-supplied plant-data read paths.

    `MFG_AGENT_ALLOWED_ROOTS` is kept as the legacy env name. New deployments
    should prefer `MFG_AGENT_DATA_ROOTS`. When an operator sets either env var,
    the project root is no longer appended implicitly.
    """
    return resolve_data_roots(roots)


def resolve_data_roots(roots: list[str | Path] | None = None) -> list[Path]:
    """Resolve roots allowed for caller-supplied plant-data read paths."""
    return _resolve_roots(roots, [DATA_ROOT_ENV, READ_ROOT_ENV], [project_root(), Path.cwd()])


def resolve_behavior_roots(roots: list[str | Path] | None = None) -> list[Path]:
    """Resolve roots allowed for behavior markdown files."""
    return _resolve_roots(roots, [BEHAVIOR_ROOT_ENV], [project_root(), Path.cwd()])


def resolve_workspace_roots(roots: list[str | Path] | None = None) -> list[Path]:
    """Resolve roots allowed for caller-supplied workspace/output paths."""
    return _resolve_roots(roots, [WORKSPACE_ROOT_ENV], [Path.cwd(), Path(tempfile.gettempdir())])


def resolve_read_path(
    path: str | Path,
    *,
    purpose: str,
    roots: list[Path] | None = None,
    require_exists: bool = False,
) -> Path:
    """Resolve a caller-controlled read path and fail closed outside roots."""
    target = Path(path).expanduser().resolve()
    allowed = roots or resolve_read_roots()
    if not is_relative_to_any(target, allowed):
        raise ValueError(f"{purpose} must be under an allowed read root: {_format_roots(allowed)}")
    if require_exists and not target.exists():
        raise FileNotFoundError(f"{purpose} not found: {target}")
    return target


def resolve_behavior_path(
    path: str | Path,
    *,
    purpose: str,
    roots: list[Path] | None = None,
    require_exists: bool = False,
) -> Path:
    target = Path(path).expanduser().resolve()
    allowed = roots or resolve_behavior_roots()
    if not is_relative_to_any(target, allowed):
        raise ValueError(f"{purpose} must be under an allowed behavior root: {_format_roots(allowed)}")
    if require_exists and not target.exists():
        raise FileNotFoundError(f"{purpose} not found: {target}")
    return target


def resolve_optional_read_path(
    path: str | Path | None,
    *,
    purpose: str,
    roots: list[Path] | None = None,
    require_exists: bool = False,
) -> Path | None:
    if path in (None, ""):
        return None
    return resolve_read_path(path, purpose=purpose, roots=roots, require_exists=require_exists)


def resolve_workspace_path(
    path: str | Path,
    *,
    purpose: str,
    roots: list[Path] | None = None,
) -> Path:
    """Resolve a caller-controlled write/workspace path and fail closed outside roots."""
    target = Path(path).expanduser().resolve()
    allowed = roots or resolve_workspace_roots()
    if not is_relative_to_any(target, allowed):
        raise ValueError(f"{purpose} must be under an allowed workspace root: {_format_roots(allowed)}")
    return target


def safe_filename(name: str, *, default: str = "artifact") -> str:
    keep = []
    for char in Path(name).name:
        keep.append(char if char.isalnum() or char in {".", "-", "_"} else "_")
    safe = "".join(keep).strip("._")
    return safe or default


def is_relative_to_any(path: Path, roots: list[Path]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


def _resolve_roots(roots: list[str | Path] | None, env_names: list[str], defaults: list[Path]) -> list[Path]:
    raw_roots: list[str | Path] = list(roots or [])
    for env_name in env_names:
        env_value = os.environ.get(env_name)
        if env_value:
            raw_roots.extend(part for part in env_value.split(os.pathsep) if part.strip())
    if not raw_roots:
        raw_roots = defaults
    return [Path(root).expanduser().resolve() for root in raw_roots]


def _format_roots(roots: list[Path]) -> str:
    return ", ".join(str(root) for root in roots)