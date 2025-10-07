#!/usr/bin/env python3
"""Testing function parameter access with $var syntax."""

import sys
sys.path.insert(0, 'src')
from ops import ShellSession, execute_line
import os

print("=" * 70)
print("BUG: Function parameters not accessible via $var")
print("=" * 70)

shell = os.environ.get('SHELL', '/bin/sh')
session = ShellSession(shell=shell, inherit_env=False)

print("\nTest 1: Function parameter with Python print")
print("-" * 70)
execute_line('def greet(name):', session)
execute_line('    print(f"Hello {name}")', session)
execute_line('    ', session)

print("Calling greet('Alice')...")
result = execute_line('greet("Alice")', session)
print(f"Exit code: {result}")

print("\n" + "=" * 70)
print("\nTest 2: Function parameter with shell command using $var")
print("-" * 70)
execute_line('def show(msg):', session)
execute_line('    echo $msg', session)
execute_line('    ', session)

print("Calling show('Hello')...")
result = execute_line('show("Hello")', session)
print(f"Exit code: {result}")

print("\n" + "=" * 70)
print("\nTest 3: Function parameter with shell command using {var}")
print("-" * 70)
execute_line('def display(text):', session)
execute_line('    echo {text}', session)
execute_line('    ', session)

print("Calling display('World')...")
result = execute_line('display("World")', session)
print(f"Exit code: {result}")

print("\n" + "=" * 70)
print("ANALYSIS")
print("=" * 70)
print("""
Expected behavior:
  - Function parameters should be accessible with $param syntax
  - This is critical for shell command interop
  
Current behavior:
  - Need to test if $param works in shell commands within functions
""")
