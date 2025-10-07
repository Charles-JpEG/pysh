from __future__ import annotations

import os
import subprocess
import sys
import ast
import shutil
import io
from dataclasses import dataclass
from contextlib import ExitStack, redirect_stdout, redirect_stderr, nullcontext
from typing import Optional, Dict, List, Tuple, Any
import codeop


# ---- Token model for parsing (word vs operator) ----
class Token:
    def __init__(self, kind: str, value: str, quoting: str = 'unquoted') -> None:
        # kind in { 'WORD', 'OP' }
        # quoting in { 'unquoted', 'single', 'double' }
        self.kind = kind
        self.value = value
        self.quoting = quoting

    def __repr__(self) -> str:
        return f"Token({self.kind!r}, {self.value!r}, {self.quoting!r})"


class ShellSession:
    """Holds session-wide shell context like environment variables."""

    def __init__(self, shell: str, inherit_env: bool = True) -> None:
        self.shell: str = shell
        # String-only environment used as base for subprocesses
        self.env: Dict[str, str] = dict(os.environ) if inherit_env else {}
        # Python variable space: holds Python objects defined by the user via assignments
        # Does not include inherited env by default; env is merged at get_env/expansion time
        self.py_vars: Dict[str, Any] = {}
        self.background_jobs: List[List[subprocess.Popen]] = []
        # Multi-line Python code accumulation and indentation handling
        self.multi_line_buffer: List[str] = []
        self.in_multi_line: bool = False
        self.command_compiler = codeop.CommandCompiler()
        self.default_indent_unit: str = os.environ.get("PYSH_INDENT", "    ")
        self.current_indent_level: int = 0

    def get_env(self) -> Dict[str, str]:
        # Merge string env with stringified Python vars; Python vars take precedence
        merged = dict(self.env)
        for k, v in self.py_vars.items():
            try:
                merged[k] = str(v)
            except Exception:
                merged[k] = repr(v)
        return merged

    def get_indent_unit(self) -> str:
        indent_override = self.py_vars.get("__pysh_indent")
        if isinstance(indent_override, str):
            return indent_override
        env_indent = self.env.get("PYSH_INDENT")
        if isinstance(env_indent, str) and env_indent:
            return env_indent
        return self.default_indent_unit

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


# Commands that are "preserved" and must resolve to system commands when invoked.
GUARANTEED_COMMANDS: set[str] = {
    'cd', 'ls', 'pwd', 'mkdir', 'rmdir', 'rm', 'cp', 'mv', 'find', 'basename', 'dirname',
    'echo', 'cat', 'head', 'tail', 'wc', 'grep', 'sort', 'uniq', 'cut',
    'date', 'uname', 'ps', 'which', 'env', 'fd', 'rg'
}


def _expand_vars_in_line(line: str, session: ShellSession, *, force_double: bool = False) -> str:
    """Expand $var and ${var} using session vars/env.

    Rules (pysh simplified):
    - No expansion inside single quotes '...'
    - Expansion allowed in unquoted and double-quoted contexts
    - Backslash escapes next char (so \\$ yields literal $) outside single quotes
    - Undefined vars expand to empty string
    """
    out: List[str] = []
    i = 0
    n = len(line)
    in_single = False
    in_double = force_double
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
            # For expansion, only consume backslash when escaping a dollar sign.
            # Otherwise, preserve the backslash for the tokenizer to handle.
            if i + 1 < n and line[i + 1] == '$':
                out.append('$')
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


_DEDENT_PREFIXES: Tuple[str, ...] = ("elif", "else", "except", "finally")


def _count_indent_units(line: str, indent_unit: str) -> int:
    if not indent_unit:
        return 0
    unit_len = len(indent_unit)
    count = 0
    pos = 0
    while line.startswith(indent_unit, pos):
        count += 1
        pos += unit_len
    return count


def _start_multiline_block(session: ShellSession, first_line: str) -> None:
    session.in_multi_line = True
    session.multi_line_buffer = [first_line]
    indent_unit = session.get_indent_unit()
    indent_count = _count_indent_units(first_line, indent_unit)
    stripped = first_line.strip()
    if stripped and stripped.endswith(":") and not stripped.startswith("#"):
        session.current_indent_level = indent_count + 1
    else:
        session.current_indent_level = indent_count
    session.command_compiler = codeop.CommandCompiler()


def _append_multiline_line(session: ShellSession, line: str) -> None:
    indent_unit = session.get_indent_unit()
    if not line:
        session.multi_line_buffer.append("")
        return

    stripped = line.lstrip()
    manual_indent = len(line) != len(stripped)
    target_level = session.current_indent_level

    if indent_unit and not manual_indent:
        lowered = stripped
        if any(lowered.startswith(prefix) for prefix in _DEDENT_PREFIXES) and target_level > 0:
            target_level -= 1
        line_to_store = indent_unit * target_level + stripped
    else:
        line_to_store = line

    session.multi_line_buffer.append(line_to_store)

    if indent_unit:
        indent_units = _count_indent_units(line_to_store, indent_unit)
    else:
        indent_units = 0

    stripped_line = line_to_store.strip()
    if stripped_line and stripped_line.endswith(":") and not stripped_line.startswith("#"):
        session.current_indent_level = indent_units + 1
    else:
        session.current_indent_level = indent_units


def _expand_word(word: str, quoting: str, session: ShellSession) -> str:
    # Handle sentinel markers injected during tokenization
    if word.startswith("\x00S"):
        # Single-quoted: return literally, no expansion
        return word[2:]
    force_double = False
    if word.startswith("\x00D"):
        force_double = True
        word = word[2:]
    # Expand command substitutions first, then variables
    s = _expand_command_substitutions(word, session, for_python=False)
    s = _expand_vars_in_line(s, session, force_double=force_double)
    # Expand ~ at start of unquoted words
    if quoting == 'unquoted' and s.startswith('~'):
        s = os.path.expanduser(s)
    return s


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

    # Disallow assigning to names that are preserved commands
    for nm in names:
        if nm in GUARANTEED_COMMANDS:
            sys.stderr.write(f"pysh: cannot assign to preserved command name: {nm}\n")
            sys.stderr.flush()
            return 1

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


def _pysh_exec_shell_helper(command: str, session: ShellSession) -> int:
    """Helper function available in Python execution context to run shell commands."""
    try:
        # Expand variables and command substitutions for shell context
        expanded_command = _expand_command_substitutions(command, session, for_python=False)
        
        # Parse and execute as shell command
        tokens = _tokenize(expanded_command)
        if not tokens:
            return 0
        
        units = _parse_sequence(tokens)
        return _exec_sequence(units, session)
    except Exception as e:
        sys.stderr.write(f"pysh: error executing shell command '{command}': {e}\n")
        sys.stderr.flush()
        return 1


def try_python(line: str, session: ShellSession) -> Optional[int]:
    """Public API: Execute arbitrary Python code, updating session.py_vars.

    Returns exit code if executed (0 on success, 1 on error), or None if parsing fails.
    Intended for explicit Python execution (REPL or tests). Command selection logic lives in execute_line.
    """
    try:
        tree = ast.parse(line, mode='exec')
    except SyntaxError:
        return None

    # Block assigning to preserved command names anywhere in the top-level code
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            # Collect target names
            names: List[str] = []
            def collect(t: ast.AST) -> None:
                if isinstance(t, ast.Name):
                    names.append(t.id)
                elif isinstance(t, (ast.Tuple, ast.List)):
                    for elt in t.elts:
                        collect(elt)
            try:
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        collect(t)
                else:
                    collect(node.target)  # type: ignore[attr-defined]
            except Exception:
                pass
            for nm in names:
                if nm in GUARANTEED_COMMANDS:
                    sys.stderr.write(f"pysh: cannot assign to preserved command name: {nm}\n")
                    sys.stderr.flush()
                    return 1

    # Handle expression statements (like bare variable names) by evaluating and printing
    if len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr):
        expr = tree.body[0].value
        eval_locals: Dict[str, Any] = dict(session.env)
        eval_locals.update(session.py_vars)
        try:
            val = eval(compile(ast.Expression(body=expr), '<pysh>', 'eval'), {"__builtins__": __builtins__}, eval_locals)
            # Print the value like REPL; update last value to underscore variable _
            try:
                session.py_vars['_'] = val
            except Exception:
                pass
            if val is not None:
                sys.stdout.write(str(val) + "\n")
                sys.stdout.flush()
            return 0
        except Exception as e:
            sys.stderr.write(f"pysh(py-eval): {e}\n")
            sys.stderr.flush()
            return 1

    exec_locals: Dict[str, Any] = dict(session.env)
    exec_locals.update(session.py_vars)
    
    # Add pysh helper functions to the execution context
    def pysh_exec_shell_dynamic(cmd):
        """Execute shell command with access to caller's local variables (function parameters)."""
        import sys
        # Get the caller's frame (the function calling __pysh_exec_shell)
        frame = sys._getframe(1)
        caller_locals = frame.f_locals
        
        # Temporarily update session.py_vars with caller's locals (includes function parameters)
        original_vars = dict(session.py_vars)
        session.py_vars.update(caller_locals)
        try:
            return _pysh_exec_shell_helper(cmd, session)
        finally:
            # Restore original py_vars, but keep any new assignments
            for k, v in session.py_vars.items():
                if k not in original_vars or original_vars[k] != v:
                    original_vars[k] = v
            session.py_vars = original_vars
    
    # Create exec_globals with __pysh_exec_shell and session variables
    # so functions can access both shell execution context and session variables
    exec_globals = dict(session.py_vars)
    exec_globals["__builtins__"] = __builtins__
    exec_globals["__pysh_exec_shell"] = pysh_exec_shell_dynamic
    
    try:
        code = compile(tree, '<pysh>', 'exec')
        exec(code, exec_globals, exec_locals)
        # Sync back names (including imports)
        for k, v in exec_locals.items():
            if k in ("__builtins__", "__pysh_exec_shell"):
                continue
            if not k or not (k[0].isalpha() or k[0] == '_'):
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
    def __init__(self, argv: List[Tuple[str, str]]) -> None:
        self.argv = argv  # list of (value, quoting)
        self.redirs: List[Redirection] = []


@dataclass
class ExpandedCommand:
    argv: List[str]
    redirs: List[Redirection]
    is_python: bool
    python_code: Optional[str] = None


class Pipeline:
    def __init__(self, commands: List[SimpleCommand], background: bool = False) -> None:
        self.commands = commands
        self.background = background


class SequenceUnit:
    def __init__(self, pipeline: Pipeline, next_op: Optional[str]) -> None:
        # next_op in {';', '&&', '||', None}
        self.pipeline = pipeline
        self.next_op = next_op


def _tokenize(line: str) -> List[Token]:
    tokens: List[Token] = []
    buf: List[str] = []
    i = 0
    n = len(line)
    in_single = False
    in_double = False
    # Track context for current buffer to mark fully quoted tokens
    buf_seen_single = False
    buf_seen_double = False
    buf_seen_unquoted = False

    def flush_buf() -> None:
        nonlocal buf_seen_single, buf_seen_double, buf_seen_unquoted
        if buf:
            val = ''.join(buf)
            # Determine quoting
            quoting = 'unquoted'
            if buf_seen_single and not buf_seen_double and not buf_seen_unquoted:
                quoting = 'single'
                val = '\x00S' + val
            elif buf_seen_double and not buf_seen_single and not buf_seen_unquoted:
                quoting = 'double'
                val = '\x00D' + val
            tokens.append(Token('WORD', val, quoting))
            buf.clear()
            buf_seen_single = buf_seen_double = buf_seen_unquoted = False

    while i < n:
        ch = line[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            i += 1
            continue
        if ch == '\\' and not in_single:
            # Escape next character
            if i + 1 < n:
                nxt = line[i + 1]
                # Preserve escape before '$' so expansion can detect it
                if nxt == '$':
                    buf.append('\\')
                    buf.append('$')
                else:
                    buf.append(nxt)
                if in_single:
                    buf_seen_single = True
                elif in_double:
                    buf_seen_double = True
                else:
                    buf_seen_unquoted = True
                i += 2
                continue
            else:
                buf.append('\\')
                if in_single:
                    buf_seen_single = True
                elif in_double:
                    buf_seen_double = True
                else:
                    buf_seen_unquoted = True
                i += 1
                continue
        if not in_single and not in_double:
            # Whitespace separates arguments
            if ch.isspace():
                flush_buf()
                i += 1
                continue
            # Operators
            if ch in ('|', '&', ';', '<', '>'):
                flush_buf()
                # Lookahead for two-char operators
                if i + 1 < n:
                    nxt = line[i + 1]
                    if ch == '&' and nxt == '&':
                        tokens.append(Token('OP', '&&')); i += 2; continue
                    if ch == '|' and nxt == '|':
                        tokens.append(Token('OP', '||')); i += 2; continue
                    if ch == '>' and nxt == '>':
                        tokens.append(Token('OP', '>>')); i += 2; continue
                    if ch == '<' and nxt == '<':
                        tokens.append(Token('OP', '<<')); i += 2; continue
                    if ch == '>' and nxt == '&':
                        tokens.append(Token('OP', '>&')); i += 2; continue
                tokens.append(Token('OP', ch))
                i += 1
                continue
        # Default: accumulate character
        buf.append(ch)
        if in_single:
            buf_seen_single = True
        elif in_double:
            buf_seen_double = True
        else:
            buf_seen_unquoted = True
        i += 1

    flush_buf()
    return tokens


def _expand_command_substitutions(line: str, session: ShellSession, *, for_python: bool) -> str:
    """Expand $(...) by executing the inner text via the system shell.

    - Respects quoting: disabled in single quotes; allowed in double quotes and unquoted.
    - Supports nested parentheses within $(...).
    - Trims trailing newlines from the command output (shell-like behavior).
    - When for_python=True, inserts a Python string literal representing the output.
      When for_python=False, inserts the raw text (no further quoting is added).
    """
    out: List[str] = []
    i = 0
    n = len(line)
    in_single = False
    in_double = False

    while i < n:
        ch = line[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            i += 1
            continue
        if ch == '$' and i + 1 < n and line[i + 1] == '(' and not in_single:
            # find matching closing ')', handle nesting and escapes
            j = i + 2
            depth = 1
            while j < n:
                c = line[j]
                if c == '\\' and j + 1 < n:
                    j += 2
                    continue
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j >= n or depth != 0:
                # Unmatched, treat '$' literally
                out.append('$')
                i += 1
                continue
            inner = line[i + 2:j]
            try:
                completed = subprocess.run(
                    [session.shell, '-c', inner],
                    capture_output=True,
                    text=True,
                    env=session.get_env(),
                )
                subst = completed.stdout.rstrip('\n')
            except Exception as e:
                subst = f"<pysh-error:{e}>"

            if for_python:
                # Insert as Python string literal
                out.append(repr(subst))
            else:
                out.append(subst)
            i = j + 1
            continue
        # default
        out.append(ch)
        i += 1
    return ''.join(out)


def has_operators(line: str) -> bool:
    # Quote-aware scan for pipe/and/or/sequence/redirection via typed tokens
    tokens = _tokenize(line)
    for t in tokens:
        if t.kind == 'OP':
            if t.value in {'|', '&&', '||', ';', '&', '>', '>>', '<', '>&'}:
                return True
    return False


def _parse_redirection(tokens: List[Token], i: int, cmd: SimpleCommand) -> int:
    # Supports: > file, >> file, < file, [n]> file, [n]>> file, 2>&1
    # tokens[i] is either '>', '>>', '<' or an int fd followed by those
    def is_int_tok(tok: Token) -> bool:
        return tok.kind == 'WORD' and tok.value.isdigit()

    fd: int = 1
    op_tok = tokens[i]
    j = i + 1
    if is_int_tok(op_tok):
        # numeric fd specified
        if j >= len(tokens):
            raise ValueError("redirection missing operator after fd")
        fd = int(op_tok.value)
        op_tok = tokens[j]
        j += 1

    # Dup redirection: n>&m must be checked before normal file redirection
    if op_tok.kind == 'OP' and op_tok.value == '>&':
        if j >= len(tokens) or not is_int_tok(tokens[j]):
            raise ValueError("dup redirection requires numeric fd target, e.g., 2>&1")
        to_fd = int(tokens[j].value)
        cmd.redirs.append(Redirection(fd, 'dup', to_fd))
        return j + 1
    if op_tok.kind == 'OP' and op_tok.value == '>' and j < len(tokens) and tokens[j].kind == 'OP' and tokens[j].value == '&':
        if j + 1 >= len(tokens) or not is_int_tok(tokens[j + 1]):
            raise ValueError("dup redirection requires numeric fd target, e.g., 2>&1")
        to_fd = int(tokens[j + 1].value)
        cmd.redirs.append(Redirection(fd, 'dup', to_fd))
        return j + 2
    # Allow spaced form: n > & m
    if op_tok.kind == 'OP' and op_tok.value == '>' and j + 1 < len(tokens) and tokens[j].kind == 'OP' and tokens[j].value == '&' and is_int_tok(tokens[j + 1]):
        to_fd = int(tokens[j + 1].value)
        cmd.redirs.append(Redirection(fd, 'dup', to_fd))
        return j + 2

    if op_tok.kind == 'OP' and op_tok.value in ('>', '>>', '<'):
        if j >= len(tokens):
            raise ValueError("redirection missing target")
        target_tok = tokens[j]
        cmd.redirs.append(Redirection(fd, op_tok.value, target_tok.value))
        return j + 1

    raise ValueError(f"unsupported redirection near: {' '.join(t.value for t in tokens[i:j+1])}")


def _parse_simple(tokens: List[Token], i: int) -> Tuple[SimpleCommand, int]:
    argv: List[str] = []
    while i < len(tokens):
        t = tokens[i]
        if t.kind == 'OP' and t.value in ('|', '&&', '||', ';', '&'):
            break
        # redirection starts: either operator or leading numeric fd
        if (t.kind == 'OP' and t.value in ('>', '>>', '<')) or (t.kind == 'WORD' and t.value.isdigit()):
            i = _parse_redirection(tokens, i, SimpleCommand(argv) if False else None)  # type: ignore
            # The above line is placeholder to satisfy typing in mypy-like tools; will be replaced below
        else:
            argv.append(t.value)
            i += 1
        # To actually record redirs on the current command, we need the command object.
    # Now reconstruct by walking again to attach redirs; simpler: parse in one pass with a command object.

    # Re-parse for real to attach redirs
    cmd = SimpleCommand(argv=[])
    i2 = i - len(argv)
    # We need to re-walk from start position; easier approach: second pass from a saved start pointer
    # Let's implement properly in a single pass instead of above.


def _parse_simple_proper(tokens: List[Token], i: int) -> Tuple[SimpleCommand, int]:
    cmd = SimpleCommand(argv=[])
    while i < len(tokens):
        t = tokens[i]
        if t.kind == 'OP' and t.value in ('|', '&&', '||', ';', '&'):
            break
        if t.kind == 'OP' and t.value in ('>', '>>', '<', '>&'):
            i = _parse_redirection(tokens, i, cmd)
        elif t.kind == 'WORD' and t.value.isdigit():
            # Interpret as fd redirection only for dup syntax (n>&m).
            # Do NOT treat a bare number before '>' as fd (e.g., 'echo 10 > f')
            if i + 1 < len(tokens) and (
                (tokens[i + 1].kind == 'OP' and tokens[i + 1].value in ('>&',)) or
                (tokens[i + 1].kind == 'OP' and tokens[i + 1].value == '>' and i + 2 < len(tokens) and tokens[i + 2].kind == 'OP' and tokens[i + 2].value == '&')
            ):
                i = _parse_redirection(tokens, i, cmd)
            else:
                cmd.argv.append((t.value, t.quoting))
                i += 1
        else:
            cmd.argv.append((t.value, t.quoting))
            i += 1
    return cmd, i


def _parse_pipeline(tokens: List[Token], i: int) -> Tuple[Pipeline, int]:
    commands: List[SimpleCommand] = []
    cmd, i = _parse_simple_proper(tokens, i)
    if not cmd.argv and not cmd.redirs:
        raise ValueError("empty command")
    commands.append(cmd)
    while i < len(tokens) and tokens[i].kind == 'OP' and tokens[i].value == '|':
        i += 1
        cmd, i = _parse_simple_proper(tokens, i)
        if not cmd.argv:
            raise ValueError("missing command after '|'")
        commands.append(cmd)

    background = False
    if i < len(tokens) and tokens[i].kind == 'OP' and tokens[i].value == '&':
        background = True
        i += 1

    return Pipeline(commands, background), i


def _parse_sequence(tokens: List[Token]) -> List[SequenceUnit]:
    i = 0
    units: List[SequenceUnit] = []
    while i < len(tokens):
        pipeline, i = _parse_pipeline(tokens, i)
        next_op: Optional[str] = None
        if i < len(tokens) and tokens[i].kind == 'OP' and tokens[i].value in (';', '&&', '||'):
            next_op = tokens[i].value
            i += 1
        units.append(SequenceUnit(pipeline, next_op))
    return units


def _apply_redirections(cmd: SimpleCommand) -> Tuple[Optional[int], Optional[int], Optional[int], List]:
    # Returns (stdin_fd, stdout_fd, stderr_fd, closer_list)
    stdin_fd = None
    stdout_fd = None
    stderr_fd = None
    closers: List = []

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
                stderr_fd = stdout_fd
            else:
                # Minimal support: only 2>&1
                raise ValueError("only 2>&1 is supported for dup redirection right now")
        else:
            raise ValueError(f"unsupported redirection: {r.op}")

    return stdin_fd, stdout_fd, stderr_fd, closers


def _reconstruct_python_source(argv_tokens: List[Tuple[str, str]]) -> str:
    parts: List[str] = []
    for value, quoting in argv_tokens:
        if value.startswith("\x00S"):
            parts.append("'" + value[2:] + "'")
        elif value.startswith("\x00D"):
            parts.append('"' + value[2:] + '"')
        else:
            parts.append(value)
    return ' '.join(parts)


def _should_treat_as_python(shell_argv: List[str], python_code: str, session: ShellSession) -> bool:
    if not shell_argv:
        return bool(python_code.strip())
    cmd_name = shell_argv[0]
    if cmd_name == 'cd' or cmd_name in GUARANTEED_COMMANDS:
        return False
    env_path = session.get_env().get('PATH', os.defpath)
    if shutil.which(cmd_name, mode=os.F_OK | os.X_OK, path=env_path):
        return False
    if not python_code.strip():
        return False
    try:
        ast.parse(python_code, mode='exec')
        return True
    except SyntaxError:
        return False


def _expand_command_for_stage(cmd: SimpleCommand, session: ShellSession) -> ExpandedCommand:
    shell_argv = [_expand_word(value, quoting, session) for value, quoting in cmd.argv]
    redirs: List[Redirection] = []
    for r in cmd.redirs:
        target = r.target
        if isinstance(target, str):
            target = _expand_word(target, 'unquoted', session)
        redirs.append(Redirection(r.fd, r.op, target))
    python_source_raw = _reconstruct_python_source(cmd.argv).strip()
    python_code = _expand_command_substitutions(python_source_raw, session, for_python=True) if python_source_raw else ""
    is_python = _should_treat_as_python(shell_argv, python_code, session)
    return ExpandedCommand(argv=shell_argv, redirs=redirs, is_python=is_python, python_code=python_code if is_python else None)


class _StreamMultiplexer:
    def __init__(self, streams: List[Any]):
        self._streams = streams

    def write(self, data: str) -> int:
        for stream in self._streams:
            try:
                stream.write(data)
            except Exception:
                continue
        return len(data)

    def flush(self) -> None:
        for stream in self._streams:
            flush = getattr(stream, 'flush', None)
            if callable(flush):
                try:
                    flush()
                except Exception:
                    # Ignore flush errors when downstream stages close early.
                    continue


def _run_python_stage(cmd: ExpandedCommand, session: ShellSession, input_data: Optional[bytes], has_more: bool) -> Tuple[int, Optional[bytes]]:
    assert cmd.python_code is not None
    encoding = 'utf-8'
    stdin_stream: Optional[io.TextIOBase] = None
    stdout_targets: List[io.TextIOBase] = []
    stderr_target: Optional[io.TextIOBase] = None
    stderr_to_stdout = False
    opened_streams: List[io.TextIOBase] = []

    for redir in cmd.redirs:
        if redir.op == '<':
            if redir.fd not in (0,):
                raise ValueError("unsupported fd for input redirection in python stage")
            f = open(str(redir.target), 'r', encoding=encoding, errors='replace')
            stdin_stream = f
            opened_streams.append(f)
        elif redir.op in ('>', '>>'):
            mode = 'w' if redir.op == '>' else 'a'
            f = open(str(redir.target), mode, encoding=encoding, errors='replace')
            opened_streams.append(f)
            if redir.fd == 1:
                stdout_targets.append(f)
            elif redir.fd == 2:
                stderr_target = f
            else:
                f.close()
                raise ValueError("unsupported fd for python redirection")
        elif redir.op == 'dup' and redir.fd == 2 and isinstance(redir.target, int) and redir.target == 1:
            stderr_to_stdout = True
        else:
            raise ValueError(f"unsupported redirection for python stage: {redir.op}")

    capture_stream: Optional[io.StringIO] = io.StringIO() if has_more else None
    stdout_stream_list: List[Any] = []
    if capture_stream is not None:
        stdout_stream_list.append(capture_stream)
    stdout_stream_list.extend(stdout_targets)
    if not stdout_stream_list:
        stdout_stream_list.append(sys.stdout)
    stdout_redirect: Optional[_StreamMultiplexer] = _StreamMultiplexer(stdout_stream_list) if (capture_stream is not None or stdout_targets) else None

    if stderr_to_stdout:
        stderr_redirect = stdout_redirect
    else:
        if stderr_target is None:
            stderr_target = sys.stderr
        stderr_redirect = _StreamMultiplexer([stderr_target])

    input_stream: Optional[io.TextIOBase]
    if stdin_stream is not None:
        input_stream = stdin_stream
    elif input_data is not None:
        input_stream = io.StringIO(input_data.decode(encoding, errors='replace'))
    else:
        input_stream = None

    rc = 0
    try:
        with ExitStack() as stack:
            if input_stream is not None:
                old_stdin = sys.stdin
                sys.stdin = input_stream
                stack.callback(lambda: setattr(sys, 'stdin', old_stdin))
            ctx_stdout = redirect_stdout(stdout_redirect) if stdout_redirect is not None else nullcontext()
            with ctx_stdout, redirect_stderr(stderr_redirect):
                result = try_python(cmd.python_code, session)
                if result is None:
                    rc = 127
                else:
                    rc = result
    finally:
        for stream in opened_streams:
            try:
                stream.flush()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    output_bytes: Optional[bytes] = None
    if capture_stream is not None:
        output_bytes = capture_stream.getvalue().encode(encoding)
    return rc, output_bytes


def _run_shell_group(group: List[ExpandedCommand], session: ShellSession, *, background: bool, initial_input: Optional[bytes], capture_output: bool) -> Tuple[int, Optional[bytes], List[subprocess.Popen]]:
    if not group:
        return 0, initial_input, []

    if background and capture_output:
        raise ValueError("cannot capture output when running in background")

    if len(group) == 1 and group[0].argv and group[0].argv[0] == 'cd' and not capture_output and initial_input is None and not background:
        target = None
        if len(group[0].argv) == 1:
            target = session.get_env().get('HOME') or os.path.expanduser('~')
        else:
            target = group[0].argv[1]
        try:
            os.chdir(target)
            newpwd = os.getcwd()
            session.env['PWD'] = newpwd
            session.py_vars['PWD'] = newpwd
            return 0, None, []
        except Exception as e:
            sys.stderr.write(f"pysh: cd: {e}\n")
            sys.stderr.flush()
            return 1, None, []

    procs: List[subprocess.Popen] = []
    open_handles: List[Any] = []
    prev_stdout = None
    try:
        for idx, info in enumerate(group):
            cmd_stub = SimpleCommand(argv=[])
            cmd_stub.redirs = [Redirection(r.fd, r.op, r.target) for r in info.redirs]
            stdin_fd, stdout_fd, stderr_fd, closers = _apply_redirections(cmd_stub)
            open_handles.extend(closers)

            if not info.argv:
                raise ValueError("empty command in pipeline")

            local_argv = list(info.argv)
            prog_name = os.path.basename(local_argv[0]) if local_argv else ''
            if prog_name == 'grep':
                engine_flags = {'-E', '--extended-regexp', '-F', '--fixed-strings', '-G', '--basic-regexp', '-P', '--perl-regexp'}
                if not any(a in engine_flags for a in local_argv[1:]):
                    local_argv.insert(1, '-P')

            use_initial_input = idx == 0 and initial_input is not None
            if use_initial_input and stdin_fd is not None:
                sys.stderr.write("pysh: cannot combine pipeline input with stdin redirection\n")
                sys.stderr.flush()
                return 1, None, []

            if use_initial_input:
                stdin = subprocess.PIPE
            else:
                stdin = prev_stdout if prev_stdout is not None else (stdin_fd if stdin_fd is not None else None)

            if idx < len(group) - 1:
                stdout = subprocess.PIPE
            else:
                if capture_output:
                    if stdout_fd is not None:
                        sys.stderr.write("pysh: cannot redirect stdout when piping to python stage\n")
                        sys.stderr.flush()
                        return 1, None, []
                    stdout = subprocess.PIPE
                else:
                    stdout = stdout_fd if stdout_fd is not None else None

            stderr = stderr_fd if stderr_fd is not None else None

            proc = subprocess.Popen(local_argv, stdin=stdin, stdout=stdout, stderr=stderr, env=session.get_env())
            procs.append(proc)

            if use_initial_input:
                assert proc.stdin is not None
                proc.stdin.write(initial_input)
                proc.stdin.close()
                proc.stdin = None

            if proc.stdout is not None:
                prev_stdout = proc.stdout
            else:
                prev_stdout = None

        if background:
            session.background_jobs.append(procs)
            return 0, None, procs

        stdout_bytes: Optional[bytes] = None
        for proc in procs[:-1]:
            proc.wait()
        if procs:
            last_proc = procs[-1]
            if capture_output:
                stdout_stream = last_proc.stdout
                if stdout_stream is not None:
                    stdout_bytes = stdout_stream.read()
                last_proc.wait()
            else:
                last_proc.wait()
        exit_code = procs[-1].returncode if procs else 0
        return exit_code, stdout_bytes, procs
    finally:
        for h in open_handles:
            try:
                h.close()
            except Exception:
                pass
        for proc in procs:
            if proc.stdout is not None:
                try:
                    proc.stdout.close()
                except Exception:
                    pass

def _exec_pipeline(p: Pipeline, session: ShellSession) -> int:
    total = len(p.commands)
    if total == 0:
        return 0

    idx = 0
    last_exit = 0
    input_data: Optional[bytes] = None
    cached: Optional[ExpandedCommand] = None

    while idx < total:
        if cached is not None:
            current = cached
            cached = None
        else:
            current = _expand_command_for_stage(p.commands[idx], session)

        if current.is_python:
            if p.background:
                sys.stderr.write("pysh: python stages cannot run in background pipelines\n")
                sys.stderr.flush()
                return 1

            has_more = (idx + 1 < total)
            rc, output_data = _run_python_stage(current, session, input_data, has_more)
            last_exit = rc
            input_data = output_data
            idx += 1
            continue

        shell_group: List[ExpandedCommand] = [current]
        idx += 1
        while idx < total:
            if cached is not None:
                next_expanded = cached
                cached = None
            else:
                next_expanded = _expand_command_for_stage(p.commands[idx], session)
            if next_expanded.is_python:
                cached = next_expanded
                break
            shell_group.append(next_expanded)
            idx += 1

        has_more = cached is not None or idx < total
        if p.background and has_more:
            sys.stderr.write("pysh: background pipelines cannot mix python stages\n")
            sys.stderr.flush()
            return 1

        rc, output_data, _ = _run_shell_group(
            shell_group,
            session,
            background=p.background and not has_more,
            initial_input=input_data,
            capture_output=has_more,
        )
        last_exit = rc
        input_data = output_data if has_more else None

        if p.background and not has_more:
            return 0

    return last_exit


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


def _execute_hybrid_multiline_buffer(session: ShellSession) -> int:
    """Execute a multi-line buffer with hybrid Python/shell line-by-line processing.
    
    This function processes each line in the multi-line buffer to determine if it should
    be executed as Python or shell, even within Python control structures.
    """
    if not session.multi_line_buffer:
        return 0
    
    # Convert the buffer into executable Python code where shell commands
    # are wrapped in subprocess calls
    converted_lines = []
    
    for line in session.multi_line_buffer:
        converted_line = _convert_line_for_hybrid_execution(line, session)
        converted_lines.append(converted_line)
    
    # Join and execute as Python
    source = '\n'.join(converted_lines)
    
    try:
        result = try_python(source, session)
        return result if result is not None else 0
    except Exception as e:
        sys.stderr.write(f"pysh: error in hybrid multi-line execution: {e}\n")
        sys.stderr.flush()
        return 1


def _convert_line_for_hybrid_execution(line: str, session: ShellSession) -> str:
    """Convert a line for hybrid execution, wrapping shell commands in Python calls."""
    
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        return line
    
    # Get the indentation
    indent = line[:len(line) - len(line.lstrip())]
    
    # Check if this is a Python control structure line
    if any(stripped.startswith(keyword + ' ') or stripped.startswith(keyword + ':') or stripped == keyword + ':'
           for keyword in ['for', 'while', 'if', 'elif', 'else', 'def', 'class', 'with', 'try', 'except', 'finally']):
        return line
    
    # Check if this line should be executed as shell
    if _should_execute_as_shell(stripped, session):
        # Instead of subprocess, use a simpler approach that calls the existing execute_line function
        shell_code = f"__pysh_exec_shell({repr(stripped)})"
        return indent + shell_code
    
    # Regular Python line
    return line


def _should_execute_as_shell(line: str, session: ShellSession) -> bool:
    """Determine if a line should be executed as a shell command."""
    
    # Skip empty lines and comments
    if not line or line.startswith('#'):
        return False
    
    # If it contains an assignment operator (=, +=, etc.), it's Python
    if any(op in line for op in ['=', '+=', '-=', '*=', '/=', '//=', '%=', '**=', '&=', '|=', '^=', '<<=', '>>=']):
        # But not if it's a comparison (==, !=, <=, >=)
        if not any(op in line for op in ['==', '!=', '<=', '>=']):
            return False
    
    # Split into tokens for analysis
    tokens = line.split()
    if not tokens:
        return False
    
    first_token = tokens[0]
    
    # Check if it's a guaranteed shell command
    if first_token in GUARANTEED_COMMANDS:
        return True
    
    # Check if it's available in PATH
    if shutil.which(first_token):
        return True
    
    # Check for shell operators
    if any(op in line for op in ['|', '>', '<', '>>', '<<', '&&', '||']):
        return True
    
    # Check for shell variable expansion patterns
    if '$' in line and not line.startswith('$'):  # Don't treat pure $var as shell
        return True
    
    # Try to parse as Python - if it fails, it might be shell
    try:
        ast.parse(line, mode='eval')
        return False  # Valid Python expression
    except SyntaxError:
        # Could be a shell command or invalid Python
        # Use heuristics: if first token looks like a command, treat as shell
        if first_token.isidentifier() and not first_token in ['and', 'or', 'not', 'in', 'is']:
            return True
        return False


def execute_line(line: str, session: ShellSession) -> int:
    # Handle multi-line Python code accumulation
    if session.in_multi_line:
        indent_unit = session.get_indent_unit()
        suggested_indent = indent_unit * max(session.current_indent_level, 0)
        terminate_now = False
        if line == "":
            terminate_now = True
        elif line.strip() == "":
            if suggested_indent and line == suggested_indent:
                terminate_now = True
            elif session.multi_line_buffer and line == session.multi_line_buffer[-1]:
                terminate_now = True

        if terminate_now:
            rc = _execute_hybrid_multiline_buffer(session)
            session.multi_line_buffer = []
            session.in_multi_line = False
            session.current_indent_level = 0
            return rc

        _append_multiline_line(session, line)
        return 0

    # Check if this line starts a Python compound statement
    stripped = line.strip()
    try:
        ast.parse(line, mode='exec')
        # If it parses successfully, it's a complete statement; proceed to normal execution
    except SyntaxError:
        # Check if it looks like the start of a compound statement
        if stripped.endswith(':') and stripped.split()[0] in ['for', 'while', 'if', 'def', 'class', 'with', 'try', 'async']:
            # Start multi-line accumulation
            _start_multiline_block(session, line)
            return 0

    # Prepare both Python and shell views of the line
    line_py = _expand_command_substitutions(line, session, for_python=True)
    # Fast path: if this is a Python assignment, handle it first regardless of operators in substituted text
    handled = _try_python_assignment(line_py, session)
    if handled is not None:
        return handled

    line_shell = _expand_command_substitutions(line, session, for_python=False)
    # Route selection per spec: prefer shell operators and commands next.
    if has_operators(line_shell):
        # Tokenize without pre-expanding variables to preserve escapes and quoting
        tokens = _tokenize(line_shell)
        if not tokens:
            return 0
        units = _parse_sequence(tokens)
        return _exec_sequence(units, session)

    # No operators: check command presence first
    import shlex as _shlex
    lex = _shlex.shlex(line_shell, posix=True)
    lex.whitespace_split = True
    simple_tokens = list(lex)
    if simple_tokens:
        cmd = simple_tokens[0]
        if cmd == 'cd' or shutil.which(cmd, mode=os.F_OK | os.X_OK, path=session.get_env().get('PATH', os.defpath)):
            tokens = _tokenize(line_shell)
            if not tokens:
                return 0
            units = _parse_sequence(tokens)
            return _exec_sequence(units, session)

    # Not a shell command: attempt Python (assignment fast-path first to set vars quietly)
    # Expand command substitutions for Python context (as string literals)
    line_py = _expand_command_substitutions(line, session, for_python=True)
    rc = try_python(line_py, session)
    if rc is None:
        sys.stderr.write(f"pysh: command or python code not found: {line}\n")
        sys.stderr.flush()
        return 127
    return rc


# Public helper for the REPL to expand variables in simple commands before delegating to the system shell
def expand_line(line: str, session: ShellSession) -> str:
    return _expand_vars_in_line(line, session)
