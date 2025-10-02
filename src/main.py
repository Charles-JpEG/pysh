#!/usr/bin/env python3

# Entry of pysh

from __future__ import annotations

import argparse
import os
import shutil
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

# List of known POSIX-compliant shells
POSIX_SHELLS = [
    "bash", "zsh", "dash", "sh", "ksh", "mksh", "pdksh", "ash", "busybox",
    "yash", "loksh", "oksh", "posh", "bosh"
]


def is_posix_shell(shell_path: str) -> bool:
    """Check if a shell is POSIX-compliant by checking its basename against known shells."""
    if not shell_path:
        return False
    
    shell_name = os.path.basename(shell_path)
    return shell_name in POSIX_SHELLS


def find_posix_shell() -> Optional[str]:
    """Find a POSIX-compliant shell from the system PATH."""
    for shell_name in POSIX_SHELLS:
        shell_path = shutil.which(shell_name)
        if shell_path:
            return shell_path
    return None


def get_default_shell(force_shell: Optional[str] = None) -> tuple[str, bool]:
    """Get the shell to use and whether a warning was issued.
    
    Returns:
        tuple: (shell_path, warning_issued)
    """
    warning_issued = False
    
    # If force_shell is provided, use it but still check for POSIX compliance
    if force_shell:
        if not is_posix_shell(force_shell):
            current_shell = os.environ.get("SHELL", force_shell)
            print(f"Warning: '{force_shell}' may not be POSIX-compliant.", file=sys.stderr)
            print(f"Consider using a POSIX shell with: \"--shell {current_shell}\" or \"-s {current_shell}\"", file=sys.stderr)
            warning_issued = True
        return force_shell, warning_issued
    
    # Priority 1: $SHELL environment variable
    shell = os.environ.get("SHELL")
    if shell:
        if not is_posix_shell(shell):
            # Try to find a POSIX shell instead
            posix_shell = find_posix_shell()
            if posix_shell:
                print(f"Warning: '{shell}' may not be POSIX-compliant. Using '{posix_shell}' instead.", file=sys.stderr)
                print(f"To force using your shell: \"--shell {shell}\" or \"-s {shell}\"", file=sys.stderr)
                warning_issued = True
                return posix_shell, warning_issued
            else:
                print(f"Warning: '{shell}' may not be POSIX-compliant and no POSIX shell found.", file=sys.stderr)
                print(f"To force using your shell: \"--shell {shell}\" or \"-s {shell}\"", file=sys.stderr)
                warning_issued = True
                return shell, warning_issued
        return shell, warning_issued
    
    # Priority 2: User's login shell from /etc/passwd
    try:
        import pwd
        shell = pwd.getpwuid(os.getuid()).pw_shell or "/bin/sh"
        if not is_posix_shell(shell):
            posix_shell = find_posix_shell()
            if posix_shell:
                print(f"Warning: Login shell '{shell}' may not be POSIX-compliant. Using '{posix_shell}' instead.", file=sys.stderr)
                warning_issued = True
                return posix_shell, warning_issued
            else:
                print(f"Warning: Login shell '{shell}' may not be POSIX-compliant.", file=sys.stderr)
                warning_issued = True
        return shell, warning_issued
    except Exception:
        pass
    
    # Priority 3: Find any POSIX shell
    posix_shell = find_posix_shell()
    if posix_shell:
        return posix_shell, warning_issued
    
    # Final fallback: /bin/sh
    return "/bin/sh", warning_issued


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


def repl(shell_path: Optional[str] = None) -> int:
    shell, warning_issued = get_default_shell(shell_path)
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


def parse_args(args=None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="pysh - A hybrid Python/shell interpreter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pysh                     # Use default shell detection
  pysh --shell /bin/bash   # Force use of bash
  pysh -s /bin/zsh         # Force use of zsh

POSIX-compliant shells: bash, zsh, dash, sh, ksh, mksh, pdksh, ash, busybox, yash, loksh, oksh, posh, bosh
"""
    )
    
    parser.add_argument(
        "--shell", "-s",
        metavar="PATH",
        help="Force use of specified shell (path to shell executable)"
    )
    
    return parser.parse_args(args)


def main() -> None:
    args = parse_args()
    sys.exit(repl(shell_path=args.shell))


if __name__ == "__main__":
    main()