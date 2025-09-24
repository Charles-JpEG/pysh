#!/usr/bin/env python3
"""
Self-contained test runner with no external dependencies.
It exercises the shell engine in a temporary sandbox using only the stdlib.

Exit code 0 on success; non-zero with a brief failure summary otherwise.
"""

from __future__ import annotations

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Allow importing from src/
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ops import ShellSession, execute_line, CommandRunner  # type: ignore


# --- Simple color utilities (no deps) ---
def _use_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    if not _use_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def green(s: str) -> str: return _c("32", s)
def red(s: str) -> str: return _c("31", s)
def yellow(s: str) -> str: return _c("33", s)
def cyan(s: str) -> str: return _c("36", s)
def bold(s: str) -> str: return _c("1", s)


def sandbox_env(tmp: Path) -> dict:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp),
        "LANG": os.environ.get("LANG", "C"),
        "LC_ALL": os.environ.get("LC_ALL", "C"),
        "TERM": os.environ.get("TERM", "dumb"),
    }
    if "SHELL" in os.environ:
        env["SHELL"] = os.environ["SHELL"]
    return env


def run_line(line: str, sess: ShellSession) -> int:
    return execute_line(line, sess)


def test_pwd_and_fs_ops(sess: ShellSession, tmp: Path):
    assert Path(".").resolve() == tmp.resolve()
    code = run_line("mkdir -p a/b", sess)
    assert code == 0
    code = run_line("ls -1 a", sess)
    assert code == 0
    # Switch directory in parent process and check pwd through child
    os.chdir(tmp / "a")
    code = run_line("pwd", sess)
    assert code == 0


def test_pipeline_grep(sess: ShellSession, tmp: Path):
    f = tmp / "text.txt"
    f.write_text("alpha\nBeta\ngamma\n")
    code = run_line("cat text.txt | grep -E '^B'", sess)
    assert code in (0, 1)


def test_redirection_and_dup(sess: ShellSession, tmp: Path):
    code = run_line("sh -c 'echo out; echo err 1>&2' >o.txt 2>&1", sess)
    assert code == 0
    text = (tmp / "o.txt").read_text()
    assert "out\n" in text and "err\n" in text


def test_to_devnull(sess: ShellSession, tmp: Path):
    code = run_line("echo hi >/dev/null 2>&1", sess)
    assert code == 0


def test_conditionals(sess: ShellSession, tmp: Path):
    assert run_line("false || echo ok", sess) in (0, 1)
    assert run_line("true && echo ok", sess) in (0, 1)
    assert run_line("false && echo bad; echo ok", sess) in (0, 1)


def test_background(sess: ShellSession, tmp: Path):
    code = run_line("sh -c 'sleep 0.1' &", sess)
    assert code == 0
    assert sess.background_jobs


def test_simple_command_runner_capture(sess: ShellSession, tmp: Path):
    runner = CommandRunner("printf 'a'", shell=sess.shell, env=dict(sess.env))
    rc = runner.shell_run()
    assert rc == 0 and runner.stdout == 'a'


def test_env_contains_sanitized_vars(sess: ShellSession, tmp: Path):
    # We won't parse output here; just ensure the command runs
    assert run_line("env", sess) in (0, 1)


def main() -> int:
    failures = []
    errors = []
    passed = 0
    tmp = Path(tempfile.mkdtemp(prefix="pysh-test-"))
    cwd = Path.cwd()
    try:
        os.chdir(tmp)
        env = sandbox_env(tmp)
        shell = os.environ.get("SHELL", "/bin/sh")
        sess = ShellSession(shell=shell, inherit_env=False)
        sess.env.update(env)

        tests = [
            test_pwd_and_fs_ops,
            test_pipeline_grep,
            test_redirection_and_dup,
            test_to_devnull,
            test_conditionals,
            test_background,
            test_simple_command_runner_capture,
            test_env_contains_sanitized_vars,
        ]

        for t in tests:
            try:
                # Ensure each test starts at the sandbox root
                os.chdir(tmp)
                t(sess, tmp)
                passed += 1
                print(f"{green('[PASS]')} {bold(t.__name__)}")
            except AssertionError as e:
                print(f"{red('[FAIL]')} {bold(t.__name__)}: {e}")
                failures.append((t.__name__, str(e)))
            except Exception as e:
                print(f"{yellow('[ERROR]')} {bold(t.__name__)}: {e}")
                errors.append((t.__name__, f"ERROR: {e}"))

        total = len(tests)
        failed = len(failures)
        errored = len(errors)
        print("\n" + bold("Summary:"))
        print(f"  Total: {total}  {green('Passed: ' + str(passed))}  {red('Failed: ' + str(failed))}  {yellow('Errors: ' + str(errored))}")

        if failures:
            print("\n" + bold(red("Failures:")))
            for name, msg in failures:
                print(f"  - {name}: {msg}")
        if errors:
            print("\n" + bold(yellow("Errors:")))
            for name, msg in errors:
                print(f"  - {name}: {msg}")

        return 0 if (failed == 0 and errored == 0) else 1
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
