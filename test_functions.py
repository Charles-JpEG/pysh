#!/usr/bin/env python3
import sys
sys.path.insert(0, 'src')

from ops import ShellSession, execute_line

session = ShellSession('/bin/sh')

# Test: Can we define and call a function?
print("=== Test 1: Define and call function ===")
execute_line('def test_func():', session)
execute_line('    return 42', session)
result = execute_line('', session)
print(f'Define function result: {result}')

if 'test_func' in session.py_vars:
    print(f'test_func exists in py_vars: YES')
    print(f'Calling directly: {session.py_vars["test_func"]()}')
else:
    print('test_func exists in py_vars: NO')

result2 = execute_line('test_func()', session)
print(f'Call function via execute_line result: {result2}')
