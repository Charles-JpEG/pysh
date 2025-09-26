#!/usr/bin/env python3

# Entry of pysh

from __future__ import annotations

import os
import sys
from typing import Optional

try:
    import readline  # type: ignore
except Exception:  # pragma: no cover - fallback when readline unavailable
    readline = None

READLINE_ACTIVE = bool(readline)

PROMPT = "pysh> "
CONTINUATION_PROMPT = "... "

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
    if not READLINE_ACTIVE:
        return
    try:
        readline.parse_and_bind("set editing-mode emacs")
        readline.parse_and_bind("Control-l: clear-screen")
    except Exception:
        pass


def _set_indent_prefill(indent: str) -> None:
    if not READLINE_ACTIVE or not sys.stdin.isatty():
        return

    def hook() -> None:
        try:
            readline.insert_text(indent)
            readline.redisplay()
        finally:
            readline.set_pre_input_hook(None)

    readline.set_pre_input_hook(hook)


def repl() -> int:
    shell = get_default_shell()
    session = ShellSession(shell=shell, inherit_env=True)

    setup_readline()
    readline_enabled = READLINE_ACTIVE and sys.stdin.isatty()

    last_runner: Optional[CommandRunner] = None
    while True:
        try:
            if session.in_multi_line:
                indent_unit = session.get_indent_unit()
                indent = indent_unit * max(session.current_indent_level, 0)
                if readline_enabled:
                    if indent:
                        _set_indent_prefill(indent)
                    else:
                        readline.set_pre_input_hook(None)  # type: ignore[attr-defined]
                    prompt = CONTINUATION_PROMPT
                else:
                    prompt = CONTINUATION_PROMPT + indent
            else:
                if readline_enabled:
                    readline.set_pre_input_hook(None)  # type: ignore[attr-defined]
                prompt = PROMPT
            # Preserve the line exactly as typed (no strip/rstrip)
            line = input(prompt)
        except EOFError:
            # Ctrl-D on empty line -> exit
            print()
            break
        except KeyboardInterrupt:
            # Ctrl-C at prompt -> new line and continue
            print()
            continue

        if line == "" and not session.in_multi_line:
            # Empty line outside of multi-line mode: prompt again
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