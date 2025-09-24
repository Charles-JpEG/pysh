#!/usr/bin/env python3

# Entry of pysh

from __future__ import annotations

import os
import subprocess
import sys

PROMPT = "> "


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

    setup_readline()

    last_status = 0
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

        # Forward the exact line to the user's shell without any parsing.
        try:
            completed = subprocess.run([shell, "-c", line])
            last_status = completed.returncode
        except KeyboardInterrupt:
            # SIGINT during command: keep wrapper alive
            print()
            last_status = 130
        except FileNotFoundError:
            print(f"pysh: shell not found: {shell}", file=sys.stderr)
            return 127
        except Exception as e:
            print(f"pysh: error: {e}", file=sys.stderr)
            last_status = 1

    return last_status


def main() -> None:
    sys.exit(repl())


if __name__ == "__main__":
    main()