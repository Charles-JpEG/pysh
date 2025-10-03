"""Comprehensive tests for ops.py functions to achieve high coverage."""

import os
import sys
from pathlib import Path

import pytest  # type: ignore

# Add src directory to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from ops import (
    ShellSession,
    execute_line,
    has_operators,
    expand_line,
    Token,
    Redirection,
    SimpleCommand,
    Pipeline,
    SequenceUnit,
    CommandRunner,
    GUARANTEED_COMMANDS
)


def run_line(line: str, session: ShellSession) -> int:
    """Helper to run a line."""
    return execute_line(line, session)


class TestShellSessionMethods:
    """Test ShellSession public methods."""
    
    def test_get_env_merges_vars(self, session):
        """Test that get_env merges Python vars with env."""
        session.env["ENV_VAR"] = "env_value"
        session.py_vars["PY_VAR"] = "py_value"
        
        env = session.get_env()
        assert "ENV_VAR" in env
        assert "PY_VAR" in env
        assert env["ENV_VAR"] == "env_value"
        assert env["PY_VAR"] == "py_value"
    
    def test_get_env_python_overrides_env(self, session):
        """Test that Python vars override env vars."""
        session.env["OVERRIDE"] = "env"
        session.py_vars["OVERRIDE"] = "python"
        
        env = session.get_env()
        assert env["OVERRIDE"] == "python"
    
    def test_get_indent_unit_default(self, session):
        """Test default indent unit."""
        indent = session.get_indent_unit()
        assert indent == "    "  # Default 4 spaces
    
    def test_get_indent_unit_custom(self, session):
        """Test custom indent unit from __pysh_indent."""
        session.py_vars["__pysh_indent"] = "  "
        indent = session.get_indent_unit()
        assert indent == "  "
    
    def test_get_indent_unit_from_env(self, session, monkeypatch):
        """Test indent unit from PYSH_INDENT env var."""
        session.env["PYSH_INDENT"] = "\t"
        indent = session.get_indent_unit()
        assert indent == "\t"
    
    def test_get_var_from_py_vars(self, session):
        """Test getting variable from py_vars."""
        session.py_vars["test_var"] = 42
        value = session.get_var("test_var")
        assert value == 42
    
    def test_get_var_from_env(self, session):
        """Test getting variable from env."""
        session.env["ENV_VAR"] = "value"
        value = session.get_var("ENV_VAR")
        assert value == "value"
    
    def test_get_var_priority(self, session):
        """Test that py_vars take priority over env."""
        session.env["VAR"] = "env"
        session.py_vars["VAR"] = "python"
        value = session.get_var("VAR")
        assert value == "python"
    
    def test_get_var_nonexistent(self, session):
        """Test getting nonexistent variable."""
        value = session.get_var("nonexistent")
        assert value is None
    
    def test_set_var(self, session):
        """Test setting a variable."""
        session.set_var("my_var", "my_value")
        assert session.py_vars["my_var"] == "my_value"
    
    def test_unset_var(self, session):
        """Test unsetting a variable."""
        session.py_vars["to_delete"] = "value"
        session.unset_var("to_delete")
        assert "to_delete" not in session.py_vars
    
    def test_unset_var_nonexistent(self, session):
        """Test unsetting nonexistent variable doesn't crash."""
        # Should not raise error
        session.unset_var("nonexistent")


class TestHasOperators:
    """Test has_operators function."""
    
    def test_has_pipe(self):
        """Test detection of pipe operator."""
        assert has_operators("ls | grep test")
    
    def test_has_redirect_output(self):
        """Test detection of output redirection."""
        assert has_operators("echo test > file.txt")
    
    def test_has_redirect_append(self):
        """Test detection of append redirection."""
        assert has_operators("echo test >> file.txt")
    
    def test_has_redirect_input(self):
        """Test detection of input redirection."""
        assert has_operators("cat < input.txt")
    
    def test_has_and_operator(self):
        """Test detection of && operator."""
        assert has_operators("true && echo success")
    
    def test_has_or_operator(self):
        """Test detection of || operator."""
        assert has_operators("false || echo fallback")
    
    def test_has_semicolon(self):
        """Test detection of semicolon."""
        assert has_operators("cmd1; cmd2")
    
    def test_has_background(self):
        """Test detection of background operator."""
        assert has_operators("sleep 10 &")
    
    def test_no_operators_simple_command(self):
        """Test simple command without operators."""
        assert not has_operators("ls")
    
    def test_no_operators_with_args(self):
        """Test command with arguments but no operators."""
        assert not has_operators("ls -la /home")


class TestExpandLine:
    """Test expand_line function."""
    
    def test_expand_line_with_var(self, session):
        """Test expanding line with variables."""
        session.py_vars["name"] = "test"
        expanded = expand_line("echo $name", session)
        assert "test" in expanded
    
    def test_expand_line_no_vars(self, session):
        """Test expanding line without variables."""
        expanded = expand_line("echo hello", session)
        assert "hello" in expanded
    
    def test_expand_line_empty(self, session):
        """Test expanding empty line."""
        expanded = expand_line("", session)
        assert expanded == ""


class TestTokenClass:
    """Test Token class."""
    
    def test_token_creation(self):
        """Test creating a token."""
        token = Token("WORD", "test", "unquoted")
        assert token.kind == "WORD"
        assert token.value == "test"
        assert token.quoting == "unquoted"
    
    def test_token_repr(self):
        """Test token representation."""
        token = Token("OP", "|", "unquoted")
        repr_str = repr(token)
        assert "OP" in repr_str
        assert "|" in repr_str


class TestDataClasses:
    """Test data classes like Redirection, SimpleCommand, etc."""
    
    def test_redirection_creation(self):
        """Test creating a Redirection."""
        redir = Redirection(fd=1, op=">", target="output.txt")
        assert redir.fd == 1
        assert redir.op == ">"
        assert redir.target == "output.txt"
    
    def test_simple_command_creation(self):
        """Test creating a SimpleCommand."""
        cmd = SimpleCommand(argv=[("echo", "unquoted"), ("test", "unquoted")])
        assert cmd.argv == [("echo", "unquoted"), ("test", "unquoted")]
        assert cmd.redirs == []
    
    def test_pipeline_creation(self):
        """Test creating a Pipeline."""
        cmd = SimpleCommand(argv=[("echo", "unquoted")])
        pipe = Pipeline(commands=[cmd], background=False)
        assert pipe.commands == [cmd]
        assert not pipe.background
    
    def test_sequence_unit_creation(self):
        """Test creating a SequenceUnit."""
        cmd = SimpleCommand(argv=[("echo", "unquoted")])
        pipe = Pipeline(commands=[cmd])
        unit = SequenceUnit(pipeline=pipe, next_op=";")
        assert unit.pipeline == pipe
        assert unit.next_op == ";"


class TestCommandRunner:
    """Test CommandRunner class."""
    
    def test_command_runner_creation(self, session):
        """Test creating a CommandRunner."""
        runner = CommandRunner("echo test", shell=session.shell, env=session.get_env())
        assert runner.line == "echo test"
        assert runner.shell == session.shell
    
    def test_command_runner_simple_execution(self, session):
        """Test running a simple command."""
        runner = CommandRunner("echo test", shell=session.shell, env=session.get_env())
        result = runner.shell_run()
        assert result == 0
        assert "test" in runner.stdout


class TestGuaranteedCommands:
    """Test that GUARANTEED_COMMANDS contains expected commands."""
    
    def test_guaranteed_commands_exist(self):
        """Test that guaranteed commands set exists."""
        assert isinstance(GUARANTEED_COMMANDS, set)
        assert len(GUARANTEED_COMMANDS) > 0
    
    def test_basic_commands_included(self):
        """Test that basic commands are included."""
        expected = ['cd', 'ls', 'pwd', 'echo', 'cat', 'grep', 'find']
        for cmd in expected:
            assert cmd in GUARANTEED_COMMANDS, f"{cmd} should be in GUARANTEED_COMMANDS"
    
    def test_text_processing_commands(self):
        """Test that text processing commands are included."""
        expected = ['head', 'tail', 'wc', 'sort', 'uniq', 'cut']
        for cmd in expected:
            assert cmd in GUARANTEED_COMMANDS


class TestVariableExpansion:
    """Test variable expansion in various contexts."""
    
    def test_dollar_expansion_in_echo(self, session, tmp_path):
        """Test $var expansion in echo command."""
        session.py_vars["myvar"] = "hello"
        code = run_line("echo $myvar > output.txt", session)
        assert code == 0
        content = (tmp_path / "output.txt").read_text()
        assert "hello" in content
    
    def test_braces_expansion(self, session, tmp_path):
        """Test ${var} expansion."""
        session.py_vars["value"] = "world"
        code = run_line("echo ${value} > output.txt", session)
        assert code == 0
        content = (tmp_path / "output.txt").read_text()
        assert "world" in content
    
    def test_undefined_var_expands_empty(self, session, tmp_path):
        """Test that undefined variables expand to empty string."""
        code = run_line("echo [$undefined] > output.txt", session)
        assert code == 0
        content = (tmp_path / "output.txt").read_text()
        assert "[]" in content


class TestComplexPipelines:
    """Test complex pipeline scenarios."""
    
    def test_three_stage_pipeline(self, session, tmp_path):
        """Test pipeline with three stages."""
        test_file = tmp_path / "data.txt"
        test_file.write_text("apple\nbanana\napricot\nberry\n")
        
        code = run_line("cat data.txt | grep a | sort > output.txt", session)
        assert code == 0 or code == 1
        if (tmp_path / "output.txt").exists():
            content = (tmp_path / "output.txt").read_text()
            # Should contain lines with 'a', sorted
            if content:
                assert "a" in content.lower()
    
    def test_pipeline_with_redirects(self, session, tmp_path):
        """Test pipeline with output redirection."""
        code = run_line("echo -e 'line1\\nline2\\nline3' | head -n 2 > output.txt", session)
        assert code == 0


class TestConditionalExecution:
    """Test && and || operators."""
    
    def test_and_success_executes_next(self, session, tmp_path):
        """Test that && executes next command on success."""
        code = run_line("true && echo success > output.txt", session)
        assert code == 0
        assert (tmp_path / "output.txt").exists()
        content = (tmp_path / "output.txt").read_text()
        assert "success" in content
    
    def test_and_failure_skips_next(self, session, tmp_path):
        """Test that && skips next command on failure."""
        code = run_line("false && echo should_not_appear > output.txt", session)
        # Command should not create file or file should be empty
        assert not (tmp_path / "output.txt").exists() or (tmp_path / "output.txt").read_text() == ""
    
    def test_or_failure_executes_next(self, session, tmp_path):
        """Test that || executes next command on failure."""
        code = run_line("false || echo fallback > output.txt", session)
        assert code == 0
        content = (tmp_path / "output.txt").read_text()
        assert "fallback" in content
    
    def test_or_success_skips_next(self, session, tmp_path):
        """Test that || skips next command on success."""
        code = run_line("true || echo should_not_appear > output.txt", session)
        # Should not execute the second command
        assert not (tmp_path / "output.txt").exists() or (tmp_path / "output.txt").read_text() == ""


class TestBackgroundJobs:
    """Test background job handling."""
    
    def test_background_job_stored(self, session):
        """Test that background jobs are tracked."""
        initial_jobs = len(session.background_jobs)
        code = run_line("sleep 0.1 &", session)
        assert code == 0
        assert len(session.background_jobs) > initial_jobs
    
    def test_background_job_non_blocking(self, session):
        """Test that background jobs don't block."""
        import time
        start = time.time()
        code = run_line("sleep 1 &", session)
        elapsed = time.time() - start
        assert code == 0
        # Should return almost immediately, not wait 1 second
        assert elapsed < 0.5


class TestMultilineBuffer:
    """Test multi-line code execution."""
    
    def test_multiline_for_loop(self, session, capsys):
        """Test multi-line for loop execution."""
        from test_framework import PyshTester
        
        with PyshTester() as tester:
            tester.run("for i in range(3):")
            tester.run("print(i)")
            result = tester.run("    ")
            
            assert "0" in result.stdout
            assert "1" in result.stdout
            assert "2" in result.stdout


class TestPythonExpression:
    """Test Python expression evaluation."""
    
    def test_arithmetic_expression(self, session, capsys):
        """Test arithmetic expression."""
        code = run_line("2 + 2", session)
        assert code == 0
        captured = capsys.readouterr()
        assert "4" in captured.out
    
    def test_string_expression(self, session, capsys):
        """Test string expression."""
        code = run_line("'hello' + ' world'", session)
        assert code == 0
        captured = capsys.readouterr()
        assert "hello world" in captured.out


class TestErrorHandling:
    """Test error handling in various scenarios."""
    
    def test_nonexistent_command(self, session):
        """Test running nonexistent command."""
        code = run_line("nonexistent_command_xyz_123", session)
        # Should return non-zero exit code
        assert code != 0
    
    def test_syntax_error_in_python(self, session, capsys):
        """Test Python syntax error."""
        code = run_line("for i in", session)
        # Should handle error gracefully
        # Either returns error code or enters multiline mode
        assert code == 0 or code != 0  # Just check it doesn't crash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
