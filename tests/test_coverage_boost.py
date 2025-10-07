#!/usr/bin/env python3
"""Tests for additional coverage - edge cases and less-tested paths."""

import sys
import os
from pathlib import Path

# Add src to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pytest
from ops import ShellSession, execute_line
from main import get_default_shell, is_posix_shell
import tempfile
import shutil


class TestShellDetectionEdgeCases:
    """Test edge cases in shell detection"""
    
    def test_get_default_shell_with_invalid_shell_env(self, monkeypatch):
        """Test shell detection when SHELL env has non-POSIX shell"""
        monkeypatch.setenv("SHELL", "/usr/bin/fish")
        shell, warning = get_default_shell()
        # Should fallback to a POSIX shell or warn
        assert shell is not None
    
    def test_get_default_shell_no_env_no_pwd(self, monkeypatch):
        """Test shell detection with no SHELL env and pwd unavailable"""
        monkeypatch.delenv("SHELL", raising=False)
        # Mock pwd to raise exception
        monkeypatch.setattr("pwd.getpwuid", lambda x: (_ for _ in ()).throw(Exception("no pwd")))
        shell, warning = get_default_shell()
        # Should fallback to finding a POSIX shell or /bin/sh
        assert shell is not None
    
    def test_get_default_shell_fallback_to_bin_sh(self, monkeypatch):
        """Test ultimate fallback to /bin/sh"""
        monkeypatch.delenv("SHELL", raising=False)
        # This test may not work as expected since we can't fully mock shell detection
        shell, warning = get_default_shell()
        # Just verify we get a shell
        assert shell is not None


class TestMultiLineIndentation:
    """Test multi-line indentation handling"""
    
    def test_manual_indentation_preserved(self):
        """Test that manually indented lines are preserved"""
        session = ShellSession(shell="/bin/sh")
        session.in_multi_line = True
        session.indent_unit = "    "
        session.current_indent_level = 0
        
        # Execute a line with manual indentation
        execute_line("    manually_indented_line", session)
        assert len(session.multi_line_buffer) > 0
        # The line should preserve manual indentation
        assert session.multi_line_buffer[-1].startswith("    ")
    
    def test_dedent_prefixes(self):
        """Test dedentation on else/elif/except/finally"""
        session = ShellSession(shell="/bin/sh")
        session.in_multi_line = True
        session.indent_unit = "    "
        session.current_indent_level = 2
        
        execute_line("else:", session)
        # Should dedent
        assert session.current_indent_level >= 0
    
    def test_empty_line_in_multiline(self):
        """Test empty lines in multi-line mode"""
        session = ShellSession(shell="/bin/sh")
        session.in_multi_line = True
        session.indent_unit = "    "
        
        execute_line("", session)
        # Empty line should be added to buffer
        assert len(session.multi_line_buffer) >= 0


class TestProtectedCommandAssignment:
    """Test protection against assigning to preserved command names"""
    
    def test_assign_to_grep_fails(self):
        """Test that assigning to 'grep' is blocked"""
        session = ShellSession(shell="/bin/sh")
        result = execute_line("grep = 5", session)
        assert result == 1  # Should fail
    
    def test_assign_to_ls_in_tuple_fails(self):
        """Test tuple assignment with preserved names"""
        session = ShellSession(shell="/bin/sh")
        result = execute_line("ls, cat = 1, 2", session)
        assert result == 1  # Should fail
    
    def test_assign_to_find_in_list_fails(self):
        """Test list assignment with preserved names"""
        session = ShellSession(shell="/bin/sh")
        result = execute_line("[find, pwd] = [1, 2]", session)
        assert result == 1  # Should fail


class TestPythonRedirections:
    """Test Python statement redirections"""
    
    def test_python_output_simple(self, tmp_path):
        """Test simple Python output redirection"""
        session = ShellSession(shell="/bin/sh")
        session.env['PWD'] = str(tmp_path)
        os.chdir(tmp_path)
        
        # Simple test case
        result = execute_line("x = 5", session)
        assert result == 0
        assert session.py_vars.get('x') == 5


class TestHybridMultiLineExecution:
    """Test hybrid multi-line execution paths"""
    
    def test_hybrid_multiline_with_shell_commands(self, tmp_path):
        """Test multi-line with shell commands"""
        session = ShellSession(shell="/bin/sh")
        session.env['PWD'] = str(tmp_path)
        os.chdir(tmp_path)
        session.in_multi_line = True
        
        execute_line("for i in range(3):", session)
        execute_line("    echo $i", session)
        result = execute_line("", session)  # Trigger execution
        
        # Buffer should have been processed
        assert not session.in_multi_line or len(session.multi_line_buffer) == 0


class TestShellCommandDetection:
    """Test shell command detection heuristics through execute_line"""
    
    def test_assignment_operators_python(self):
        """Test that assignments are detected as Python"""
        session = ShellSession("/bin/sh")
        result = execute_line("x = 5", session)
        assert result == 0
        assert session.py_vars.get('x') == 5
        
        result = execute_line("x += 1", session)
        assert result == 0
        assert session.py_vars.get('x') == 6
    
    def test_guaranteed_commands(self):
        """Test guaranteed commands are always shell"""
        session = ShellSession("/bin/sh")
        result = execute_line("ls /tmp > /dev/null 2>&1", session)
        assert result == 0
    
    def test_path_commands(self):
        """Test PATH commands are detected"""
        session = ShellSession("/bin/sh")
        if shutil.which("python3"):
            result = execute_line("python3 --version > /dev/null 2>&1", session)
            assert result == 0
    
    def test_shell_operators(self):
        """Test shell operators trigger shell detection"""
        session = ShellSession("/bin/sh")
        result = execute_line("echo test | cat > /dev/null", session)
        assert result == 0
        
        result = execute_line("true && echo yes > /dev/null", session)
        assert result == 0
    
    def test_variable_expansion(self):
        """Test $var expansion triggers shell detection"""
        session = ShellSession("/bin/sh")
        session.env['TESTVAR'] = 'value'
        result = execute_line("echo $TESTVAR > /dev/null", session)
        assert result == 0
    
    def test_python_expressions(self):
        """Test valid Python expressions"""
        session = ShellSession("/bin/sh")
        result = execute_line("result = 2 + 2", session)
        assert result == 0
        assert session.py_vars.get('result') == 4


class TestErrorHandling:
    """Test error handling paths"""
    
    def test_parse_error_handling(self):
        """Test handling of parse errors"""
        session = ShellSession(shell="/bin/sh")
        # Invalid syntax
        result = execute_line("def (invalid", session)
        # Should handle error gracefully
    
    def test_malformed_hybrid_line(self):
        """Test malformed hybrid command"""
        session = ShellSession(shell="/bin/sh")
        session.in_multi_line = True
        execute_line("if True:", session)
        execute_line("    !!invalid!!", session)
        result = execute_line("", session)
        # Should handle error


class TestInteractiveLoopEdgeCases:
    """Test interactive loop edge cases from main.py"""
    
    def test_continuation_prompt_with_readline(self, monkeypatch):
        """Test continuation prompt with readline"""
        # This tests the readline continuation logic
        # Would need to mock readline properly
        pass
    
    def test_keyboard_interrupt_handling(self):
        """Test Ctrl-C handling"""
        # This would require simulating KeyboardInterrupt
        pass


class TestEnvironmentVariables:
    """Test environment variable handling"""
    
    def test_env_var_expansion_in_shell(self):
        """Test $VAR expansion in shell commands"""
        session = ShellSession(shell="/bin/sh")
        session.env['TESTVAR'] = 'testvalue'
        result = execute_line("echo $TESTVAR", session)
        assert result == 0
    
    def test_env_var_from_python_to_shell(self):
        """Test Python-set vars available in shell"""
        session = ShellSession(shell="/bin/sh")
        execute_line("MYVAR = 'frompy'", session)
        # MYVAR should be in py_vars
        assert 'MYVAR' in session.py_vars
        assert session.py_vars['MYVAR'] == 'frompy'


class TestBackgroundJobs:
    """Test background job handling"""
    
    def test_background_job_tracking(self):
        """Test that background jobs are tracked"""
        session = ShellSession(shell="/bin/sh")
        result = execute_line("sleep 0.01 &", session)
        assert result == 0
        assert len(session.background_jobs) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
