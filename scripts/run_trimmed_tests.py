#!/usr/bin/env python3
"""运行 Tangyuge-Hermes 精简版验证 profile。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
COMPILE_TARGETS = (
    "agent",
    "gateway",
    "tools",
    "skills_builtin",
    "scripts",
    "hermes_cli",
    "providers",
    "plugins/model-providers/custom",
    "plugins/image_gen/openai",
    "plugins/model-providers/minimax",
    "plugins/model-providers/deepseek",
    "plugins/rtk-rewrite",
    "tests/trimmed_manifest.py",
    "tests/hermes_cli/test_tangyuge_trimmed_profile.py",
)


def _run(args: list[str]) -> None:
    print("+ " + " ".join(args), flush=True)
    subprocess.run(args, cwd=REPO_ROOT, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Tangyuge-Hermes trimmed verification profile.",
    )
    parser.add_argument(
        "--no-compile",
        action="store_true",
        help="Skip compileall and run only pytest.",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Extra pytest args. Prefix with -- to pass options such as -x.",
    )
    ns = parser.parse_args(argv)

    if not ns.no_compile:
        _run([sys.executable, "-m", "compileall", "-q", *COMPILE_TARGETS])

    from tests.trimmed_manifest import TRIMMED_TEST_TARGETS

    extra = list(ns.pytest_args)
    if extra[:1] == ["--"]:
        extra = extra[1:]
    _run([
        sys.executable,
        "-m",
        "pytest",
        *TRIMMED_TEST_TARGETS,
        "-q",
        "--timeout-method=thread",
        *extra,
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
