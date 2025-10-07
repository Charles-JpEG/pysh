#!/usr/bin/env python3
import sys
sys.path.insert(0, 'src')
from ops import ShellSession, execute_line
import os

# Create session
shell = os.environ.get('SHELL', '/bin/sh')
session = ShellSession(shell=shell, inherit_env=False)

# Define a function with a shell command
print("=== Defining function ===")
execute_line('def test_func():', session)
execute_line('    echo "hello from function"', session)
execute_line('    ', session)

print("\n=== Function defined ===")
print("py_vars keys:", list(session.py_vars.keys()))

# Let's inspect the function
if 'test_func' in session.py_vars:
    func = session.py_vars['test_func']
    print(f"\nFunction object: {func}")
    print(f"Function __globals__ keys: {list(func.__globals__.keys())}")
    print(f"Has __pysh_exec_shell in globals? {'__pysh_exec_shell' in func.__globals__}")

print("\n=== Now calling test_func() ===")
result = execute_line('test_func()', session)
print(f"Result: {result}")
