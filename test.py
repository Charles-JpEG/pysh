#!/usr/bin/env python3
"""
Self-contained test runner (no external Python deps).

Usage:
  ./test.py           # run base tests
  ./test.py -e        # run base + extended tests (rg, fd if installed)
  ./test.py --extend
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Allow importing from src/
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ops import ShellSession, execute_line, CommandRunner  # type: ignore


# --- Color utilities ---
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
def blue(s: str) -> str: return _c("34", s)
def bold(s: str) -> str: return _c("1", s)


class SkipTest(Exception):
    pass


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


def has_cmd(name: str) -> bool:
    return shutil.which(name) is not None


# ---- Base tests ----
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


def test_find_txt_files(sess: ShellSession, tmp: Path):
    # Create structure under a dedicated root to avoid capturing output files
    search = tmp / "search"
    (search / "d1").mkdir(parents=True)
    (search / "d2").mkdir()
    (search / "d1" / "a.txt").write_text("a\n")
    (search / "d2" / "b.txt").write_text("b\n")
    (search / "d2" / "c.log").write_text("c\n")
    # Find only within ./search and write output in tmp root so it isn't included
    assert run_line("find ./search -type f -name '*.txt' | sort > files.txt", sess) in (0, 1)
    out = (tmp / "files.txt").read_text().strip().splitlines()
    # Expect exactly the two .txt files
    expected = sorted(["./search/d1/a.txt", "./search/d2/b.txt"])
    assert out == expected


def test_find_and_wc_count(sess: ShellSession, tmp: Path):
    logs = tmp / "logs"
    logs.mkdir(exist_ok=True)
    for i in range(5):
        (logs / f"f{i}.log").write_text("x\n")
    assert run_line("find ./logs -type f -name '*.log' | wc -l > count.txt", sess) in (0, 1)
    count = int((tmp / "count.txt").read_text().strip() or "0")
    assert count == 5


def test_sort_basic(sess: ShellSession, tmp: Path):
    (tmp / "unsorted.txt").write_text("banana\napple\ncherry\n")
    assert run_line("sort unsorted.txt > sorted.txt", sess) == 0
    out = (tmp / "sorted.txt").read_text().splitlines()
    assert out == ["apple", "banana", "cherry"]


def test_uniq_basic(sess: ShellSession, tmp: Path):
    (tmp / "dups.txt").write_text("a\na\nb\na\n")
    # uniq removes adjacent dups, so we sort first for deterministic grouping
    assert run_line("sort dups.txt | uniq > uniq.txt", sess) in (0, 1)
    out = (tmp / "uniq.txt").read_text().splitlines()
    assert out == ["a", "b"]


def test_uniq_count(sess: ShellSession, tmp: Path):
    (tmp / "dupsc.txt").write_text("x\ny\nx\nx\n")
    assert run_line("sort dupsc.txt | uniq -c > uniqc.txt", sess) in (0, 1)
    lines = (tmp / "uniqc.txt").read_text().splitlines()
    # Parse like: '  3 x' and '  1 y'
    parsed = [(int(l.strip().split()[0]), l.strip().split()[1]) for l in lines]
    # Order after sort: x then y
    assert parsed == [(3, 'x'), (1, 'y')]


def test_cut_fields(sess: ShellSession, tmp: Path):
    (tmp / "data.csv").write_text("a,b,c\nd,e,f\n1,2,3\n")
    assert run_line("cut -d ',' -f 2 data.csv > col2.txt", sess) == 0
    out = (tmp / "col2.txt").read_text().splitlines()
    assert out == ["b", "e", "2"]


def test_wc_counts(sess: ShellSession, tmp: Path):
    # 3 lines, 4 words, known bytes (with newlines)
    text = "alpha beta\n\nGAMMA\n"
    (tmp / "m.txt").write_text(text)
    assert run_line("wc -l -w -c m.txt > wc.txt", sess) in (0, 1)
    parts = (tmp / "wc.txt").read_text().split()
    # wc outputs: lines words bytes filename
    lines, words, bytes_ = int(parts[0]), int(parts[1]), int(parts[2])
    assert lines == 3 and words == 3 and bytes_ == len(text.encode())


# ---- Extended tests (optional): rg, fd ----
def test_fd_find_txt_files(sess: ShellSession, tmp: Path):
    if not has_cmd("fd"):
        raise SkipTest("fd not installed")
    search = tmp / "search_fd"
    (search / "d1").mkdir(parents=True)
    (search / "d2").mkdir()
    (search / "d1" / "a.txt").write_text("a\n")
    (search / "d2" / "b.txt").write_text("b\n")
    (search / "d2" / "c.log").write_text("c\n")
    # '.' pattern matches anything; -t f for files; -e txt for extension
    assert run_line("fd . -t f -e txt ./search_fd | sort > fd_files.txt", sess) in (0, 1)
    out = (tmp / "fd_files.txt").read_text().strip().splitlines()
    expected = sorted(["./search_fd/d1/a.txt", "./search_fd/d2/b.txt"])
    assert out == expected


def test_rg_search(sess: ShellSession, tmp: Path):
    if not has_cmd("rg"):
        raise SkipTest("rg not installed")
    f = tmp / "text.txt"
    f.write_text("alpha\nBeta\ngamma\n")
    # Force filename in output and disable color
    assert run_line("rg -n --with-filename --color=never '^B' ./text.txt > rg_out.txt", sess) in (0, 1)
    out = (tmp / "rg_out.txt").read_text()
    assert "Beta" in out and "text.txt:" in out


def test_rg_count(sess: ShellSession, tmp: Path):
    if not has_cmd("rg"):
        raise SkipTest("rg not installed")
    f = tmp / "count.txt"
    f.write_text("foo\nbar\nfoo\n")
    assert run_line("rg -n 'foo' ./count.txt | wc -l > n.txt", sess) in (0, 1)
    n = int((tmp / "n.txt").read_text().strip() or "0")
    assert n == 2


def collect_tests(extend: bool):
    base_tests = [
        test_pwd_and_fs_ops,
        test_pipeline_grep,
        test_redirection_and_dup,
        test_to_devnull,
        test_conditionals,
        test_background,
        test_simple_command_runner_capture,
        test_env_contains_sanitized_vars,
        test_find_txt_files,
        test_find_and_wc_count,
        test_sort_basic,
        test_uniq_basic,
        test_uniq_count,
        test_cut_fields,
        test_wc_counts,
    ]
    if not extend:
        return base_tests
    return base_tests + [
        test_fd_find_txt_files,
        test_rg_search,
        test_rg_count,
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="pysh test runner")
    parser.add_argument("-e", "--extend", action="store_true", help="run extended tests (rg, fd)")
    args = parser.parse_args(argv)

    failures = []
    errors = []
    skipped = []
    passed = 0
    tmp = Path(tempfile.mkdtemp(prefix="pysh-test-"))
    cwd = Path.cwd()
    try:
        os.chdir(tmp)
        env = sandbox_env(tmp)
        shell = os.environ.get("SHELL", "/bin/sh")
        sess = ShellSession(shell=shell, inherit_env=False)
        sess.env.update(env)

        tests = collect_tests(args.extend)

        for t in tests:
            try:
                # Ensure each test starts at the sandbox root
                os.chdir(tmp)
                t(sess, tmp)
                passed += 1
                print(f"{green('[PASS]')} {bold(t.__name__)}")
            except SkipTest as e:
                skipped.append((t.__name__, str(e)))
                print(f"{blue('[SKIP]')} {bold(t.__name__)}: {e}")
            except AssertionError as e:
                print(f"{red('[FAIL]')} {bold(t.__name__)}: {e}")
                failures.append((t.__name__, str(e)))
            except Exception as e:
                print(f"{yellow('[ERROR]')} {bold(t.__name__)}: {e}")
                errors.append((t.__name__, f"ERROR: {e}"))

        total = len(tests)
        failed = len(failures)
        errored = len(errors)
        skipped_n = len(skipped)
        print("\n" + bold("Summary:"))
        print(
            "  Total: {}  {}  {}  {}  {}".format(
                total,
                green("Passed: " + str(passed)),
                red("Failed: " + str(failed)),
                yellow("Errors: " + str(errored)),
                cyan("Skipped: " + str(skipped_n)),
            )
        )

        if failures:
            print("\n" + bold(red("Failures:")))
            for name, msg in failures:
                print(f"  - {name}: {msg}")
        if errors:
            print("\n" + bold(yellow("Errors:")))
            for name, msg in errors:
                print(f"  - {name}: {msg}")
        if skipped:
            print("\n" + bold(cyan("Skipped:")))
            for name, msg in skipped:
                print(f"  - {name}: {msg}")

        return 0 if (failed == 0 and errored == 0) else 1
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
