from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional, Dict


class ShellSession:
    """Holds session-wide shell context like environment variables.

    - env: a dictionary snapshot of the current process environment by default.
    - shell: path to the shell binary being used by the session.

    This is where future features (export, unset, aliases, functions) can update
    the environment to persist across commands.
    """

    def __init__(self, shell: str, inherit_env: bool = True) -> None:
        self.shell: str = shell
        self.env: Dict[str, str] = dict(os.environ) if inherit_env else {}

    def get_env(self) -> Dict[str, str]:
        # Return a copy to prevent accidental external mutation
        return dict(self.env)


class CommandRunner:
    """Wrap execution of a single command string via the system shell.

    Lifecycle:
    - Initialize with a command line as typed.
    - Call shell_run() to execute using `<shell> -c <line>`.
    - After running, access exit_code, stdout, stderr.

    Notes:
    - shell_run captures stdout/stderr and then echoes them to the parent
      process's stdout/stderr to approximate shell behavior.
    - For fully interactive TTY programs, a future method can use a pty.
    """

    def __init__(self, line: str, shell: str, env: Optional[Dict[str, str]] = None) -> None:
        self.line: str = line
        self.shell: str = shell
        self.env: Optional[Dict[str, str]] = dict(env) if env is not None else None
        self.exit_code: Optional[int] = None
        self.stdout: Optional[str] = None
        self.stderr: Optional[str] = None

    def shell_run(self) -> int:
        """Run the command through the shell, capturing output and exit code.

        Returns the process exit code and stores it on `self.exit_code`.
        """
        try:
            completed = subprocess.run(
                [self.shell, "-c", self.line],
                capture_output=True,
                text=True,
                env=self.env,
            )
            self.exit_code = completed.returncode
            self.stdout = completed.stdout
            self.stderr = completed.stderr

            # Echo outputs to the terminal to mimic normal shell behavior
            if self.stdout:
                sys.stdout.write(self.stdout)
                sys.stdout.flush()
            if self.stderr:
                sys.stderr.write(self.stderr)
                sys.stderr.flush()

            return self.exit_code
        except KeyboardInterrupt:
            # SIGINT during command
            self.exit_code = 130
            return self.exit_code
        except FileNotFoundError:
            self.stderr = f"pysh: shell not found: {self.shell}\n"
            sys.stderr.write(self.stderr)
            sys.stderr.flush()
            self.exit_code = 127
            return self.exit_code
        except Exception as e:
            self.stderr = f"pysh: error: {e}\n"
            sys.stderr.write(self.stderr)
            sys.stderr.flush()
            self.exit_code = 1
            return self.exit_code
