#!/usr/bin/env python3
"""Utilities for driving ``pysh`` interactively in tests."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from main import PROMPT as DEFAULT_PROMPT, CONTINUATION_PROMPT as DEFAULT_CONTINUATION_PROMPT
except Exception:  # pragma: no cover - fallback when main cannot be imported
    DEFAULT_PROMPT = "pysh> "
    DEFAULT_CONTINUATION_PROMPT = "... "


@dataclass
class CommandResult:
    """Container for command execution output collected from the REPL."""

    stdout: str
    stderr: str
    output: str
    prompt: str


class PyshTester:
    """Lightweight helper for scripting interactions with ``pysh``."""

    QUIESCENT_DELAY = 0.05

    def __init__(
        self,
        executable: Optional[str] = None,
        cwd: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
        startup_timeout: float = 5.0,
    ) -> None:
        self.prompt = DEFAULT_PROMPT
        self.continuation_prompt = DEFAULT_CONTINUATION_PROMPT
        python = executable or sys.executable
        main_script = SRC_DIR / "main.py"
        env_vars = dict(os.environ, PYTHONUNBUFFERED="1")
        if env:
            env_vars.update(env)
        self.proc = subprocess.Popen(
            [python, str(main_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,
            cwd=str(cwd or ROOT),
            env=env_vars,
        )
        if not self.proc.stdin or not self.proc.stdout or not self.proc.stderr:
            raise RuntimeError("Failed to start pysh subprocess with pipes")

        self.stdout_queue: "queue.Queue[str]" = queue.Queue()
        self.stderr_queue: "queue.Queue[str]" = queue.Queue()
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()
        self._last_prompt: Optional[str] = None

        # Consume the initial prompt so subsequent reads start cleanly.
        self._wait_for_prompt(timeout=startup_timeout)

    # ------------------------------------------------------------------
    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        while True:
            chunk = self.proc.stdout.read(1)
            if not chunk:
                break
            self.stdout_queue.put(chunk)

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        while True:
            chunk = self.proc.stderr.read(1)
            if not chunk:
                break
            self.stderr_queue.put(chunk)

    # ------------------------------------------------------------------
    def _match_prompt(self, buffer: str) -> Optional[str]:
        if buffer.endswith(self.continuation_prompt):
            return self.continuation_prompt
        if buffer.endswith(self.prompt):
            return self.prompt
        return None

    def _collect_until_prompt(self, timeout: float) -> tuple[str, str, str]:
        start = time.time()
        stdout_buffer = ""
        stderr_buffer = ""
        candidate_prompt: Optional[str] = None
        last_activity = time.time()

        while time.time() - start < timeout:
            got_chunk = False
            try:
                chunk = self.stdout_queue.get(timeout=0.05)
                stdout_buffer += chunk
                candidate_prompt = self._match_prompt(stdout_buffer) or candidate_prompt
                last_activity = time.time()
                got_chunk = True
            except queue.Empty:
                pass

            try:
                err_chunk = self.stderr_queue.get_nowait()
                stderr_buffer += err_chunk
                last_activity = time.time()
                got_chunk = True
            except queue.Empty:
                pass

            if candidate_prompt and (time.time() - last_activity) >= self.QUIESCENT_DELAY:
                stdout_without_prompt = stdout_buffer[: -len(candidate_prompt)] if candidate_prompt else stdout_buffer
                return stdout_without_prompt, stderr_buffer, candidate_prompt

            if not got_chunk:
                time.sleep(0.01)

        raise TimeoutError("Timed out waiting for pysh prompt")

    def _wait_for_prompt(self, timeout: float = 5.0) -> None:
        stdout_text, stderr_text, prompt = self._collect_until_prompt(timeout)
        # Discard any accidental boot noise but keep last prompt for state.
        self._last_prompt = prompt
        if stdout_text or stderr_text:
            # If pysh printed output before first prompt, stash it for debugging.
            self._boot_output = stdout_text + stderr_text
        else:
            self._boot_output = ""

    # ------------------------------------------------------------------
    def run(self, cmd: str, timeout: float = 5.0) -> CommandResult:
        if self.proc.poll() is not None:
            raise RuntimeError("pysh subprocess has exited; cannot run command")

        # Send the command followed by newline to simulate pressing Enter.
        assert self.proc.stdin is not None
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

        stdout_text, stderr_text, prompt = self._collect_until_prompt(timeout)
        combined = stdout_text + stderr_text
        self._last_prompt = prompt
        return CommandResult(stdout=stdout_text, stderr=stderr_text, output=combined, prompt=prompt)

    # ------------------------------------------------------------------
    def close(self, timeout: float = 2.0) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

    def __enter__(self) -> "PyshTester":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()

    # ------------------------------------------------------------------
    @property
    def last_prompt(self) -> Optional[str]:
        return self._last_prompt