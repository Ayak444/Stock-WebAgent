"""Offline syntax and unit-test quality gate for the repository."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT_ALLOWLIST = {
    "APPDATA",
    "CI",
    "COMSPEC",
    "GITHUB_ACTIONS",
    "GITHUB_BASE_REF",
    "GITHUB_HEAD_REF",
    "GITHUB_REF",
    "GITHUB_REF_NAME",
    "GITHUB_REPOSITORY",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_NUMBER",
    "GITHUB_SHA",
    "GITHUB_WORKSPACE",
    "HOME",
    "LANG",
    "LC_ALL",
    "LD_LIBRARY_PATH",
    "LOCALAPPDATA",
    "NUMBER_OF_PROCESSORS",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "PYTHONHOME",
    "PYTHONPATH",
    "RUNNER_ARCH",
    "RUNNER_OS",
    "RUNNER_TEMP",
    "RUNNER_TOOL_CACHE",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "TMPDIR",
    "TZ",
    "USERPROFILE",
    "VIRTUAL_ENV",
    "WINDIR",
}


def python_files() -> list[Path]:
    """Return tracked and unignored untracked Python sources reported by Git."""
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "*.py",
        ],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        detail = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"git ls-files failed: {detail}")
    return sorted(
        ROOT / os.fsdecode(entry)
        for entry in result.stdout.split(b"\0")
        if entry
    )


def build_test_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build a minimal child environment without inherited credentials."""
    source = os.environ if source is None else source
    environment = {
        key: source[key]
        for key in ENVIRONMENT_ALLOWLIST
        if key in source
    }
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHON_DOTENV_DISABLED": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return environment


def compile_sources() -> bool:
    """Compile sources in memory so the gate leaves no bytecode artifacts."""
    failures: list[tuple[Path, BaseException]] = []
    try:
        sources = python_files()
    except RuntimeError as exc:
        print(f"Python source discovery failed: {exc}", file=sys.stderr)
        return False

    for path in sources:
        try:
            source = path.read_text(encoding="utf-8-sig")
            compile(source, str(path.relative_to(ROOT)), "exec")
        except (OSError, SyntaxError, UnicodeError) as exc:
            failures.append((path, exc))

    if failures:
        print("Python compile check failed:", file=sys.stderr)
        for path, exc in failures:
            print(f"- {path.relative_to(ROOT)}: {exc}", file=sys.stderr)
        return False

    print(f"Python compile check passed ({len(sources)} files).", flush=True)
    return True


def run_unit_tests() -> int:
    """Run unittest discovery inside the offline runner."""
    command = [
        sys.executable,
        "-m",
        "scripts.offline_unittest",
        "discover",
        "-s",
        "tests",
        "-v",
    ]
    print(f"Running: {' '.join(command)}", flush=True)
    return subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        env=build_test_environment(),
    ).returncode


def main() -> int:
    if not compile_sources():
        return 1
    return run_unit_tests()


if __name__ == "__main__":
    raise SystemExit(main())
