"""Shared security, privacy, and external-error helpers."""
from __future__ import annotations

import os
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEBUG_ENV = "MFG_AGENT_DEBUG"
LLM_EGRESS_ENV = "MFG_AGENT_ALLOW_LLM_EGRESS"
KEY_DISCOVERY_ENV = "MFG_AGENT_ALLOW_KEY_DISCOVERY"
LLM_CACHE_ENV = "MFG_AGENT_LLM_CACHE"
PARSER_CACHE_ENV = "MFG_AGENT_CACHE"


@dataclass(slots=True)
class ExternalError:
    code: str
    message: str
    debug: str | None = None

    def to_dict(self) -> dict[str, str]:
        payload = {"error_code": self.code, "error": self.message}
        if self.debug:
            payload["debug"] = self.debug
        return payload

    def to_text(self) -> str:
        return f"Error [{self.code}]: {self.message}"


def env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def debug_enabled() -> bool:
    return env_flag(DEBUG_ENV)


def parser_cache_enabled() -> bool:
    return env_flag(PARSER_CACHE_ENV, default=True)


def llm_cache_enabled() -> bool:
    return env_flag(LLM_CACHE_ENV, default=True)


def llm_egress_allowed(feature: str) -> bool:
    feature_env = f"MFG_AGENT_ALLOW_LLM_{feature.upper().replace('-', '_')}"
    return env_flag(LLM_EGRESS_ENV) or env_flag(feature_env)


def get_openai_api_key(feature: str) -> str | None:
    """Return an OpenAI key only when egress is explicitly enabled."""
    if not llm_egress_allowed(feature):
        return None

    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key.strip()

    if not env_flag(KEY_DISCOVERY_ENV):
        return None

    for path in [
        Path.home() / ".openclaw" / "auth" / "openai",
        Path.home() / ".openclaw" / ".env",
        Path.home() / ".bashrc",
    ]:
        if not path.is_file():
            continue
        text = path.read_text().strip()
        for line in text.splitlines():
            if "OPENAI_API_KEY=" in line:
                return line.split("OPENAI_API_KEY=", 1)[1].strip().strip('"').strip("'").strip()
        if text.startswith("sk-"):
            return text
    return None


def external_error(exc: BaseException, *, default_code: str = "internal_error") -> ExternalError:
    code, message = _classify_error(exc, default_code=default_code)
    debug = traceback.format_exc() if debug_enabled() else None
    return ExternalError(code=code, message=message, debug=debug)


def external_error_payload(exc: BaseException, *, default_code: str = "internal_error") -> dict[str, Any]:
    return {"status": "error", **external_error(exc, default_code=default_code).to_dict()}


def require_args(args: dict[str, Any], *names: str) -> None:
    for name in names:
        if name not in args or args[name] in (None, ""):
            raise ValueError(f"missing required argument: {name}")


def _classify_error(exc: BaseException, *, default_code: str) -> tuple[str, str]:
    if isinstance(exc, KeyError):
        key = str(exc).strip("'\"") or "argument"
        return "missing_required_argument", f"Missing required argument: {key}."

    text = str(exc)
    lowered = text.lower()
    if "missing required argument:" in lowered:
        name = text.split(":", 1)[1].strip() if ":" in text else "argument"
        return "missing_required_argument", f"Missing required argument: {name}."
    if "allowed read root" in lowered:
        return "path_outside_allowed_roots", "Input path is outside the configured data roots."
    if "allowed workspace root" in lowered:
        return "path_outside_workspace_roots", "Output path is outside the configured workspace roots."
    if "not found" in lowered and isinstance(exc, FileNotFoundError):
        return "not_found", "Required input was not found."
    if "too large" in lowered:
        return "input_too_large", "Input exceeds the configured size limit."
    if "unsupported data file extension" in lowered:
        return "unsupported_file_type", "Unsupported data file type."
    if "data_url" in lowered and ("localhost" in lowered or "private" in lowered or "local network" in lowered):
        return "blocked_url", "URL targets a blocked host or network range."
    if "data_url must use http or https" in lowered:
        return "blocked_url", "URL must use http or https."
    if "no parseable" in lowered:
        return "parse_failed", "No parseable production data was found."

    if isinstance(exc, ValueError):
        return "invalid_request", "Invalid request."

    return default_code, "Internal error."