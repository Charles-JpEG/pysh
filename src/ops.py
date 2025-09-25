from __future__ import annotations

import os
import subprocess
import sys
import ast
from typing import Optional, Dict, List, Tuple, Any


class ShellSession:
    """Holds session-wide shell context like environment variables.

    - env: a dictionary snapshot of the current process environment by default.
    - shell: path to the shell binary being used by the session.

    This is where future features (export, unset, aliases, functions) can update
    the environment to persist across commands.
    """

    def __init__(self, shell: str, inherit_env: bool = True) -> None:
        self.shell: str = shell
        # String-only environment used as base for subprocesses
        self.env: Dict[str, str] = dict(os.environ) if inherit_env else {}
    # Python variable space: holds Python objects defined by the user via assignments
    # Does not include inherited env by default; env is merged at get_env/expansion time
        self.py_vars: Dict[str, Any] = {}
        self.background_jobs: List[List[subprocess.Popen]] = []

    def get_env(self) -> Dict[str, str]:
        # Merge string env with stringified Python vars; Python vars take precedence
        merged = dict(self.env)
        for k, v in self.py_vars.items():
            try:
                merged[k] = str(v)
            except Exception:
                merged[k] = repr(v)
        return merged

    # --- Python variable helpers ---
    def get_var(self, name: str) -> Optional[Any]:
        if name in self.py_vars:
            return self.py_vars[name]
        return self.env.get(name)

    def set_var(self, name: str, value: Any) -> None:
        self.py_vars[name] = value

    def unset_var(self, name: str) -> None:
        if name in self.py_vars:
            del self.py_vars[name]


def _expand_vars_in_line(line: str, session: ShellSession) -> str:
    """Expand $var and ${var} using session vars/env.

    Rules (pysh simplified):
    - No expansion inside single quotes '...'
    - Expansion allowed in unquoted and double-quoted contexts
    - Backslash escapes next char (so \$ yields literal $) outside single quotes
    - Undefined vars expand to empty string
    """
    out: List[str] = []
    i = 0
    n = len(line)
    in_single = False
    in_double = False
    while i < n:
        ch = line[i]
        if ch == "'":
            in_single = not in_single if not in_double else in_single
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = not in_double if not in_single else in_double
            out.append(ch)
            i += 1
            continue
        if ch == '\\' and not in_single:
            # Escape next character (if any)
            if i + 1 < n:
                out.append(line[i + 1])
                i += 2
                continue
            else:
                out.append('\\')
                i += 1
                continue
        if ch == '$' and not in_single:
            # Parse variable name
            if i + 1 < n and line[i + 1] == '{':
                # ${var}
                j = i + 2
                name_chars: List[str] = []
                while j < n and line[j] != '}':
                    name_chars.append(line[j])
                    j += 1
                if j < n and line[j] == '}':
                    var_name = ''.join(name_chars)
                    val = session.get_var(var_name)
                    out.append('' if val is None else str(val))
                    i = j + 1
                    continue
                else:
                    # No closing }, treat literally
                    out.append('$')
                    i += 1
                    continue
            else:
                # $var_name
                j = i + 1
                if j < n and ((line[j] == '_' or line[j].isalpha())):
                    name_chars: List[str] = []
                    while j < n and (line[j] == '_' or line[j].isalnum()):
                        name_chars.append(line[j])
                        j += 1
                    var_name = ''.join(name_chars)
                    val = session.get_var(var_name)
                    out.append('' if val is None else str(val))
                    i = j
                    continue
                else:
                    # Not a valid var expansion ($ followed by non-name)
                    out.append('$')
                    i += 1
                    continue
        # default
        out.append(ch)
        i += 1
    return ''.join(out)


def _try_python_assignment(line: str, session: ShellSession) -> Optional[int]:
    """Detect and execute simple Python assignments like: x = 10, a, b = (1, 2).

    Returns an int exit code (0/1) if handled, else None if the line is not an assignment.
    """
    try:
        tree = ast.parse(line, mode='exec')
    except SyntaxError:
        return None
    # Only handle a single Assign statement
    if not tree.body or len(tree.body) != 1:
        return None
    node = tree.body[0]
    if not isinstance(node, ast.Assign):
        return None

    # Collect target names
    names: List[str] = []
    def collect(t: ast.AST) -> None:
        if isinstance(t, ast.Name):
            names.append(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            for elt in t.elts:
                collect(elt)
        else:
            # Unsupported complex target like attribute or subscription
            raise SyntaxError("unsupported assignment target")

    try:
        for tgt in node.targets:
            collect(tgt)
    except SyntaxError:
        return None

    # Build an execution local namespace seeded with both env and current py vars
    # so RHS can reference them.
    exec_locals: Dict[str, Any] = dict(session.env)
    exec_locals.update(session.py_vars)
    try:
        compiled = compile(tree, '<pysh>', 'exec')
        exec(compiled, {"__builtins__": __builtins__}, exec_locals)
        # Pull assigned values back into python vars
        for nm in names:
            if nm in exec_locals:
                session.set_var(nm, exec_locals[nm])
        return 0
    except Exception as e:
        sys.stderr.write(f"pysh: python error: {e}\n")
        sys.stderr.flush()
        return 1


def try_python(line: str, session: ShellSession) -> Optional[int]:
    """Public API: Execute Python statements/expressions.

    - If line is valid Python (imports, assignments, general statements), execute it with
      access to prior Python vars and env values (as strings). Assignments update session.py_vars.
    - If it's a single expression, evaluate and print its repr() to stdout.
    - On SyntaxError, return None (so shell path can handle it). On other errors, print and return 1.
    """
    try:
        tree = ast.parse(line, mode='exec')
    except SyntaxError:
        return None

    exec_locals: Dict[str, Any] = dict(session.env)
    exec_locals.update(session.py_vars)
    try:
        # If single expression, evaluate and print
        if len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr):
            expr = ast.Expression(tree.body[0].value)
            val = eval(compile(expr, '<pysh>', 'eval'), {"__builtins__": __builtins__}, exec_locals)
            if val is not None:
                sys.stdout.write(repr(val) + "\n")
                sys.stdout.flush()
            return 0

        # General statements (assignments, imports, etc.)
        code = compile(tree, '<pysh>', 'exec')
        exec(code, {"__builtins__": __builtins__}, exec_locals)

        # Sync back any names that look newly set/changed compared to env baseline
        for k, v in exec_locals.items():
            if k in ("__builtins__",):
                continue
            # Only store Python identifiers
            if k and (k[0] == '_' or not (k[0].isalpha() or k[0] == '_')):
                continue
            session.py_vars[k] = v
        return 0
    except Exception as e:
        sys.stderr.write(f"pysh(py): {e}\n")
        sys.stderr.flush()
        return 1


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


# --------- Operator-aware parsing and execution ---------

class Redirection:
    def __init__(self, fd: int, op: str, target: str | int) -> None:
        # op in { '>', '>>', '<', 'dup' } ; target is filename for >,>>,< and int for dup (e.g., 2>&1)
        self.fd = fd
        self.op = op
        self.target = target


class SimpleCommand:
    def __init__(self, argv: List[str]) -> None:
        self.argv = argv
        self.redirs: List[Redirection] = []


class Pipeline:
    def __init__(self, commands: List[SimpleCommand], background: bool = False) -> None:
        self.commands = commands
        self.background = background


class SequenceUnit:
    def __init__(self, pipeline: Pipeline, next_op: Optional[str]) -> None:
        # next_op in {';', '&&', '||', None}
        self.pipeline = pipeline
        self.next_op = next_op


def _tokenize(line: str) -> List[str]:
    import shlex as _shlex

    # Split punctuation so operators are separate tokens
    lex = _shlex.shlex(line, posix=True, punctuation_chars='|&;<>')
    lex.whitespace_split = True
    tokens = list(lex)

    # Combine multi-char operators: &&, ||, >>, <<, 2>&1 patterns will be handled in parser
    combined: List[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if i + 1 < len(tokens):
            t2 = tokens[i + 1]
            if t == '&' and t2 == '&':
                combined.append('&&'); i += 2; continue
            if t == '|' and t2 == '|':
                combined.append('||'); i += 2; continue
            if t == '>' and t2 == '>':
                combined.append('>>'); i += 2; continue
            if t == '<' and t2 == '<':
                combined.append('<<'); i += 2; continue
            if t == '>' and t2 == '&':
                combined.append('>&'); i += 2; continue
        combined.append(t)
        i += 1
    return combined


def has_operators(line: str) -> bool:
    # Determine if line contains shell operators that we handle
    ops = {'|', '&&', '||', ';', '&', '>', '>>', '<'}
    toks = _tokenize(line)
    return any(t in ops or (t.isdigit() and i + 1 < len(toks) and toks[i + 1] in ('>', '>>', '>&')) for i, t in enumerate(toks))


def _parse_redirection(tokens: List[str], i: int, cmd: SimpleCommand) -> int:
    # Supports: > file, >> file, < file, [n]> file, [n]>> file, 2>&1
    # tokens[i] is either '>', '>>', '<' or an int fd followed by those
    def is_int(s: str) -> bool:
        return s.isdigit()

    fd: int = 1
    op = tokens[i]
    j = i + 1
    if is_int(op):
        # numeric fd specified
        if j >= len(tokens):
            raise ValueError("redirection missing operator after fd")
        fd = int(op)
        op = tokens[j]
        j += 1

    # Dup redirection: n>&m must be checked before normal file redirection
    if op == '>&':
        if j >= len(tokens) or not is_int(tokens[j]):
            raise ValueError("dup redirection requires numeric fd target, e.g., 2>&1")
        to_fd = int(tokens[j])
        cmd.redirs.append(Redirection(fd, 'dup', to_fd))
        return j + 1
    if op == '>' and j < len(tokens) and tokens[j] == '&':
        if j + 1 >= len(tokens) or not is_int(tokens[j + 1]):
            raise ValueError("dup redirection requires numeric fd target, e.g., 2>&1")
        to_fd = int(tokens[j + 1])
        cmd.redirs.append(Redirection(fd, 'dup', to_fd))
        return j + 2

    if op in ('>', '>>', '<'):
        if j >= len(tokens):
            raise ValueError("redirection missing target")
        target = tokens[j]
        cmd.redirs.append(Redirection(fd, op, target))
        return j + 1

    raise ValueError(f"unsupported redirection near: {' '.join(tokens[i:j+1])}")


def _parse_simple(tokens: List[str], i: int) -> Tuple[SimpleCommand, int]:
    argv: List[str] = []
    while i < len(tokens):
        t = tokens[i]
        if t in ('|', '&&', '||', ';', '&'):
            break
        # redirection starts: either operator or leading numeric fd
        if t in ('>', '>>', '<') or t.isdigit():
            i = _parse_redirection(tokens, i, SimpleCommand(argv) if False else None)  # type: ignore
            # The above line is placeholder to satisfy typing in mypy-like tools; will be replaced below
        else:
            argv.append(t)
            i += 1
        # To actually record redirs on the current command, we need the command object.
    # Now reconstruct by walking again to attach redirs; simpler: parse in one pass with a command object.

    # Re-parse for real to attach redirs
    cmd = SimpleCommand(argv=[])
    i2 = i - len(argv)
    # We need to re-walk from start position; easier approach: second pass from a saved start pointer
    # Let's implement properly in a single pass instead of above.


def _parse_simple_proper(tokens: List[str], i: int) -> Tuple[SimpleCommand, int]:
    cmd = SimpleCommand(argv=[])
    while i < len(tokens):
        t = tokens[i]
        if t in ('|', '&&', '||', ';', '&'):
            break
        if t in ('>', '>>', '<', '>&'):
            i = _parse_redirection(tokens, i, cmd)
        elif t.isdigit():
            # Interpret as fd redirection only if followed by a redirection operator
            if i + 1 < len(tokens) and tokens[i + 1] in ('>', '>>', '<', '>&'):
                i = _parse_redirection(tokens, i, cmd)
            else:
                cmd.argv.append(t)
                i += 1
        else:
            cmd.argv.append(t)
            i += 1
    return cmd, i


def _parse_pipeline(tokens: List[str], i: int) -> Tuple[Pipeline, int]:
    commands: List[SimpleCommand] = []
    cmd, i = _parse_simple_proper(tokens, i)
    if not cmd.argv and not cmd.redirs:
        raise ValueError("empty command")
    commands.append(cmd)
    while i < len(tokens) and tokens[i] == '|':
        i += 1
        cmd, i = _parse_simple_proper(tokens, i)
        if not cmd.argv:
            raise ValueError("missing command after '|'")
        commands.append(cmd)

    background = False
    if i < len(tokens) and tokens[i] == '&':
        background = True
        i += 1

    return Pipeline(commands, background), i


def _parse_sequence(tokens: List[str]) -> List[SequenceUnit]:
    i = 0
    units: List[SequenceUnit] = []
    while i < len(tokens):
        pipeline, i = _parse_pipeline(tokens, i)
        next_op: Optional[str] = None
        if i < len(tokens) and tokens[i] in (';', '&&', '||'):
            next_op = tokens[i]
            i += 1
        units.append(SequenceUnit(pipeline, next_op))
    return units


def _apply_redirections(cmd: SimpleCommand) -> Tuple[Optional[int], Optional[int], Optional[int], List]:
    # Returns (stdin_fd, stdout_fd, stderr_fd, closer_list)
    stdin_fd = None
    stdout_fd = None
    stderr_fd = None
    closers: List = []

    # Track dup stderr to stdout
    dup_stderr_to_stdout = False
    for r in cmd.redirs:
        if r.op == '<':
            f = open(r.target, 'rb')
            closers.append(f)
            stdin_fd = f.fileno()
        elif r.op == '>':
            f = open(r.target, 'wb')
            closers.append(f)
            if r.fd == 1:
                stdout_fd = f.fileno()
            elif r.fd == 2:
                stderr_fd = f.fileno()
        elif r.op == '>>':
            f = open(r.target, 'ab')
            closers.append(f)
            if r.fd == 1:
                stdout_fd = f.fileno()
            elif r.fd == 2:
                stderr_fd = f.fileno()
        elif r.op == 'dup':
            if r.fd == 2 and isinstance(r.target, int) and r.target == 1:
                dup_stderr_to_stdout = True
            else:
                # Minimal support: only 2>&1
                raise ValueError("only 2>&1 is supported for dup redirection right now")
        else:
            raise ValueError(f"unsupported redirection: {r.op}")

    return stdin_fd, stdout_fd, (subprocess.STDOUT if dup_stderr_to_stdout else stderr_fd), closers


def _exec_pipeline(p: Pipeline, session: ShellSession) -> int:
    procs: List[subprocess.Popen] = []
    prev_stdout = None
    open_handles: List = []
    try:
        for idx, cmd in enumerate(p.commands):
            stdin_fd, stdout_fd, stderr_fd, closers = _apply_redirections(cmd)
            open_handles.extend(closers)

            stdin = prev_stdout if prev_stdout is not None else (stdin_fd if stdin_fd is not None else None)
            # For intermediate commands in a pipeline, stdout must be a PIPE unless explicitly redirected
            if idx < len(p.commands) - 1:
                stdout = subprocess.PIPE
            else:
                stdout = stdout_fd if stdout_fd is not None else None

            stderr = stderr_fd if stderr_fd is not None else None

            # Spec tweak: default grep engine is PCRE (-P) unless an engine flag is provided
            if cmd.argv:
                prog = os.path.basename(cmd.argv[0])
                if prog == 'grep':
                    engine_flags = {'-E', '--extended-regexp', '-F', '--fixed-strings', '-G', '--basic-regexp', '-P', '--perl-regexp'}
                    if not any(a in engine_flags for a in cmd.argv[1:]):
                        cmd.argv.insert(1, '-P')

            proc = subprocess.Popen(
                cmd.argv,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                env=session.get_env(),
            )
            procs.append(proc)

            # If we created a pipe, hook next command's stdin to this stdout
            if proc.stdout is not None:
                prev_stdout = proc.stdout
            else:
                prev_stdout = None

        if p.background:
            session.background_jobs.append(procs)
            return 0

        # Foreground: wait for all; exit code from last
        exit_code = 0
        for proc in procs[:-1]:
            proc.wait()
        if procs:
            exit_code = procs[-1].wait()
        return exit_code
    finally:
        # Close any open file handles we created for redirections
        for h in open_handles:
            try:
                h.close()
            except Exception:
                pass
        # Close any pipe endpoints we inherited in parent
        for proc in procs:
            if proc.stdout is not None:
                try:
                    proc.stdout.close()
                except Exception:
                    pass


def _exec_sequence(units: List[SequenceUnit], session: ShellSession) -> int:
    last = 0
    i = 0
    while i < len(units):
        u = units[i]
        ec = _exec_pipeline(u.pipeline, session)
        last = ec
        # Decide whether to execute the next unit depending on the operator attached to this one
        if u.next_op == '&&' and ec != 0:
            # Skip the next unit
            i += 2
            continue
        if u.next_op == '||' and ec == 0:
            # Skip the next unit
            i += 2
            continue
        i += 1
    return last


def execute_line(line: str, session: ShellSession) -> int:
    # Python assignment handling
    handled = _try_python_assignment(line, session)
    if handled is not None:
        return handled

    # Expand variables before parsing/execution so pipelines and simple commands see expanded args
    line = _expand_vars_in_line(line, session)
    tokens = _tokenize(line)
    if not tokens:
        return 0
    units = _parse_sequence(tokens)
    return _exec_sequence(units, session)


# Public helper for the REPL to expand variables in simple commands before delegating to the system shell
def expand_line(line: str, session: ShellSession) -> str:
    return _expand_vars_in_line(line, session)
