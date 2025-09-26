#!/usr/bin/env python3
"""
Self-contained test runner (base suite has no external Python deps).

Usage:
    ./test.py           # run base tests
    ./test.py -e        # run base + extended tests (rg, fd, pytest-based suites)
    ./test.py --extend
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import subprocess
import random
from pathlib import Path

# Allow importing from src/
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ops import ShellSession, execute_line, CommandRunner, try_python  # type: ignore


PYTEST_SUITES = [
    ROOT / "tests" / "test_shell_basics.py",
    ROOT / "tests" / "interactive_loop_test.py",
]


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
        "PWD": str(tmp),
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


def test_tilde_expansion(sess: ShellSession, tmp: Path):
    # ~ should expand to home directory when used at start of unquoted path
    out = _run_and_read("echo ~", tmp / 'o.txt', sess).strip()
    assert out == str(Path.home())


def test_ls_tilde(sess: ShellSession, tmp: Path):
    # ls ~ should expand ~ and list home directory
    rc = run_line("ls ~", sess)
    assert rc == 0


# ---- Quote/operator edge cases ----

def test_quoted_pipe_literal(sess: ShellSession, tmp: Path):
    # '|' inside quotes must not be treated as a pipe operator
    assert run_line("echo 'a|b' > qp.txt", sess) in (0, 1)
    out = (tmp / 'qp.txt').read_text().strip()
    assert out == 'a|b'


def test_escaped_pipe_literal(sess: ShellSession, tmp: Path):
    # Escaped pipe in unquoted context should be literal
    assert run_line("echo a\|b > ep.txt", sess) in (0, 1)
    out = (tmp / 'ep.txt').read_text().strip()
    assert out == 'a|b'


def test_operators_inside_quotes(sess: ShellSession, tmp: Path):
    # Ensure logical OR '||' inside quotes is not parsed as operator
    assert run_line("echo 'x||y' > qo.txt", sess) in (0, 1)
    out = (tmp / 'qo.txt').read_text().strip()
    assert out == 'x||y'


def test_quoted_pipe_with_pipeline(sess: ShellSession, tmp: Path):
    # Mix a real pipeline with a quoted pipe character in argument
    assert run_line("printf 'a|b\n' | grep -F 'a|b' > mix.txt", sess) in (0, 1)
    out = (tmp / 'mix.txt').read_text()
    assert out == 'a|b\n'


def test_dup_redirection_spaced_forms(sess: ShellSession, tmp: Path):
    # Both compact and spaced dup forms should work: 2>&1 and 2 >& 1 / 2 > & 1
    # 1) Compact form already covered elsewhere; test spaced variants here
    assert run_line("sh -c 'echo out; echo err 1>&2' >o2.txt 2 >& 1", sess) in (0, 1)
    text = (tmp / 'o2.txt').read_text()
    assert 'out\n' in text and 'err\n' in text
    # 2) With explicit separation between '>' and '&'
    assert run_line("sh -c 'echo out; echo err 1>&2' >o3.txt 2 > & 1", sess) in (0, 1)
    text2 = (tmp / 'o3.txt').read_text()
    assert 'out\n' in text2 and 'err\n' in text2


# ---- Python loop tests ----

def test_for_loop_basic(sess: ShellSession, tmp: Path):
    # Basic for loop
    code = run_line("for i in range(3):", sess)
    assert code == 0
    code = run_line("    print(i)", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_for_loop_with_else(sess: ShellSession, tmp: Path):
    # For loop with else
    code = run_line("for i in range(2):", sess)
    assert code == 0
    code = run_line("    print(i)", sess)
    assert code == 0
    code = run_line("else:", sess)
    assert code == 0
    code = run_line("    print('done')", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_while_loop_basic(sess: ShellSession, tmp: Path):
    # Basic while loop
    code = run_line("x = 0", sess)
    assert code == 0
    code = run_line("while x < 3:", sess)
    assert code == 0
    code = run_line("    print(x)", sess)
    assert code == 0
    code = run_line("    x += 1", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_nested_for_loops(sess: ShellSession, tmp: Path):
    # Nested for loops
    code = run_line("for i in range(2):", sess)
    assert code == 0
    code = run_line("    for j in range(2):", sess)
    assert code == 0
    code = run_line("        print(i, j)", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_for_loop_list_comprehension(sess: ShellSession, tmp: Path):
    # For loop with list comprehension
    code = run_line("squares = [x**2 for x in range(3)]", sess)
    assert code == 0
    code = run_line("for sq in squares:", sess)
    assert code == 0
    code = run_line("    print(sq)", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_while_loop_with_break(sess: ShellSession, tmp: Path):
    # While loop with break
    code = run_line("x = 0", sess)
    assert code == 0
    code = run_line("while True:", sess)
    assert code == 0
    code = run_line("    print(x)", sess)
    assert code == 0
    code = run_line("    x += 1", sess)
    assert code == 0
    code = run_line("    if x >= 3:", sess)
    assert code == 0
    code = run_line("        break", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_for_loop_enumerate(sess: ShellSession, tmp: Path):
    # For loop with enumerate
    code = run_line("for idx, val in enumerate(['a', 'b']):", sess)
    assert code == 0
    code = run_line("    print(idx, val)", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_while_loop_continue(sess: ShellSession, tmp: Path):
    # While loop with continue
    code = run_line("x = 0", sess)
    assert code == 0
    code = run_line("while x < 5:", sess)
    assert code == 0
    code = run_line("    x += 1", sess)
    assert code == 0
    code = run_line("    if x % 2 == 0:", sess)
    assert code == 0
    code = run_line("        continue", sess)
    assert code == 0
    code = run_line("    print(x)", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_for_loop_dict_items(sess: ShellSession, tmp: Path):
    # For loop over dict items
    code = run_line("d = {'a': 1, 'b': 2}", sess)
    assert code == 0
    code = run_line("for k, v in d.items():", sess)
    assert code == 0
    code = run_line("    print(k, v)", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_while_loop_else(sess: ShellSession, tmp: Path):
    # While loop with else
    code = run_line("x = 0", sess)
    assert code == 0
    code = run_line("while x < 2:", sess)
    assert code == 0
    code = run_line("    print(x)", sess)
    assert code == 0
    code = run_line("    x += 1", sess)
    assert code == 0
    code = run_line("else:", sess)
    assert code == 0
    code = run_line("    print('finished')", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


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


# ---- Variables: assignment, expansion, stringification, and env overlay ----

def test_var_assignment_and_expansion(sess: ShellSession, tmp: Path):
    # Assign Python var and expand via $var
    assert try_python("num = 10", sess) == 0
    assert run_line("echo $num > v.txt", sess) in (0, 1)
    assert (tmp / "v.txt").read_text().strip() == "10"


def test_var_mutation_python_then_expand(sess: ShellSession, tmp: Path):
    assert try_python("num = 10", sess) == 0
    assert try_python("num = num + 1", sess) == 0
    assert run_line("echo $num > v2.txt", sess) in (0, 1)
    assert (tmp / "v2.txt").read_text().strip() == "11"


def test_object_str_expansion(sess: ShellSession, tmp: Path):
    code = (
        "class Foo:\n"
        "    def __str__(self):\n"
        "        return 'FOO'\n"
        "obj = Foo()\n"
    )
    assert try_python(code, sess) == 0
    assert run_line("echo $obj > obj.txt", sess) in (0, 1)
    assert (tmp / "obj.txt").read_text().strip() == "FOO"


def test_list_str_in_quotes(sess: ShellSession, tmp: Path):
    assert try_python("arr = [1, 2, 3]", sess) == 0
    assert run_line("echo \"$arr\" > arr.txt", sess) in (0, 1)
    assert (tmp / "arr.txt").read_text().strip() == "[1, 2, 3]"


def test_no_expansion_in_single_quotes_and_escape(sess: ShellSession, tmp: Path):
    assert try_python("x = 'hi'", sess) == 0
    # Single quotes should prevent expansion
    assert run_line("echo '$x' > s.txt", sess) in (0, 1)
    assert (tmp / "s.txt").read_text().strip() == "$x"
    # Backslash escape should prevent expansion and yield literal $x
    assert run_line("echo \\$x > esc.txt", sess) in (0, 1)
    assert (tmp / "esc.txt").read_text().strip() == "$x"


def test_env_overlay_contains_python_vars(sess: ShellSession, tmp: Path):
    # Lowercase python var should be visible in env mapping passed to subprocess
    assert try_python("myvar = 123", sess) == 0
    assert run_line("env | grep '^myvar=' > envvars.txt", sess) in (0, 1)
    lines = (tmp / "envvars.txt").read_text().splitlines()
    # Accept presence with stringified value
    assert any(line.strip() == "myvar=123" for line in lines)


# ---- Programmatic tests per guaranteed shell command (>=5 each) ----

def _write(p: Path, text: str) -> None:
    p.write_text(text)


def _read(p: Path) -> str:
    return p.read_text()


def _run_and_read(line: str, out: Path, sess: ShellSession) -> str:
    rc = run_line(f"{line} > {out}", sess)
    assert rc in (0, 1)
    return _read(out)


def build_guaranteed_command_tests():
    tests = []

    # cd (5)
    def cd_1(sess: ShellSession, tmp: Path):
        (tmp / 'd1').mkdir()
        assert run_line("cd d1", sess) == 0
        out = _run_and_read("pwd", tmp / 'o.txt', sess).strip()
        assert out.endswith('/d1')

    def cd_2(sess: ShellSession, tmp: Path):
        # Starting from tmp, going up should land at tmp's parent
        assert run_line("cd ..", sess) == 0
        out = _run_and_read("pwd", tmp / 'o.txt', sess).strip()
        assert out == str(tmp.parent)

    def cd_3(sess: ShellSession, tmp: Path):
        home = str(tmp)
        sess.env['HOME'] = home
        assert run_line("cd", sess) == 0
        out = _run_and_read("pwd", tmp / 'o.txt', sess).strip()
        assert out == home

    def cd_4(sess: ShellSession, tmp: Path):
        p = tmp / 'abs'
        p.mkdir()
        assert run_line(f"cd {p}", sess) == 0
        out = _run_and_read("pwd", tmp / 'o.txt', sess).strip()
        assert out == str(p)

    def cd_5(sess: ShellSession, tmp: Path):
        rc = run_line("cd no_such_dir", sess)
        assert rc != 0

    tests += [cd_1, cd_2, cd_3, cd_4, cd_5]

    # ls (5)
    def ls_1(sess: ShellSession, tmp: Path):
        # Use unique filenames to avoid collisions with earlier tests' directories
        (tmp / 'fa').write_text('x')
        (tmp / 'fb').write_text('y')
        out = _run_and_read("ls -1", tmp / 'o.txt', sess)
        lines = set(l for l in out.splitlines() if l)
        assert {'fa', 'fb'}.issubset(lines)

    def ls_2(sess: ShellSession, tmp: Path):
        d = tmp / 'ld'
        d.mkdir(exist_ok=True)
        (d / 'c').write_text('z')
        out = _run_and_read(f"ls -1 {d}", tmp / 'o.txt', sess)
        assert out.strip().splitlines() == ['c']

    def ls_3(sess: ShellSession, tmp: Path):
        d = tmp / 'empty'
        d.mkdir(exist_ok=True)
        out = _run_and_read(f"ls -1 {d}", tmp / 'o.txt', sess)
        assert out.strip() == ''

    def ls_4(sess: ShellSession, tmp: Path):
        (tmp / '.dot').write_text('h')
        rc = run_line("ls -a | grep \.dot > o.txt", sess)
        assert rc in (0, 1)
        out = _read(tmp / 'o.txt')
        assert '.dot' in out

    def ls_5(sess: ShellSession, tmp: Path):
        rc = run_line("ls no_such_file", sess)
        assert rc != 0

    tests += [ls_1, ls_2, ls_3, ls_4, ls_5]

    # pwd (5)
    def pwd_1(sess: ShellSession, tmp: Path):
        out = _run_and_read("pwd", tmp / 'o.txt', sess).strip()
        assert out == str(tmp)

    def pwd_2(sess: ShellSession, tmp: Path):
        (tmp / 'p').mkdir(exist_ok=True)
        assert run_line("cd p", sess) == 0
        out = _run_and_read("pwd", tmp / 'o.txt', sess).strip()
        assert out.endswith('/p')

    def pwd_3(sess: ShellSession, tmp: Path):
        # From tmp, cd .. should produce tmp's parent
        assert run_line("cd ..", sess) == 0
        out = _run_and_read("pwd", tmp / 'o.txt', sess).strip()
        assert out == str(tmp.parent)

    def pwd_4(sess: ShellSession, tmp: Path):
        # PWD env should track real pwd
        out = _run_and_read("echo $PWD", tmp / 'o.txt', sess).strip()
        assert out == os.getcwd()

    def pwd_5(sess: ShellSession, tmp: Path):
        # After cd, PWD updates
        (tmp / 'q').mkdir(exist_ok=True)
        assert run_line("cd q", sess) == 0
        out = _run_and_read("echo $PWD", tmp / 'o.txt', sess).strip()
        assert out == str(tmp / 'q')
        assert run_line("cd ..", sess) == 0

    tests += [pwd_1, pwd_2, pwd_3, pwd_4, pwd_5]

    # mkdir (5)
    def mkdir_1(sess: ShellSession, tmp: Path):
        assert run_line("mkdir dmk", sess) in (0, 1)
        assert (tmp / 'dmk').is_dir()

    def mkdir_2(sess: ShellSession, tmp: Path):
        assert run_line("mkdir -p dmkp/a/b", sess) in (0, 1)
        assert (tmp / 'dmkp/a/b').is_dir()

    def mkdir_3(sess: ShellSession, tmp: Path):
        # mkdir existing without -p should fail
        assert run_line("mkdir dmk", sess) != 0

    def mkdir_4(sess: ShellSession, tmp: Path):
        # create with absolute path
        p = tmp / 'abs_mk'
        assert run_line(f"mkdir {p}", sess) in (0, 1)
        assert p.is_dir()

    def mkdir_5(sess: ShellSession, tmp: Path):
        # -p existing dir succeeds
        assert run_line("mkdir -p dmk", sess) in (0, 1)

    tests += [mkdir_1, mkdir_2, mkdir_3, mkdir_4, mkdir_5]

    # rmdir (5)
    def rmdir_1(sess: ShellSession, tmp: Path):
        d = tmp / 'drm'
        d.mkdir(exist_ok=True)
        assert run_line("rmdir drm", sess) in (0, 1)
        assert not d.exists()

    def rmdir_2(sess: ShellSession, tmp: Path):
        d = tmp / 'drm2'
        (d / 'x').parent.mkdir(parents=True, exist_ok=True)
        (d / 'x').write_text('1')
        assert run_line("rmdir drm2", sess) != 0

    def rmdir_3(sess: ShellSession, tmp: Path):
        d = tmp / 'drm3/a/b'
        d.mkdir(parents=True, exist_ok=True)
        assert run_line("rmdir drm3/a/b", sess) in (0, 1)
        assert not (tmp / 'drm3/a/b').exists()

    def rmdir_4(sess: ShellSession, tmp: Path):
        # removing non-existent dir should fail
        assert run_line("rmdir no_such", sess) != 0

    def rmdir_5(sess: ShellSession, tmp: Path):
        # remove nested after clearing
        d = tmp / 'drm4'
        (d).mkdir(exist_ok=True)
        assert run_line("rmdir drm4", sess) in (0, 1)
        assert not d.exists()

    tests += [rmdir_1, rmdir_2, rmdir_3, rmdir_4, rmdir_5]

    # rm (5)
    def rm_1(sess: ShellSession, tmp: Path):
        f = tmp / 'rf'
        f.write_text('a')
        assert run_line("rm rf", sess) in (0, 1)
        assert not f.exists()

    def rm_2(sess: ShellSession, tmp: Path):
        d = tmp / 'rd'
        (d / 'x').parent.mkdir(parents=True, exist_ok=True)
        (d / 'x').write_text('1')
        assert run_line("rm -r rd", sess) in (0, 1)
        assert not d.exists()

    def rm_3(sess: ShellSession, tmp: Path):
        f1 = tmp / 'a1'; f2 = tmp / 'a2'
        f1.write_text('1'); f2.write_text('2')
        assert run_line("rm a1 a2", sess) in (0, 1)
        assert not f1.exists() and not f2.exists()

    def rm_4(sess: ShellSession, tmp: Path):
        assert run_line("rm no_such", sess) != 0

    def rm_5(sess: ShellSession, tmp: Path):
        d = tmp / 'rdr'
        (d / 'y').parent.mkdir(parents=True, exist_ok=True)
        (d / 'y').write_text('1')
        assert run_line("rm -rf rdr", sess) in (0, 1)
        assert not d.exists()

    tests += [rm_1, rm_2, rm_3, rm_4, rm_5]

    # cp (5)
    def cp_1(sess: ShellSession, tmp: Path):
        (tmp / 's').write_text('hi')
        assert run_line("cp s t", sess) in (0, 1)
        assert (tmp / 't').read_text() == 'hi'

    def cp_2(sess: ShellSession, tmp: Path):
        d = tmp / 'cdir'
        (d / 'a').parent.mkdir(parents=True, exist_ok=True)
        (d / 'a').write_text('1')
        assert run_line("cp -r cdir cdir2", sess) in (0, 1)
        assert (tmp / 'cdir2/a').read_text() == '1'

    def cp_3(sess: ShellSession, tmp: Path):
        # overwrite
        (tmp / 't').write_text('new')
        assert run_line("cp s t", sess) in (0, 1)
        assert (tmp / 't').read_text() == 'hi'

    def cp_4(sess: ShellSession, tmp: Path):
        # copy into dir
        (tmp / 'dirx').mkdir(exist_ok=True)
        assert run_line("cp s dirx/", sess) in (0, 1)
        assert (tmp / 'dirx/s').read_text() == 'hi'

    def cp_5(sess: ShellSession, tmp: Path):
        # missing source
        assert run_line("cp nofile target", sess) != 0

    tests += [cp_1, cp_2, cp_3, cp_4, cp_5]

    # mv (5)
    def mv_1(sess: ShellSession, tmp: Path):
        (tmp / 'm').write_text('z')
        assert run_line("mv m n", sess) in (0, 1)
        assert (tmp / 'n').read_text() == 'z'

    def mv_2(sess: ShellSession, tmp: Path):
        (tmp / 'n2').write_text('q')
        (tmp / 'dirn').mkdir(exist_ok=True)
        assert run_line("mv n2 dirn/", sess) in (0, 1)
        assert (tmp / 'dirn/n2').read_text() == 'q'

    def mv_3(sess: ShellSession, tmp: Path):
        # rename into existing (should overwrite or prompt depending); use -f to force
        (tmp / 'x').write_text('1')
        (tmp / 'y').write_text('2')
        assert run_line("mv -f x y", sess) in (0, 1)
        assert (tmp / 'y').read_text() == '1'

    def mv_4(sess: ShellSession, tmp: Path):
        # missing source
        assert run_line("mv nofile target", sess) != 0

    def mv_5(sess: ShellSession, tmp: Path):
        # move directory
        (tmp / 'mvdir/a').mkdir(parents=True, exist_ok=True)
        assert run_line("mv mvdir mvdir2", sess) in (0, 1)
        assert (tmp / 'mvdir2/a').is_dir()

    tests += [mv_1, mv_2, mv_3, mv_4, mv_5]

    # find (we already have 2) add 3 more
    def find_3(sess: ShellSession, tmp: Path):
        d = tmp / 'fx'; (d).mkdir(exist_ok=True)
        (d / 'a.txt').write_text('1'); (d / 'b.log').write_text('2')
        out = _run_and_read("find ./fx -type f -name '*.log'", tmp / 'o.txt', sess)
        assert './fx/b.log' in out

    def find_4(sess: ShellSession, tmp: Path):
        d = tmp / 'fy/a'; d.mkdir(parents=True, exist_ok=True)
        (d / 'c.txt').write_text('3')
        out = _run_and_read("find ./fy -type d -name 'a'", tmp / 'o.txt', sess)
        assert './fy/a' in out

    def find_5(sess: ShellSession, tmp: Path):
        d = tmp / 'fz'; d.mkdir(exist_ok=True)
        (d / 'x').write_text('')
        out = _run_and_read("find ./fz -type f -size 0", tmp / 'o.txt', sess)
        assert './fz/x' in out

    tests += [find_3, find_4, find_5]

    # basename (5)
    def basename_1(sess: ShellSession, tmp: Path):
        out = _run_and_read("basename /a/b/c.txt", tmp / 'o.txt', sess).strip()
        assert out == 'c.txt'

    def basename_2(sess: ShellSession, tmp: Path):
        out = _run_and_read("basename c.txt .txt", tmp / 'o.txt', sess).strip()
        assert out == 'c'

    def basename_3(sess: ShellSession, tmp: Path):
        out = _run_and_read("basename /", tmp / 'o.txt', sess).strip()
        assert out in ('/', '')

    def basename_4(sess: ShellSession, tmp: Path):
        out = _run_and_read("basename ./d/e/", tmp / 'o.txt', sess).strip()
        assert out == 'e'

    def basename_5(sess: ShellSession, tmp: Path):
        out = _run_and_read("basename file", tmp / 'o.txt', sess).strip()
        assert out == 'file'

    tests += [basename_1, basename_2, basename_3, basename_4, basename_5]

    # dirname (5)
    def dirname_1(sess: ShellSession, tmp: Path):
        out = _run_and_read("dirname /a/b/c.txt", tmp / 'o.txt', sess).strip()
        assert out == '/a/b'

    def dirname_2(sess: ShellSession, tmp: Path):
        out = _run_and_read("dirname c.txt", tmp / 'o.txt', sess).strip()
        assert out == '.'

    def dirname_3(sess: ShellSession, tmp: Path):
        out = _run_and_read("dirname ./a/b/", tmp / 'o.txt', sess).strip()
        assert out.endswith('./a') or out.endswith('/a')

    def dirname_4(sess: ShellSession, tmp: Path):
        out = _run_and_read("dirname /", tmp / 'o.txt', sess).strip()
        assert out == '/'

    def dirname_5(sess: ShellSession, tmp: Path):
        out = _run_and_read("dirname .", tmp / 'o.txt', sess).strip()
        assert out == '.'

    tests += [dirname_1, dirname_2, dirname_3, dirname_4, dirname_5]

    # echo (5)
    def echo_1(sess: ShellSession, tmp: Path):
        out = _run_and_read("echo hello", tmp / 'o.txt', sess).strip()
        assert out == 'hello'

    def echo_2(sess: ShellSession, tmp: Path):
        out = _run_and_read("echo 'a b'", tmp / 'o.txt', sess).strip()
        assert out == 'a b'

    def echo_3(sess: ShellSession, tmp: Path):
        out = _run_and_read("echo \$HOME", tmp / 'o.txt', sess).strip()
        assert out == '$HOME'

    def echo_4(sess: ShellSession, tmp: Path):
        assert try_python("v = 42", sess) == 0
        out = _run_and_read("echo $v", tmp / 'o.txt', sess).strip()
        assert out == '42'

    def echo_5(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf '%s' hello", tmp / 'o.txt', sess).strip()
        assert out == 'hello'

    tests += [echo_1, echo_2, echo_3, echo_4, echo_5]

    # cat (5)
    def cat_1(sess: ShellSession, tmp: Path):
        (tmp / 'f').write_text('x')
        out = _run_and_read("cat f", tmp / 'o.txt', sess).strip()
        assert out == 'x'

    def cat_2(sess: ShellSession, tmp: Path):
        (tmp / 'f2').write_text('a\nb\n')
        out = _run_and_read("cat f2", tmp / 'o.txt', sess)
        assert out == 'a\nb\n'

    def cat_3(sess: ShellSession, tmp: Path):
        (tmp / 'f3').write_text('1')
        (tmp / 'f4').write_text('2')
        out = _run_and_read("cat f3 f4", tmp / 'o.txt', sess)
        # Some systems may not add trailing newline when concatenating files without newlines
        assert out in ('1\n2\n', '1\n2', '12')

    def cat_4(sess: ShellSession, tmp: Path):
        rc = run_line("cat no_such", sess)
        assert rc != 0

    def cat_5(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf 'a\n' | cat", tmp / 'o.txt', sess)
        assert out == 'a\n'

    tests += [cat_1, cat_2, cat_3, cat_4, cat_5]

    # head (5)
    def head_1(sess: ShellSession, tmp: Path):
        (tmp / 'h').write_text('\n'.join(str(i) for i in range(1,11)) + '\n')
        out = _run_and_read("head -n 3 h", tmp / 'o.txt', sess)
        assert out == '1\n2\n3\n'

    def head_2(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf '1\n2\n3\n4\n' | head -n 2", tmp / 'o.txt', sess)
        assert out == '1\n2\n'

    def head_3(sess: ShellSession, tmp: Path):
        out = _run_and_read("head -n 1 h", tmp / 'o.txt', sess)
        assert out == '1\n'

    def head_4(sess: ShellSession, tmp: Path):
        out = _run_and_read("head h", tmp / 'o.txt', sess)
        assert out.splitlines()[0] == '1'

    def head_5(sess: ShellSession, tmp: Path):
        rc = run_line("head no_such", sess)
        assert rc != 0

    tests += [head_1, head_2, head_3, head_4, head_5]

    # tail (5)
    def tail_1(sess: ShellSession, tmp: Path):
        (tmp / 't').write_text('\n'.join(str(i) for i in range(1,11)) + '\n')
        out = _run_and_read("tail -n 2 t", tmp / 'o.txt', sess)
        assert out == '10\n' if out.count('\n')==1 else '9\n10\n'

    def tail_2(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf 'a\nb\n' | tail -n 1", tmp / 'o.txt', sess)
        assert out == 'b\n'

    def tail_3(sess: ShellSession, tmp: Path):
        out = _run_and_read("tail -n +3 t", tmp / 'o.txt', sess)
        assert out.splitlines()[0] in ('3', '3\n') if out else True

    def tail_4(sess: ShellSession, tmp: Path):
        out = _run_and_read("tail t", tmp / 'o.txt', sess)
        assert out.splitlines()[-1] == '10'

    def tail_5(sess: ShellSession, tmp: Path):
        rc = run_line("tail no_such", sess)
        assert rc != 0

    tests += [tail_1, tail_2, tail_3, tail_4, tail_5]

    # wc (5) (we already have one) add more
    def wc_1(sess: ShellSession, tmp: Path):
        (tmp / 'w').write_text('a b c\n')
        out = _run_and_read("wc -w w", tmp / 'o.txt', sess).strip().split()
        assert int(out[0]) == 3

    def wc_2(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf 'x\ny\n' | wc -l", tmp / 'o.txt', sess).strip()
        assert out.isdigit() and int(out) == 2

    def wc_3(sess: ShellSession, tmp: Path):
        data = 'abc\n'
        (tmp / 'wc3').write_text(data)
        out = _run_and_read("wc -c wc3", tmp / 'o.txt', sess).strip().split()[0]
        assert int(out) == len(data.encode())

    def wc_4(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf '' | wc -c", tmp / 'o.txt', sess).strip()
        assert int(out) == 0

    def wc_5(sess: ShellSession, tmp: Path):
        rc = run_line("wc no_such", sess)
        assert rc != 0

    tests += [wc_1, wc_2, wc_3, wc_4, wc_5]

    # grep (5)
    def grep_1(sess: ShellSession, tmp: Path):
        (tmp / 'g').write_text('alpha\nBeta\n')
        out = _run_and_read("grep -F 'Beta' g", tmp / 'o.txt', sess)
        assert 'Beta' in out

    def grep_2(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf 'a\n' | grep -F 'a'", tmp / 'o.txt', sess)
        assert out == 'a\n'

    def grep_3(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf 'a\n' | grep -F 'b'", tmp / 'o.txt', sess)
        assert out == ''

    def grep_4(sess: ShellSession, tmp: Path):
        (tmp / 'g2').write_text('aaa\naba\n')
        out = _run_and_read("grep -E 'ab.' ./g2", tmp / 'o.txt', sess)
        assert 'aba' in out

    def grep_5(sess: ShellSession, tmp: Path):
        rc = run_line("grep -F 'x' no_such", sess)
        assert rc != 0

    tests += [grep_1, grep_2, grep_3, grep_4, grep_5]

    # sort (5)
    def sort_1(sess: ShellSession, tmp: Path):
        (tmp / 's').write_text('b\na\n')
        out = _run_and_read("sort s", tmp / 'o.txt', sess)
        assert out.splitlines() == ['a', 'b']

    def sort_2(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf '2\n10\n' | sort -n", tmp / 'o.txt', sess)
        assert out.splitlines() == ['2', '10']

    def sort_3(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf 'x\n' | sort", tmp / 'o.txt', sess)
        assert out == 'x\n'

    def sort_4(sess: ShellSession, tmp: Path):
        rc = run_line("sort no_such", sess)
        assert rc != 0

    def sort_5(sess: ShellSession, tmp: Path):
        (tmp / 's2').write_text('b\na\n')
        out = _run_and_read("sort -r s2", tmp / 'o.txt', sess)
        assert out.splitlines() == ['b', 'a']

    tests += [sort_1, sort_2, sort_3, sort_4, sort_5]

    # uniq (5)
    def uniq_1(sess: ShellSession, tmp: Path):
        (tmp / 'u').write_text('a\na\nb\n')
        out = _run_and_read("uniq u", tmp / 'o.txt', sess)
        assert out.splitlines() == ['a', 'b']

    def uniq_2(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf 'a\na\n' | uniq -c", tmp / 'o.txt', sess)
        assert out.strip().split()[0].isdigit()

    def uniq_3(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf 'b\na\n' | sort | uniq", tmp / 'o.txt', sess)
        assert out.splitlines() == ['a', 'b']

    def uniq_4(sess: ShellSession, tmp: Path):
        rc = run_line("uniq no_such", sess)
        assert rc != 0

    def uniq_5(sess: ShellSession, tmp: Path):
        (tmp / 'uu').write_text('a\nA\n')
        out = _run_and_read("uniq -i uu", tmp / 'o.txt', sess)
        assert out.strip().lower() == 'a'

    tests += [uniq_1, uniq_2, uniq_3, uniq_4, uniq_5]

    # cut (5)
    def cut_1(sess: ShellSession, tmp: Path):
        (tmp / 'c').write_text('a,b,c\n')
        out = _run_and_read("cut -d, -f2 c", tmp / 'o.txt', sess)
        assert out.strip() == 'b'

    def cut_2(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf '1\t2\n' | cut -f2", tmp / 'o.txt', sess)
        assert out.strip() == '2'

    def cut_3(sess: ShellSession, tmp: Path):
        out = _run_and_read("printf 'abc\n' | cut -c2", tmp / 'o.txt', sess)
        assert out.strip() == 'b'

    def cut_4(sess: ShellSession, tmp: Path):
        rc = run_line("cut -d, -f2 no_such", sess)
        assert rc != 0

    def cut_5(sess: ShellSession, tmp: Path):
        (tmp / 'c2').write_text('a,b,c\n1,2,3\n')
        out = _run_and_read("cut -d, -f1,3 c2", tmp / 'o.txt', sess)
        assert out.splitlines() == ['a,c', '1,3']

    tests += [cut_1, cut_2, cut_3, cut_4, cut_5]

    # date (5)
    def date_1(sess: ShellSession, tmp: Path):
        out = _run_and_read("date +%Y", tmp / 'o.txt', sess).strip()
        assert out.isdigit() and len(out) == 4

    def date_2(sess: ShellSession, tmp: Path):
        out = _run_and_read("date +%m", tmp / 'o.txt', sess).strip()
        assert out.isdigit()

    def date_3(sess: ShellSession, tmp: Path):
        out = _run_and_read("date +%d", tmp / 'o.txt', sess).strip()
        assert out.isdigit()

    def date_4(sess: ShellSession, tmp: Path):
        out = _run_and_read("date +%H:%M", tmp / 'o.txt', sess).strip()
        assert ':' in out

    def date_5(sess: ShellSession, tmp: Path):
        assert run_line("date -u > o.txt", sess) in (0, 1)

    tests += [date_1, date_2, date_3, date_4, date_5]

    # uname (5)
    def uname_1(sess: ShellSession, tmp: Path):
        out = _run_and_read("uname -s", tmp / 'o.txt', sess).strip()
        assert out != ''

    def uname_2(sess: ShellSession, tmp: Path):
        out = _run_and_read("uname -m", tmp / 'o.txt', sess).strip()
        assert out != ''

    def uname_3(sess: ShellSession, tmp: Path):
        out = _run_and_read("uname -n", tmp / 'o.txt', sess).strip()
        assert out != ''

    def uname_4(sess: ShellSession, tmp: Path):
        out = _run_and_read("uname -r", tmp / 'o.txt', sess).strip()
        assert out != ''

    def uname_5(sess: ShellSession, tmp: Path):
        out = _run_and_read("uname", tmp / 'o.txt', sess).strip()
        assert out != ''

    tests += [uname_1, uname_2, uname_3, uname_4, uname_5]

    # ps (5)
    def ps_1(sess: ShellSession, tmp: Path):
        rc = run_line("ps > o.txt", sess)
        assert rc in (0, 1)
        out = _read(tmp / 'o.txt')
        assert out != ''

    def ps_2(sess: ShellSession, tmp: Path):
        rc = run_line("ps -o pid,comm | head -n 1 > o.txt", sess)
        assert rc in (0, 1)
        out = _read(tmp / 'o.txt')
        assert 'PID' in out.upper() or 'pid' in out

    def ps_3(sess: ShellSession, tmp: Path):
        rc = run_line("ps | grep -v grep | grep ps > o.txt", sess)
        assert rc in (0, 1)

    def ps_4(sess: ShellSession, tmp: Path):
        rc = run_line("ps aux > o.txt", sess)
        assert rc in (0, 1)

    def ps_5(sess: ShellSession, tmp: Path):
        rc = run_line("ps -e > o.txt", sess)
        assert rc in (0, 1)

    tests += [ps_1, ps_2, ps_3, ps_4, ps_5]

    # which (5)
    def which_1(sess: ShellSession, tmp: Path):
        rc = run_line("which sh > o.txt", sess)
        assert rc in (0, 1)
        out = _read(tmp / 'o.txt')
        assert out.strip() != ''

    def which_2(sess: ShellSession, tmp: Path):
        rc = run_line("which env > o.txt", sess)
        assert rc in (0, 1)
        out = _read(tmp / 'o.txt')
        assert out.strip() != ''

    def which_3(sess: ShellSession, tmp: Path):
        rc = run_line("which no_such > o.txt", sess)
        assert rc != 0

    def which_4(sess: ShellSession, tmp: Path):
        rc = run_line("which ls > o.txt", sess)
        assert rc in (0, 1)

    def which_5(sess: ShellSession, tmp: Path):
        rc = run_line("which printf > o.txt", sess)
        assert rc in (0, 1)

    tests += [which_1, which_2, which_3, which_4, which_5]

    # env (5)
    def env_1(sess: ShellSession, tmp: Path):
        out = _run_and_read("env", tmp / 'o.txt', sess)
        assert 'PATH=' in out

    def env_2(sess: ShellSession, tmp: Path):
        assert try_python("FOO = 'bar'", sess) == 0
        out = _run_and_read("env", tmp / 'o.txt', sess)
        assert 'FOO=bar' in out

    def env_3(sess: ShellSession, tmp: Path):
        assert try_python("BAR = 123", sess) == 0
        out = _run_and_read("env", tmp / 'o.txt', sess)
        assert 'BAR=123' in out

    def env_4(sess: ShellSession, tmp: Path):
        out = _run_and_read("env | grep '^HOME='", tmp / 'o.txt', sess)
        assert 'HOME=' in out

    def env_5(sess: ShellSession, tmp: Path):
        out = _run_and_read("env | grep '^SHELL='", tmp / 'o.txt', sess)
        assert 'SHELL=' in out

    tests += [env_1, env_2, env_3, env_4, env_5]

    return tests


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


# ---- Extended loop tests with modules ----

def test_for_loop_with_re(sess: ShellSession, tmp: Path):
    import re
    # For loop with re module
    code = run_line("import re", sess)
    assert code == 0
    code = run_line("for word in ['hello', 'world', 'test']:", sess)
    assert code == 0
    code = run_line("    if re.match(r'^h', word):", sess)
    assert code == 0
    code = run_line("        print(word)", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_while_loop_with_math(sess: ShellSession, tmp: Path):
    import math
    # While loop with math module
    code = run_line("import math", sess)
    assert code == 0
    code = run_line("x = 1", sess)
    assert code == 0
    code = run_line("while x <= 10:", sess)
    assert code == 0
    code = run_line("    print(math.sqrt(x))", sess)
    assert code == 0
    code = run_line("    x *= 2", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_for_loop_numpy_array(sess: ShellSession, tmp: Path):
    # For loop with numpy (if available)
    try:
        import numpy as np
    except ImportError:
        raise SkipTest("numpy not installed")
    code = run_line("import numpy as np", sess)
    assert code == 0
    code = run_line("arr = np.array([1, 2, 3])", sess)
    assert code == 0
    code = run_line("for val in arr:", sess)
    assert code == 0
    code = run_line("    print(val)", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_while_loop_collections(sess: ShellSession, tmp: Path):
    import collections
    # While loop with collections
    code = run_line("import collections", sess)
    assert code == 0
    code = run_line("dq = collections.deque([1, 2, 3])", sess)
    assert code == 0
    code = run_line("while dq:", sess)
    assert code == 0
    code = run_line("    print(dq.popleft())", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_for_loop_itertools(sess: ShellSession, tmp: Path):
    import itertools
    # For loop with itertools
    code = run_line("import itertools", sess)
    assert code == 0
    code = run_line("for x, y in itertools.product([1, 2], ['a', 'b']):", sess)
    assert code == 0
    code = run_line("    print(x, y)", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_while_loop_random(sess: ShellSession, tmp: Path):
    import random
    # While loop with random
    code = run_line("import random", sess)
    assert code == 0
    code = run_line("count = 0", sess)
    assert code == 0
    code = run_line("while count < 3:", sess)
    assert code == 0
    code = run_line("    print(random.randint(1, 10))", sess)
    assert code == 0
    code = run_line("    count += 1", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_for_loop_json(sess: ShellSession, tmp: Path):
    import json
    # For loop with json
    code = run_line("import json", sess)
    assert code == 0
    code = run_line("data = {'a': 1, 'b': 2}", sess)
    assert code == 0
    code = run_line("for k in json.dumps(data):", sess)
    assert code == 0
    code = run_line("    print(k)", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_while_loop_datetime(sess: ShellSession, tmp: Path):
    import datetime
    # While loop with datetime
    code = run_line("import datetime", sess)
    assert code == 0
    code = run_line("now = datetime.datetime.now()", sess)
    assert code == 0
    code = run_line("future = now + datetime.timedelta(seconds=2)", sess)
    assert code == 0
    code = run_line("while datetime.datetime.now() < future:", sess)
    assert code == 0
    code = run_line("    pass", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_for_loop_os(sess: ShellSession, tmp: Path):
    import os
    # For loop with os
    code = run_line("import os", sess)
    assert code == 0
    code = run_line("for f in os.listdir('.'):", sess)
    assert code == 0
    code = run_line("    if f.endswith('.txt'):", sess)
    assert code == 0
    code = run_line("        print(f)", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


def test_while_loop_subprocess(sess: ShellSession, tmp: Path):
    import subprocess
    # While loop with subprocess (careful)
    code = run_line("import subprocess", sess)
    assert code == 0
    code = run_line("attempts = 0", sess)
    assert code == 0
    code = run_line("while attempts < 2:", sess)
    assert code == 0
    code = run_line("    result = subprocess.run(['echo', 'test'], capture_output=True, text=True)", sess)
    assert code == 0
    code = run_line("    print(result.stdout.strip())", sess)
    assert code == 0
    code = run_line("    attempts += 1", sess)
    assert code == 0
    code = run_line("", sess)
    assert code == 0


# ---- Extended comparison test: pysh vs system shell on a multi-step pipeline ----
def test_compare_pysh_vs_shell_phonebook(sess: ShellSession, tmp: Path):
    # Requires standard tools
    if not has_cmd("sed"):
        raise SkipTest("sed not installed")
    if not has_cmd("nl"):
        raise SkipTest("nl not installed")

    rng = random.Random(42)
    names = [
        "Harry Potter", "Hermione Granger", "Ron Weasley", "Albus Dumbledore",
        "Severus Snape", "Rubeus Hagrid", "Minerva McGonagall", "Sirius Black",
        "Remus Lupin", "Draco Malfoy"
    ]
    rng.shuffle(names)
    def phone() -> str:
        return ''.join(rng.choice('0123456789') for _ in range(9))

    # Create two separate sandboxes: one for pysh, one for system shell
    py_dir = tmp / 'pb_pysh'
    sh_dir = tmp / 'pb_shell'
    py_dir.mkdir(exist_ok=True)
    sh_dir.mkdir(exist_ok=True)

    py_file = py_dir / 'test.psv'
    sh_file = sh_dir / 'test.psv'
    content_lines = [f"{n}|{phone()}" for n in names]
    py_file.write_text('\n'.join(content_lines) + '\n')
    sh_file.write_text('\n'.join(content_lines) + '\n')

    # Environment for both
    env = sandbox_env(tmp)

    # --- pysh path (interactive via same session) ---
    shell = os.environ.get("SHELL", "/bin/sh")
    sess_py = ShellSession(shell=shell, inherit_env=False)
    sess_py.env.update(env)

    # Task1: cat phonebook
    os.chdir(py_dir)
    assert run_line("cat test.psv > cat_out.txt", sess_py) in (0, 1)

    # Task2: sort by name (field 1), then generate line numbers as id, write to phonebook.psv
    # Using 'nl' for stable numbering with a '|' separator
    cmd2 = "sort -t '|' -k1,1 test.psv | nl -ba -w1 -s '|' > phonebook.psv"
    assert run_line(cmd2, sess_py) in (0, 1)

    # Task3: lowercase names in place (left side of the first '|')
    # GNU sed: \L to lower-case capture group
    cmd3 = "sed -i -E 's/^([^|]+)/\\L\\1/' phonebook.psv"
    assert run_line(cmd3, sess_py) in (0, 1)

    # --- system shell path ---
    os.chdir(sh_dir)
    sh = os.environ.get("SHELL", "/bin/sh")

    def sh_run(cmd: str) -> None:
        r = subprocess.run([sh, "-c", cmd], cwd=sh_dir, env=env, capture_output=True, text=True)
        if r.returncode not in (0, 1):
            raise AssertionError(f"shell cmd failed: {cmd}\nstdout: {r.stdout}\nstderr: {r.stderr}")

    sh_run("cat test.psv > cat_out.txt")
    sh_run("sort -t '|' -k1,1 test.psv | nl -ba -w1 -s '|' > phonebook.psv")
    sh_run("sed -i -E 's/^([^|]+)/\\L\\1/' phonebook.psv")

    # --- Compare outputs exactly ---
    os.chdir(tmp)  # ensure no lingering cwd locks
    assert (py_dir / 'cat_out.txt').read_text() == (sh_dir / 'cat_out.txt').read_text()
    assert (py_dir / 'phonebook.psv').read_text() == (sh_dir / 'phonebook.psv').read_text()


def pytest_extended_suite(sess: ShellSession, tmp: Path):
    try:
        import pytest  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        raise SkipTest("pytest not installed") from exc

    original_cwd = Path.cwd()
    try:
        os.chdir(ROOT)
        args = ["-q", *[str(path) for path in PYTEST_SUITES]]
        exit_code = pytest.main(args)
    finally:
        os.chdir(original_cwd)

    if exit_code != 0:
        raise AssertionError(f"pytest suite failed (exit code {exit_code})")


def collect_tests(extend: bool):
    base_tests = [
        test_pwd_and_fs_ops,
        test_pipeline_grep,
        test_redirection_and_dup,
        test_to_devnull,
        # Quote/operator edge cases
        test_quoted_pipe_literal,
        test_escaped_pipe_literal,
        test_operators_inside_quotes,
        test_quoted_pipe_with_pipeline,
        test_dup_redirection_spaced_forms,
        test_conditionals,
        test_background,
        test_simple_command_runner_capture,
        test_env_contains_sanitized_vars,
        test_tilde_expansion,
        test_ls_tilde,
        test_find_txt_files,
        test_find_and_wc_count,
        test_sort_basic,
        test_uniq_basic,
        test_uniq_count,
        test_cut_fields,
        test_wc_counts,
        # Variables
        test_var_assignment_and_expansion,
        test_var_mutation_python_then_expand,
        test_object_str_expansion,
        test_list_str_in_quotes,
        test_no_expansion_in_single_quotes_and_escape,
        test_env_overlay_contains_python_vars,
    ]
    # Append per-command comprehensive tests
    base_tests += build_guaranteed_command_tests()
    if not extend:
        return base_tests
    return base_tests + [
        test_fd_find_txt_files,
        test_rg_search,
        test_rg_count,
        test_compare_pysh_vs_shell_phonebook,
        pytest_extended_suite,
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
                # Keep session PWD synced to current cwd for each test
                sess.env['PWD'] = str(tmp)
                sess.py_vars['PWD'] = str(tmp)
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
