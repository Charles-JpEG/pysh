#!/usr/bin/env python3
"""Interactive loop tests using pexpect to reach 95% coverage"""

import sys
import os
from pathlib import Path
import subprocess
import time

# Add src to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pytest

# Try to import pexpect
try:
    import pexpect
    HAS_PEXPECT = True
except ImportError:
    HAS_PEXPECT = False
    pytestmark = pytest.mark.skip(reason="pexpect not installed")


@pytest.mark.skipif(not HAS_PEXPECT, reason="requires pexpect")
class TestInteractiveLoop:
    """Test interactive loop with pexpect"""
    
    def test_empty_line_continues(self):
        """Test that empty line prompts again"""
        child = pexpect.spawn('python3', [str(ROOT / 'src' / 'main.py')], timeout=5, cwd=str(ROOT))
        try:
            child.expect('pysh> ')
            child.sendline('')  # Empty line
            child.expect('pysh> ')  # Should prompt again
            child.sendline('exit()')
            child.expect(pexpect.EOF)
            child.close()
            assert child.exitstatus == 0
        finally:
            if child.isalive():
                child.terminate(force=True)
    
    def test_ctrl_d_exits(self):
        """Test that Ctrl-D exits"""
        child = pexpect.spawn('python3', [str(ROOT / 'src' / 'main.py')], timeout=5, cwd=str(ROOT))
        try:
            child.expect('pysh> ')
            child.sendcontrol('d')  # Send EOF
            child.expect(pexpect.EOF)
            child.close()
            assert True  # Successfully exited
        finally:
            if child.isalive():
                child.terminate(force=True)
    
    def test_ctrl_c_continues(self):
        """Test that Ctrl-C at prompt continues"""
        child = pexpect.spawn('python3', [str(ROOT / 'src' / 'main.py')], timeout=5, cwd=str(ROOT))
        try:
            child.expect('pysh> ')
            child.sendcontrol('c')  # Send SIGINT
            child.expect('pysh> ')  # Should prompt again
            child.sendline('exit()')
            child.expect(pexpect.EOF)
            child.close()
            assert child.exitstatus == 0
        finally:
            if child.isalive():
                child.terminate(force=True)
    
    def test_multiline_continuation_prompt(self):
        """Test multiline mode shows continuation prompt"""
        child = pexpect.spawn('python3', [str(ROOT / 'src' / 'main.py')], timeout=5, cwd=str(ROOT))
        try:
            child.expect('pysh> ')
            child.sendline('def foo():')
            child.expect(r'\.\.\. ')  # Continuation prompt
            child.sendline('    return 42')
            child.expect(r'\.\.\. ')
            child.sendline('')  # Empty line to complete
            child.expect('pysh> ')
            child.sendline('exit()')
            child.expect(pexpect.EOF)
            child.close()
            assert child.exitstatus == 0
        finally:
            if child.isalive():
                child.terminate(force=True)
    
    def test_multiline_with_indentation(self):
        """Test multiline indentation handling"""
        child = pexpect.spawn('python3', [str(ROOT / 'src' / 'main.py')], timeout=5, cwd=str(ROOT))
        try:
            child.expect('pysh> ')
            child.sendline('if True:')
            child.expect(r'\.\.\. ')
            # Readline should provide indentation
            child.sendline('    x = 1')
            child.expect(r'\.\.\. ')
            child.sendline('')
            child.expect('pysh> ')
            child.sendline('exit()')
            child.expect(pexpect.EOF)
            child.close()
            assert child.exitstatus == 0
        finally:
            if child.isalive():
                child.terminate(force=True)
    
    def test_execute_line_success(self):
        """Test successful command execution"""
        child = pexpect.spawn('python3', [str(ROOT / 'src' / 'main.py')], timeout=5, cwd=str(ROOT))
        try:
            child.expect('pysh> ')
            child.sendline('x = 5')
            child.expect('pysh> ')
            child.sendline('print(x)')
            child.expect('5')
            child.expect('pysh> ')
            child.sendline('exit()')
            child.expect(pexpect.EOF)
            child.close()
            assert child.exitstatus == 0
        finally:
            if child.isalive():
                child.terminate(force=True)
    
    def test_execute_line_with_error(self):
        """Test command that causes error"""
        child = pexpect.spawn('python3', [str(ROOT / 'src' / 'main.py')], timeout=5, cwd=str(ROOT))
        try:
            child.expect('pysh> ')
            child.sendline('1 / 0')
            child.expect('pysh> ')  # Should continue after error
            child.sendline('exit()')
            child.expect(pexpect.EOF)
            child.close()
            assert child.exitstatus == 0
        finally:
            if child.isalive():
                child.terminate(force=True)


@pytest.mark.skipif(not HAS_PEXPECT, reason="requires pexpect")
class TestInteractiveReadline:
    """Test readline-specific interactive features"""
    
    def test_continuation_with_indent_prefill(self):
        """Test that continuation provides indent prefill"""
        child = pexpect.spawn('python3', [str(ROOT / 'src' / 'main.py')], timeout=5, cwd=str(ROOT))
        try:
            child.expect('pysh> ')
            child.sendline('for i in range(1):')
            child.expect(r'\.\.\. ')
            # Readline should prefill indent
            child.sendline('pass')
            child.expect(r'\.\.\. ')
            child.sendline('')
            child.expect('pysh> ')
            child.sendline('exit()')
            child.expect(pexpect.EOF)
            child.close()
            assert child.exitstatus == 0
        finally:
            if child.isalive():
                child.terminate(force=True)
    
    def test_dedent_with_else(self):
        """Test dedentation with else"""
        child = pexpect.spawn('python3', [str(ROOT / 'src' / 'main.py')], timeout=5, cwd=str(ROOT))
        try:
            child.expect('pysh> ')
            child.sendline('if True:')
            child.expect(r'\.\.\. ')
            child.sendline('    x = 1')
            child.expect(r'\.\.\. ')
            child.sendline('else:')
            child.expect(r'\.\.\. ')
            child.sendline('    x = 2')
            child.expect(r'\.\.\. ')
            child.sendline('')
            child.expect('pysh> ')
            child.sendline('exit()')
            child.expect(pexpect.EOF)
            child.close()
            assert child.exitstatus == 0
        finally:
            if child.isalive():
                child.terminate(force=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
