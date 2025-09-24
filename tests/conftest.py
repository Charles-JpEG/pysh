import os
import sys
from pathlib import Path
import pytest


@pytest.fixture(scope="session", autouse=True)
def add_src_to_path():
    # Ensure we can import modules from src/
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    sys.path.insert(0, str(src))
    yield
    # Cleanup path insertion
    try:
        sys.path.remove(str(src))
    except ValueError:
        pass


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    # Work in an isolated temp directory
    monkeypatch.chdir(tmp_path)
    # Prune environment to a minimal safe set
    safe_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "LANG": os.environ.get("LANG", "C"),
        "LC_ALL": os.environ.get("LC_ALL", "C"),
        "TERM": os.environ.get("TERM", "dumb"),
    }
    # Carry over SHELL if set to respect the user's default shell
    if "SHELL" in os.environ:
        safe_env["SHELL"] = os.environ["SHELL"]
    monkeypatch.setenv("PYSH_TEST_SANDBOX", "1")
    # Replace entire environment for subprocesses via monkeypatch (affects os.environ reads)
    monkeypatch.setenv("PATH", safe_env["PATH"])  # at least PATH is guaranteed
    # Return path and env dict for session creation
    return tmp_path, safe_env


@pytest.fixture()
def session(sandbox):
    from ops import ShellSession
    tmp_path, safe_env = sandbox
    shell = os.environ.get("SHELL", "/bin/sh")
    sess = ShellSession(shell=shell, inherit_env=False)
    sess.env.update(safe_env)
    return sess
