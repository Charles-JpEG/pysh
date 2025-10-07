#!/usr/bin/env python3
"""Detailed trace showing exactly how the bug occurs."""

import sys
sys.path.insert(0, 'src')
from ops import ShellSession, execute_line
import os

print("=" * 70)
print("DETAILED TRACE: The Function Scope Bug")
print("=" * 70)

# Create session
shell = os.environ.get('SHELL', '/bin/sh')
session = ShellSession(shell=shell, inherit_env=False)

print("\n1. DEFINING THE FUNCTION")
print("-" * 70)
print("Input code:")
print("  def test_func():")
print("      echo 'hello'")
print()

execute_line('def test_func():', session)
execute_line("    echo 'hello'", session)
execute_line('    ', session)

print("2. INSPECTING THE DEFINED FUNCTION")
print("-" * 70)
func = session.py_vars['test_func']
print(f"Function object: {func}")
print(f"Function name: {func.__name__}")
print(f"Function code: {func.__code__}")
print()
print(f"Function's __globals__ dictionary contents:")
for key in sorted(func.__globals__.keys()):
    val = func.__globals__[key]
    if key == '__builtins__':
        print(f"  {key}: <module> (standard Python builtins)")
    else:
        print(f"  {key}: {val}")

print()
print(f"🔍 Critical observation:")
print(f"   '__pysh_exec_shell' in function.__globals__? {('__pysh_exec_shell' in func.__globals__)}")
print()

print("3. WHAT THE FUNCTION BODY ACTUALLY CONTAINS")
print("-" * 70)
import dis
print("Disassembly of test_func:")
dis.dis(func)
print()

print("4. CALLING THE FUNCTION")
print("-" * 70)
print("When test_func() executes:")
print("  1. It tries to call: __pysh_exec_shell('echo \"hello\"')")
print("  2. Python looks for __pysh_exec_shell in:")
print("     a) Local variables (function scope) → Not found")
print("     b) Function's __globals__ → Not found (only has __builtins__)")
print("  3. NameError is raised!")
print()
print("Calling test_func()...")
result = execute_line('test_func()', session)
print(f"Exit code: {result}")
print()

print("5. WHERE IS __pysh_exec_shell?")
print("-" * 70)
print("It was defined in exec_locals during the 'def' statement execution,")
print("but Python functions capture their __globals__ at definition time,")
print("and exec() was called with:")
print()
print("  exec(code, globals_dict, locals_dict)")
print("            ^^^^^^^^^^^^  ^^^^^^^^^^^")
print("            Only __builtins__  Had __pysh_exec_shell")
print()
print("The function's __globals__ points to globals_dict, which doesn't")
print("contain __pysh_exec_shell!")
print()

print("6. THE FIX")
print("-" * 70)
print("Solution: Put __pysh_exec_shell in the globals dict passed to exec():")
print()
print("  BEFORE (buggy):")
print("    exec_globals = {'__builtins__': __builtins__}")
print("    exec_locals['__pysh_exec_shell'] = lambda cmd: ...")
print("    exec(code, exec_globals, exec_locals)")
print()
print("  AFTER (fixed):")
print("    exec_globals = {'__builtins__': __builtins__,")
print("                    '__pysh_exec_shell': lambda cmd: ...}")
print("    exec(code, exec_globals, exec_locals)")
print()

print("=" * 70)
print("END OF TRACE")
print("=" * 70)
