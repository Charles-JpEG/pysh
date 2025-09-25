#!/usr/bin/env python3

# Entry of pysh

from __future__ import annotations

import os
import sys
from typing import Optional

PROMPT = "> "

from ops import CommandRunner, ShellSession, execute_line  # local module in the same folder


def get_default_shell() -> str:
    shell = os.environ.get("SHELL")
    if shell:
        return shell
    try:
        import pwd

        shell = pwd.getpwuid(os.getuid()).pw_shell or "/bin/sh"
        return shell
    except Exception:
        return "/bin/sh"


def setup_readline() -> None:
    # Enable Ctrl-L to clear screen and basic line editing if readline is available
    try:
        import readline  # type: ignore

        # Ensure emacs-style bindings and explicit clear-screen on Ctrl-L
        readline.parse_and_bind("set editing-mode emacs")
        readline.parse_and_bind("Control-l: clear-screen")
        # Let Ctrl-D send EOF (default behavior); no binding needed
    except Exception:
        # readline not available; Ctrl-L won't clear without pressing Enter
        pass


def repl() -> int:
    shell = get_default_shell()
    session = ShellSession(shell=shell, inherit_env=True)

    setup_readline()

    last_runner: Optional[CommandRunner] = None
    while True:
        try:
            # Preserve the line exactly as typed (no strip/rstrip)
            line = input(PROMPT)
        except EOFError:
            # Ctrl-D on empty line -> exit
            print()
            break
        except KeyboardInterrupt:
            # Ctrl-C at prompt -> new line and continue
            print()
            continue

        if line == "":
            # Empty line: prompt again
            continue

        # Delegate to unified executor which prefers shell commands for preserved names and PATH commands,
        # and falls back to Python only when appropriate per spec.
        try:
            exit_code = execute_line(line, session)
            runner = CommandRunner(line=line, shell=shell, env=session.get_env())
            runner.exit_code = exit_code
            runner.stdout = None
            runner.stderr = None
            last_runner = runner
        except Exception as e:
            print(f"pysh: parse/exec error: {e}", file=sys.stderr)
            runner = CommandRunner(line=line, shell=shell, env=session.get_env())
            runner.exit_code = 1
            last_runner = runner

    # If loop exits via EOF, return the last exit code we saw (default 0).
    return (last_runner.exit_code if last_runner and last_runner.exit_code is not None else 0)


def main() -> None:
    sys.exit(repl())


if __name__ == "__main__":
    main()