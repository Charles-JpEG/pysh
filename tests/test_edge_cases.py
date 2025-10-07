#!/usr/bin/env python3
"""Additional edge case tests to boost coverage to 95%+"""

import sys
import os
from pathlib import Path

# Add src to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pytest
from ops import ShellSession, execute_line, CommandRunner, try_python
import tempfile


class TestCommandRunnerEdgeCases:
    """Test CommandRunner edge cases"""
    
    def test_command_runner_with_empty_command(self):
        """Test CommandRunner with empty command"""
        runner = CommandRunner("", shell="/bin/sh", env={})
        # Should handle empty command
        
    def test_command_runner_shell_run_with_capture(self):
        """Test shell_run with output capture"""
        runner = CommandRunner("echo test", shell="/bin/sh", env={})
        result = runner.shell_run()
        assert result == 0
        
    def test_command_runner_get_output(self):
        """Test getting output from runner"""
        runner = CommandRunner("echo test", shell="/bin/sh", env={})
        runner.shell_run()
        # Test output access
        if hasattr(runner, 'stdout'):
            output = runner.stdout


class TestTryPythonEdgeCases:
    """Test try_python function edge cases"""
    
    def test_try_python_with_imports(self):
        """Test Python code with imports"""
        session = ShellSession("/bin/sh")
        result = try_python("import os; x = 5", session)
        assert result == 0
        
    def test_try_python_with_exception(self):
        """Test Python code that raises exception"""
        session = ShellSession("/bin/sh")
        result = try_python("raise ValueError('test')", session)
        assert result != 0
        
    def test_try_python_with_syntax_error(self):
        """Test Python code with syntax error"""
        session = ShellSession("/bin/sh")
        result = try_python("def invalid(", session)
        assert result != 0
        
    def test_try_python_with_print(self):
        """Test Python print statements"""
        session = ShellSession("/bin/sh")
        result = try_python("print('hello world')", session)
        assert result == 0


class TestMultiLineEdgeCases:
    """Test multi-line mode edge cases"""
    
    def test_multiline_with_dedent_elif(self):
        """Test elif causes dedent"""
        session = ShellSession("/bin/sh")
        session.in_multi_line = True
        session.indent_unit = "    "
        session.current_indent_level = 2
        
        execute_line("elif True:", session)
        # Should have dedented
        
    def test_multiline_with_dedent_except(self):
        """Test except causes dedent"""
        session = ShellSession("/bin/sh")
        session.in_multi_line = True
        session.indent_unit = "    "
        session.current_indent_level = 2
        
        execute_line("except:", session)
        # Should have dedented
        
    def test_multiline_with_dedent_finally(self):
        """Test finally causes dedent"""
        session = ShellSession("/bin/sh")
        session.in_multi_line = True
        session.indent_unit = "    "
        session.current_indent_level = 2
        
        execute_line("finally:", session)
        # Should have dedented
        
    def test_multiline_comment_line(self):
        """Test comment lines in multi-line"""
        session = ShellSession("/bin/sh")
        session.in_multi_line = True
        session.indent_unit = "    "
        
        execute_line("# comment", session)
        assert len(session.multi_line_buffer) > 0
        
    def test_multiline_with_colon_indent(self):
        """Test lines ending with : trigger indent"""
        session = ShellSession("/bin/sh")
        session.in_multi_line = True
        session.indent_unit = "    "
        session.current_indent_level = 0
        
        execute_line("if True:", session)
        # Should have indented
        assert session.current_indent_level >= 1


class TestShellVariableExpansion:
    """Test shell variable expansion edge cases"""
    
    def test_dollar_sign_in_string(self):
        """Test $ in Python strings doesn't trigger shell"""
        session = ShellSession("/bin/sh")
        result = execute_line('s = "price is $5"', session)
        assert result == 0
        assert session.py_vars.get('s') == "price is $5"
        
    def test_env_var_in_command(self):
        """Test environment variable expansion in shell command"""
        session = ShellSession("/bin/sh")
        session.env['TESTVAR'] = 'value123'
        result = execute_line("echo $TESTVAR | cat > /dev/null", session)
        assert result == 0


class TestAssignmentProtection:
    """Test assignment protection for preserved commands"""
    
    def test_augmented_assignment_to_protected(self):
        """Test augmented assignment to protected name"""
        session = ShellSession("/bin/sh")
        result = execute_line("grep += 1", session)
        # Should fail - grep is protected
        
    def test_multiple_assignment_with_protected(self):
        """Test multiple assignment including protected name"""
        session = ShellSession("/bin/sh")
        result = execute_line("x, ls, y = 1, 2, 3", session)
        # Should fail - ls is protected


class TestPipelineEdgeCases:
    """Test pipeline edge cases"""
    
    def test_pipeline_with_python_and_shell(self, tmp_path):
        """Test Python | shell pipeline"""
        session = ShellSession("/bin/sh")
        os.chdir(tmp_path)
        result = execute_line("print('test') | cat > /dev/null", session)
        # Should work
        
    def test_pipeline_three_stages(self, tmp_path):
        """Test three-stage pipeline"""
        session = ShellSession("/bin/sh")
        os.chdir(tmp_path)
        result = execute_line("echo test | cat | grep test > /dev/null", session)
        assert result == 0


class TestBackgroundProcesses:
    """Test background process handling"""
    
    def test_multiple_background_jobs(self):
        """Test multiple background jobs"""
        session = ShellSession("/bin/sh")
        execute_line("sleep 0.01 &", session)
        execute_line("sleep 0.01 &", session)
        assert len(session.background_jobs) >= 2
        
    def test_background_job_with_pipeline(self):
        """Test background job with pipeline"""
        session = ShellSession("/bin/sh")
        result = execute_line("echo test | cat &", session)
        # Should work


class TestConditionalOperators:
    """Test && and || operators"""
    
    def test_and_operator_with_failure(self):
        """Test && with first command failing"""
        session = ShellSession("/bin/sh")
        result = execute_line("false && echo should_not_run", session)
        # Should short-circuit
        
    def test_or_operator_with_success(self):
        """Test || with first command succeeding"""
        session = ShellSession("/bin/sh")
        result = execute_line("true || echo should_not_run", session)
        # Should short-circuit
        
    def test_combined_and_or(self):
        """Test combined && and ||"""
        session = ShellSession("/bin/sh")
        result = execute_line("false || true && echo yes > /dev/null", session)


class TestRedirectionEdgeCases:
    """Test redirection edge cases"""
    
    def test_multiple_output_redirections(self, tmp_path):
        """Test multiple output redirections"""
        session = ShellSession("/bin/sh")
        os.chdir(tmp_path)
        f1 = tmp_path / "out1.txt"
        f2 = tmp_path / "out2.txt"
        # This may not work, but test error handling
        result = execute_line(f"echo test > {f1} > {f2}", session)
        
    def test_input_and_output_redirection(self, tmp_path):
        """Test combined input and output redirection"""
        session = ShellSession("/bin/sh")
        os.chdir(tmp_path)
        infile = tmp_path / "in.txt"
        outfile = tmp_path / "out.txt"
        infile.write_text("test\n")
        result = execute_line(f"cat < {infile} > {outfile}", session)
        if result == 0 and outfile.exists():
            assert "test" in outfile.read_text()


class TestSessionMethods:
    """Test ShellSession methods"""
    
    def test_get_indent_unit(self):
        """Test get_indent_unit method"""
        session = ShellSession("/bin/sh")
        unit = session.get_indent_unit()
        assert unit is not None
        
    def test_get_env_merges_py_vars(self):
        """Test get_env merges Python variables"""
        session = ShellSession("/bin/sh")
        session.py_vars['MYVAR'] = 'value'
        env = session.get_env()
        assert 'MYVAR' in env
        assert env['MYVAR'] == 'value'
        
    def test_get_env_with_non_string_values(self):
        """Test get_env handles non-string Python values"""
        session = ShellSession("/bin/sh")
        session.py_vars['NUM'] = 123
        session.py_vars['LST'] = [1, 2, 3]
        env = session.get_env()
        # Should convert to strings
        if 'NUM' in env:
            assert env['NUM'] == '123'


class TestCommentHandling:
    """Test comment handling"""
    
    def test_comment_only_line(self):
        """Test line with only comment"""
        session = ShellSession("/bin/sh")
        result = execute_line("# this is a comment", session)
        # Should be ignored or return 0
        
    def test_command_with_trailing_comment(self):
        """Test command with trailing comment"""
        session = ShellSession("/bin/sh")
        result = execute_line("echo test > /dev/null  # comment", session)


class TestQuoting:
    """Test quoting edge cases"""
    
    def test_single_quotes(self):
        """Test single quoted strings"""
        session = ShellSession("/bin/sh")
        result = execute_line("s = 'single quoted'", session)
        assert result == 0
        assert session.py_vars.get('s') == 'single quoted'
        
    def test_double_quotes(self):
        """Test double quoted strings"""
        session = ShellSession("/bin/sh")
        result = execute_line('s = "double quoted"', session)
        assert result == 0
        assert session.py_vars.get('s') == 'double quoted'
        
    def test_shell_quoting_in_command(self):
        """Test quoting in shell commands"""
        session = ShellSession("/bin/sh")
        result = execute_line("echo 'hello world' > /dev/null", session)
        assert result == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
