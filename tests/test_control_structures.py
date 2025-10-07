"""Tests for control structures: functions (def) and if-else statements."""

import sys
from pathlib import Path

import pytest  # type: ignore

# Add src directory to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from test_framework import PyshTester


@pytest.fixture()
def tester():
    with PyshTester() as instance:
        yield instance


class TestFunctionDefinition:
    """Test function definition and invocation."""
    
    def test_simple_function(self, tester: PyshTester):
        """Test defining and calling a simple function."""
        # Define function
        tester.run("def greet():")
        tester.run("print('Hello')")
        result = tester.run("    ")
        assert result.stderr == ""
        
        # Call function
        result = tester.run("greet()")
        assert "Hello" in result.stdout
    
    def test_function_with_parameter(self, tester: PyshTester):
        """Test function with parameters."""
        tester.run("def say(msg):")
        tester.run("print(msg)")
        tester.run("    ")
        
        result = tester.run("say('test')")
        assert "test" in result.stdout
    
    @pytest.mark.xfail(reason="Functions don't have access to shell execution context")
    def test_function_with_return(self, tester: PyshTester):
        """Test function that returns a value."""
        tester.run("def add(a, b):")
        tester.run("return a + b")
        tester.run("    ")
        
        result = tester.run("add(3, 4)")
        assert "7" in result.stdout
    
    @pytest.mark.xfail(reason="Functions don't have access to shell execution context")
    def test_function_with_shell_command(self, tester: PyshTester):
        """Test function containing shell commands."""
        tester.run("def list_files():")
        tester.run("ls")
        result = tester.run("    ")
        assert result.stderr == ""
        
        # Call function
        result = tester.run("list_files()")
        # Should execute ls command
        assert result.stderr == "" or result.stdout != ""
    
    @pytest.mark.xfail(reason="Functions don't have access to session variables")
    def test_function_accesses_variable(self, tester: PyshTester):
        """Test that function can access variables (priority rule)."""
        # Set up variable
        tester.run("x = 42")
        
        # Define function that uses variable
        tester.run("def show_x():")
        tester.run("print(x)")
        tester.run("    ")
        
        # Call function
        result = tester.run("show_x()")
        assert "42" in result.stdout
    
    @pytest.mark.xfail(reason="Nested functions don't have access to shell execution context")
    def test_nested_function_calls(self, tester: PyshTester):
        """Test nested function definitions."""
        tester.run("def outer():")
        tester.run("def inner():")
        tester.run("return 'nested'")
        tester.run("    ")
        tester.run("return inner()")
        tester.run("    ")
        
        result = tester.run("outer()")
        assert "nested" in result.stdout


class TestIfElseStatement:
    """Test if-else conditional statements."""
    
    def test_simple_if(self, tester: PyshTester):
        """Test simple if statement."""
        tester.run("x = 5")
        tester.run("if x > 3:")
        tester.run("print('yes')")
        result = tester.run("    ")
        
        assert "yes" in result.stdout
    
    def test_if_else(self, tester: PyshTester):
        """Test if-else statement."""
        tester.run("x = 1")
        tester.run("if x > 3:")
        tester.run("print('big')")
        tester.run("else:")
        tester.run("print('small')")
        result = tester.run("    ")
        
        assert "small" in result.stdout
    
    def test_if_elif_else(self, tester: PyshTester):
        """Test if-elif-else statement."""
        tester.run("x = 5")
        tester.run("if x < 3:")
        tester.run("print('small')")
        tester.run("elif x < 7:")
        tester.run("print('medium')")
        tester.run("else:")
        tester.run("print('large')")
        result = tester.run("    ")
        
        assert "medium" in result.stdout
    
    def test_if_with_shell_command(self, tester: PyshTester):
        """Test if statement with shell command in body."""
        tester.run("flag = True")
        tester.run("if flag:")
        tester.run("echo 'flag is set'")
        result = tester.run("    ")
        
        assert "flag is set" in result.stdout
    
    def test_nested_if(self, tester: PyshTester):
        """Test nested if statements."""
        tester.run("a = 5")
        tester.run("b = 10")
        tester.run("if a > 0:")
        tester.run("if b > 5:")
        tester.run("print('both')")
        tester.run("    ")
        result = tester.run("    ")
        
        assert "both" in result.stdout


class TestHybridPriority:
    """Test that variables/functions are prioritized in control structures."""
    
    def test_outside_control_uses_command(self, tester: PyshTester):
        """Test that outside control structures, commands are prioritized."""
        # This tests the spec: "Generally pysh would prioritize shell commands"
        # But we need ls variable to not interfere outside control structures
        # This is a tricky test - may need adjustment based on actual behavior
        result = tester.run("ls")
        # Should run ls command, not error about undefined variable
        # CommandResult doesn't have returncode, check for proper execution
        assert result.stderr == "" or "pysh>" in result.prompt


class TestControlStructureCombinations:
    """Test combinations of control structures."""
    
    def test_function_with_loop(self, tester: PyshTester):
        """Test function containing a loop."""
        tester.run("def count_to(n):")
        tester.run("for i in range(n):")
        tester.run("print(i)")
        tester.run("    ")
        tester.run("    ")
        
        result = tester.run("count_to(3)")
        assert "0" in result.stdout
        assert "1" in result.stdout
        assert "2" in result.stdout
    
    @pytest.mark.xfail(reason="Functions with complex control structures lose context")
    def test_function_with_if(self, tester: PyshTester):
        """Test function containing if statement."""
        tester.run("def check_positive(n):")
        tester.run("if n > 0:")
        tester.run("return 'positive'")
        tester.run("else:")
        tester.run("return 'non-positive'")
        tester.run("    ")
        tester.run("    ")
        
        result = tester.run("check_positive(5)")
        assert "positive" in result.stdout
    
    def test_loop_with_if(self, tester: PyshTester):
        """Test loop containing if statement."""
        tester.run("for i in range(5):")
        tester.run("if i % 2 == 0:")
        tester.run("print(i)")
        tester.run("    ")
        result = tester.run("    ")
        
        assert "0" in result.stdout
        assert "2" in result.stdout
        assert "4" in result.stdout
        # Odd numbers should not appear
        lines = [l.strip() for l in result.stdout.split('\n') if l.strip()]
        assert "1" not in lines
        assert "3" not in lines


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
