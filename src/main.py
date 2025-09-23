#!/usr/bin/env python3

# Main module for pysh

import os
import sys
import command
from groups import (
    split_line,
    format_groups,
)

# Optional readline import for key bindings (Ctrl+L clear-screen)
try:
    import readline  # type: ignore
except Exception:  # pragma: no cover - fallback if readline missing
    readline = None  # type: ignore

## Parsing helpers now imported from groups.py


def main():
    if len(sys.argv) > 1:
        line = ' '.join(sys.argv[1:])
        print(format_groups(split_line(line)))
        return
    print("pysh <dry run>\n")   # <FIXME>

    # Setup key bindings if readline is available.
    if readline is not None:  # type: ignore
        # Bind Ctrl+L to the built-in clear-screen action (like bash)
        try:
            readline.parse_and_bind('Control-l: clear-screen')  # type: ignore
        except Exception:
            pass

    def clear_screen():
        """Clear the terminal using ANSI escape sequence.
        Used as a fallback if readline binding not active; also used when user
        enters a line containing form-feed (Ctrl+L char) that wasn't intercepted.
        """
        # Standard ANSI clear & home
        print("\033[H\033[J", end='', flush=True)

    # Main loop
    while True:
        try:
            cwd = os.getcwd()
            home = os.path.expanduser('~')
            if cwd.startswith(home):
                cwd = cwd.replace(home, '~', 1)
            line = input(f"{cwd}> ")    # TODO: Use template from env or config
        except EOFError:
            print()
            sys.exit(0)
        except KeyboardInterrupt:
            print()
            continue
        # Detect raw form feed (Ctrl+L) if readline didn't
        # clear screen (e.g., platforms without readline)
        if '\x0c' in line:  # form feed char
            clear_screen()
            # Remove all form-feed chars; if nothing else remains, reprompt.
            line = line.replace('\x0c', '')
            if not line.strip():
                continue
        line = line.strip()
        if not line:
            continue
        groups = split_line(line)
        # Execute command
        pass

if __name__ == '__main__':
    main()