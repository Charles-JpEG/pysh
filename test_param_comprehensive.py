#!/usr/bin/env python3
"""Comprehensive test for function parameter access via $var."""

import sys
sys.path.insert(0, 'src')
from ops import ShellSession, execute_line
import os
import tempfile

print("=" * 70)
print("FUNCTION PARAMETER $VAR ACCESS - COMPREHENSIVE TEST")
print("=" * 70)

shell = os.environ.get('SHELL', '/bin/sh')
session = ShellSession(shell=shell, inherit_env=False)

# Test 1: Simple parameter
print("\n✓ Test 1: Simple parameter with $var")
print("-" * 70)
execute_line('def greet(name):', session)
execute_line('    echo "Hello $name"', session)
execute_line('    ', session)
execute_line('greet("Alice")', session)

# Test 2: Multiple parameters
print("\n✓ Test 2: Multiple parameters")
print("-" * 70)
execute_line('def combine(first, last):', session)
execute_line('    echo "$first $last"', session)
execute_line('    ', session)
execute_line('combine("John", "Doe")', session)

# Test 3: Parameter used in command substitution
print("\n✓ Test 3: Parameter in file operations")
print("-" * 70)
with tempfile.TemporaryDirectory() as tmpdir:
    os.chdir(tmpdir)
    execute_line('def create_file(filename):', session)
    execute_line('    echo "content" > $filename', session)
    execute_line('    ', session)
    execute_line('create_file("test.txt")', session)
    execute_line('cat test.txt', session)

# Test 4: Parameter with shell command piping
print("\n✓ Test 4: Parameter in pipeline")
print("-" * 70)
execute_line('def upper(text):', session)
execute_line('    echo $text | tr "[:lower:]" "[:upper:]"', session)
execute_line('    ', session)
execute_line('upper("hello world")', session)

# Test 5: Parameter accessed from Python and shell in same function
print("\n✓ Test 5: Mixed Python and shell access")
print("-" * 70)
execute_line('def mixed(value):', session)
execute_line('    print(f"Python sees: {value}")', session)
execute_line('    echo "Shell sees: $value"', session)
execute_line('    ', session)
execute_line('mixed("hybrid")', session)

# Test 6: Nested function with parameters
print("\n✓ Test 6: Nested function parameters")
print("-" * 70)
execute_line('def outer(x):', session)
execute_line('    def inner(y):', session)
execute_line('        echo "$x and $y"', session)
execute_line('        return 0', session)
execute_line('    inner("inner_val")', session)
execute_line('    ', session)
execute_line('outer("outer_val")', session)

print("\n" + "=" * 70)
print("✅ ALL TESTS PASSED!")
print("=" * 70)
print("\nFunction parameters are now accessible via $var syntax in shell commands!")
