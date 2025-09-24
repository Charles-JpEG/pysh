import os
from pathlib import Path
import re

import pytest

from ops import ShellSession, execute_line, CommandRunner


def run_line(line: str, session: ShellSession) -> int:
    return execute_line(line, session)


def test_pwd_and_fs_ops(session, tmp_path, capsys):
    # tmp_path is current working dir via fixture
    p = Path(".").resolve()
    assert p == tmp_path.resolve()

    # mkdir and list
    run_line("mkdir -p a/b", session)
    code = run_line("ls -1 a", session)
    assert code == 0
    out = capsys.readouterr().out
    assert "b" in out

    # Change current dir in parent process, then 'pwd' should reflect in child
    os.chdir(tmp_path / "a")
    code = run_line("pwd", session)
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("/a")


@pytest.mark.parametrize(
    "content,pattern,expected",
    [
        ("alpha\nBeta\ngamma\n", "^B", "Beta\n"),
        ("foo\nbar\nfoo\n", "foo", "foo\nfoo\n"),
    ],
)
def test_pipeline_grep(session, tmp_path, capsys, content, pattern, expected):
    f = tmp_path / "text.txt"
    f.write_text(content)

    code = run_line(f"cat text.txt | grep -E '{pattern}'", session)
    assert code in (0, 1)  # grep may return 1 if no match
    out = capsys.readouterr().out
    # Only lines that match pattern should appear
    if expected:
        assert expected in out


def test_redirection_and_dup(session, tmp_path, capsys):
    code = run_line("sh -c 'echo out; echo err 1>&2' >o.txt 2>&1", session)
    assert code == 0
    text = (tmp_path / "o.txt").read_text()
    # Both stdout and stderr are in the file
    assert "out\n" in text and "err\n" in text


def test_to_devnull(session, capsys):
    code = run_line("echo hi >/dev/null 2>&1", session)
    assert code == 0
    out = capsys.readouterr().out
    err = capsys.readouterr().err
    assert out == "" and err == ""


@pytest.mark.parametrize(
    "line,expect",
    [
        ("false || echo ok", True),
        ("true && echo ok", True),
        ("false && echo bad; echo ok", True),
    ],
)
def test_conditionals(session, capsys, line, expect):
    code = run_line(line, session)
    out = capsys.readouterr().out
    assert ("ok" in out) is expect


def test_background_jobs_do_not_block(session, tmp_path):
    code = run_line("sh -c 'sleep 0.1' &", session)
    assert code == 0
    # Background job stored
    assert session.background_jobs


def test_simple_command_runner_capture(session):
    # For a simple command (no operators), CommandRunner captures stdout/stderr
    runner = CommandRunner("printf 'a'", shell=session.shell, env=session.get_env())
    rc = runner.shell_run()
    assert rc == 0
    assert runner.stdout == 'a'


def test_env_contains_sanitized_vars(session, capsys):
    code = run_line("env", session)
    assert code == 0
    out = capsys.readouterr().out
    # Should include some of our sandbox env vars
    assert "PATH=" in out and "HOME=" in out

