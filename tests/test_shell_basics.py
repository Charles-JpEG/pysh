import os
from pathlib import Path

import pytest  # type: ignore

from ops import ShellSession, execute_line, CommandRunner


def run_line(line: str, session: ShellSession) -> int:
    return execute_line(line, session)


def test_pwd_and_fs_ops(session, tmp_path):
    # tmp_path is current working dir via fixture
    p = Path(".").resolve()
    assert p == tmp_path.resolve()

    # mkdir and list
    run_line("mkdir -p a/b", session)
    code = run_line("ls -1 a > listing.txt", session)
    assert code == 0
    listing = (tmp_path / "listing.txt").read_text()
    assert "b" in listing

    # Change current dir in parent process, then 'pwd' should reflect in child
    os.chdir(tmp_path / "a")
    code = run_line("pwd > pwd.txt", session)
    assert code == 0
    assert (tmp_path / "a" / "pwd.txt").read_text().strip().endswith("/a")


@pytest.mark.parametrize(
    "content,pattern,expected",
    [
        ("alpha\nBeta\ngamma\n", "^B", "Beta\n"),
        ("foo\nbar\nfoo\n", "foo", "foo\nfoo\n"),
    ],
)
def test_pipeline_grep(session, tmp_path, content, pattern, expected):
    f = tmp_path / "text.txt"
    f.write_text(content)

    code = run_line(f"cat text.txt | grep -E '{pattern}' > filtered.txt", session)
    assert code in (0, 1)  # grep may return 1 if no match
    filtered = (tmp_path / "filtered.txt").read_text() if (tmp_path / "filtered.txt").exists() else ""
    if expected:
        assert expected in filtered
    else:
        assert filtered == ""


def test_python_pipeline_into_shell(session, tmp_path):
    run_line("ENV = {'COLOR': 'blue', 'OTHER': 'green'}", session)
    code = run_line("print(ENV) | grep COLOR > env_hit.txt", session)
    assert code in (0, 1)
    text = (tmp_path / "env_hit.txt").read_text()
    assert "COLOR" in text
    assert "blue" in text


def test_redirection_and_dup(session, tmp_path):
    code = run_line("sh -c 'echo out; echo err 1>&2' >o.txt 2>&1", session)
    assert code == 0
    text = (tmp_path / "o.txt").read_text()
    # Both stdout and stderr are in the file
    assert "out\n" in text and "err\n" in text


def test_to_devnull(session):
    code = run_line("sh -c 'echo hi; echo err 1>&2' >/dev/null 2>&1", session)
    assert code == 0


@pytest.mark.parametrize(
    "line,expect",
    [
        ("false || echo ok", True),
        ("true && echo ok", True),
        ("false && echo bad; echo ok", True),
    ],
)
def test_conditionals(session, line, expect):
    outfile = Path("cond.txt")
    if outfile.exists():
        outfile.unlink()
    code = run_line(f"{line} > cond.txt", session)
    assert code == 0
    result = outfile.read_text() if outfile.exists() else ""
    assert ("ok" in result) is expect


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


def test_env_contains_sanitized_vars(session):
    code = run_line("env > env.txt", session)
    assert code == 0
    text = Path("env.txt").read_text()
    assert "PATH=" in text and "HOME=" in text

