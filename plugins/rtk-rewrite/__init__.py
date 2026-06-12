"""Hermes plugin adapter for RTK command rewriting.

RTK owns the rewrite policy in its ``rtk rewrite`` command. This adapter only
bridges Hermes ``pre_tool_call`` payloads to that command and fails open.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

ACCEPTED_REWRITE_RETURN_CODES = {0, 3}
EXPECTED_PASSTHROUGH_RETURN_CODES = {1, 2}

_rtk_available: bool | None = None
_rtk_missing_warned = False


def register(ctx):
    """Register the Hermes pre-tool callback when RTK exists."""
    if not _check_rtk():
        return

    ctx.register_hook("pre_tool_call", _pre_tool_call)


def reset_state_for_tests() -> None:
    """Reset cached RTK availability for focused plugin tests."""
    global _rtk_available, _rtk_missing_warned
    _rtk_available = None
    _rtk_missing_warned = False


def _check_rtk() -> bool:
    """Return whether the rtk binary is in PATH, warning once when missing."""
    global _rtk_available, _rtk_missing_warned

    if _rtk_available is None:
        _rtk_available = shutil.which("rtk") is not None

    if not _rtk_available and not _rtk_missing_warned:
        _warn("rtk binary not found in PATH; Hermes hook not registered")
        _rtk_missing_warned = True

    return _rtk_available


def _pre_tool_call(tool_name=None, args=None, **_kwargs):
    """Rewrite mutable Hermes terminal command args when RTK returns a change."""
    try:
        if tool_name != "terminal" or not isinstance(args, dict):
            return

        command = args.get("command")
        if not isinstance(command, str) or not command.strip():
            return

        try:
            result = subprocess.run(
                ["rtk", "rewrite", command],
                shell=False,
                timeout=2,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired:
            _warn("rtk rewrite timed out")
            return
        except OSError as exc:
            _warn(f"rtk rewrite unavailable: {exc}")
            return

        if result.returncode not in ACCEPTED_REWRITE_RETURN_CODES:
            if result.returncode not in EXPECTED_PASSTHROUGH_RETURN_CODES:
                details = f"rtk rewrite failed with exit {result.returncode}"
                stderr = result.stderr.strip()
                if stderr:
                    details = f"{details}: {stderr}"
                _warn(details)
            return

        rewritten = result.stdout.strip()
        if rewritten and rewritten != command:
            args["command"] = rewritten
    except Exception as exc:
        _warn(str(exc))
        return


def _warn(message: str) -> None:
    print(f"rtk: hermes plugin warning: {message}", file=sys.stderr)
