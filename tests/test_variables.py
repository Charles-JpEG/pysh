"""Tests for variable management - a core feature of pysh."""

import os
import sys
from pathlib import Path

import pytest  # type: ignore

# Add src directory to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from ops import ShellSession, execute_line


def run_line(line: str, session: ShellSession) -> int:
    return execute_line(line, session)


class TestVariableAssignment:
    """Test Python variable assignments."""
    
    def test_simple_assignment(self, session):
        """Test basic variable assignment."""
        code = run_line("x = 42", session)
        assert code == 0
        assert session.py_vars["x"] == 42
    
    def test_string_assignment(self, session):
        """Test string variable assignment."""
        code = run_line("name = 'Alice'", session)
        assert code == 0
        assert session.py_vars["name"] == "Alice"
    
    def test_list_assignment(self, session):
        """Test list assignment."""
        code = run_line("items = [1, 2, 3]", session)
        assert code == 0
        assert session.py_vars["items"] == [1, 2, 3]
    
    def test_dict_assignment(self, session):
        """Test dictionary assignment."""
        code = run_line("data = {'key': 'value'}", session)
        assert code == 0
        assert session.py_vars["data"] == {"key": "value"}
    
    def test_multiple_assignment(self, session):
        """Test multiple variable assignment."""
        code = run_line("a, b = 1, 2", session)
        assert code == 0
        assert session.py_vars["a"] == 1
        assert session.py_vars["b"] == 2


class TestVariableAccess:
    """Test accessing variables in different contexts."""
    
    def test_python_variable_access(self, session):
        """Test accessing Python variables."""
        session.py_vars["x"] = 100
        code = run_line("x", session)
        assert code == 0
    
    def test_variable_in_expression(self, session):
        """Test using variable in expression."""
        session.py_vars["x"] = 10
        code = run_line("x + 5", session)
        assert code == 0
    
    def test_variable_in_print(self, session, tmp_path, capsys):
        """Test printing variable."""
        session.py_vars["message"] = "Hello"
        code = run_line("print(message)", session)
        assert code == 0
        captured = capsys.readouterr()
        assert "Hello" in captured.out


class TestDollarExpansion:
    """Test $var expansion in shell commands."""
    
    def test_dollar_expansion_simple(self, session, tmp_path):
        """Test simple $var expansion."""
        session.py_vars["name"] = "test"
        code = run_line("echo $name > output.txt", session)
        assert code == 0
        content = (tmp_path / "output.txt").read_text()
        assert "test" in content
    
    def test_dollar_expansion_braces(self, session, tmp_path):
        """Test ${var} expansion."""
        session.py_vars["value"] = "42"
        code = run_line("echo ${value} > output.txt", session)
        assert code == 0
        content = (tmp_path / "output.txt").read_text()
        assert "42" in content
    
    def test_dollar_expansion_undefined(self, session, tmp_path):
        """Test expansion of undefined variable (should be empty)."""
        code = run_line("echo $undefined_var > output.txt", session)
        assert code == 0
        # Undefined vars should expand to empty string
        content = (tmp_path / "output.txt").read_text().strip()
        assert content == ""
    
    def test_dollar_in_single_quotes(self, session, tmp_path):
        """Test that $var is literal in single quotes."""
        session.py_vars["x"] = "expanded"
        code = run_line("echo '$x' > output.txt", session)
        assert code == 0
        content = (tmp_path / "output.txt").read_text()
        assert "$x" in content
        assert "expanded" not in content
    
    def test_dollar_in_double_quotes(self, session, tmp_path):
        """Test that $var expands in double quotes."""
        session.py_vars["y"] = "inside"
        code = run_line('echo "$y" > output.txt', session)
        assert code == 0
        content = (tmp_path / "output.txt").read_text()
        assert "inside" in content


class TestProtectedCommands:
    """Test that command names cannot be overridden."""
    
    def test_cannot_assign_to_date(self, session, capsys):
        """Test that assigning to 'date' fails with appropriate error."""
        code = run_line("date = '11:05'", session)
        # Should fail or produce error message
        # The spec says: "pysh: cannot assign to preserved command name: date"
        captured = capsys.readouterr()
        # Check if either error code or stderr contains the message
        assert code != 0 or "cannot assign" in captured.err.lower() or "preserved" in captured.err.lower()
    
    def test_cannot_assign_to_echo(self, session, capsys):
        """Test that assigning to 'echo' fails."""
        code = run_line("echo = 'test'", session)
        captured = capsys.readouterr()
        assert code != 0 or "cannot assign" in captured.err.lower() or "preserved" in captured.err.lower()
    
    def test_cannot_assign_to_ls(self, session, capsys):
        """Test that assigning to 'ls' fails."""
        code = run_line("ls = []", session)
        captured = capsys.readouterr()
        assert code != 0 or "cannot assign" in captured.err.lower() or "preserved" in captured.err.lower()
    
    def test_can_use_command_after_failed_assignment(self, session, tmp_path):
        """Test that command still works after failed assignment attempt."""
        # Try to assign (should fail)
        run_line("pwd = '/fake'", session)
        
        # Command should still work
        code = run_line("pwd > pwd.txt", session)
        assert code == 0
        assert (tmp_path / "pwd.txt").exists()


class TestEnvironmentVariables:
    """Test environment variable handling."""
    
    def test_env_var_accessible(self, session, tmp_path):
        """Test that environment variables are accessible."""
        session.env["MY_VAR"] = "my_value"
        code = run_line("echo $MY_VAR > output.txt", session)
        assert code == 0
        content = (tmp_path / "output.txt").read_text()
        assert "my_value" in content
    
    def test_python_var_overrides_env(self, session, tmp_path):
        """Test that Python vars take precedence over env vars."""
        session.env["OVERRIDE_TEST"] = "env_value"
        session.py_vars["OVERRIDE_TEST"] = "py_value"
        code = run_line("echo $OVERRIDE_TEST > output.txt", session)
        assert code == 0
        content = (tmp_path / "output.txt").read_text()
        assert "py_value" in content
        assert "env_value" not in content
    
    def test_path_accessible(self, session):
        """Test that PATH is accessible."""
        # PATH should be inherited from environment
        assert "PATH" in session.get_env()
    
    def test_home_accessible(self, session):
        """Test that HOME is accessible."""
        # HOME should be inherited from environment
        env = session.get_env()
        assert "HOME" in env or "home" in str(env).lower()


class TestVariableInHybridContext:
    """Test variables in hybrid Python/shell contexts."""
    
    def test_variable_in_loop_with_shell(self, session, tmp_path):
        """Test variable access in loop with shell command."""
        # This is the hybrid feature that was fixed
        from test_framework import PyshTester
        
        with PyshTester() as tester:
            tester.run("x = 'hello'")
            tester.run("for i in range(2):")
            tester.run("echo $i")
            result = tester.run("    ")
            
            assert "0" in result.stdout
            assert "1" in result.stdout
    
    def test_python_var_in_shell_command(self, session, tmp_path):
        """Test using Python variable in shell command."""
        session.py_vars["filename"] = "test.txt"
        code = run_line("echo 'content' > $filename", session)
        assert code == 0
        assert (tmp_path / "test.txt").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
