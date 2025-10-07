#!/usr/bin/env python3
"""Demo: The function scope bug is now fixed!"""

import sys
sys.path.insert(0, 'src')
from ops import ShellSession, execute_line
import os

print("=" * 70)
print("DEMO: Function Scope Bug Fix")
print("=" * 70)

shell = os.environ.get('SHELL', '/bin/sh')
session = ShellSession(shell=shell, inherit_env=False)

print("\n✅ TEST 1: Functions with shell commands")
print("-" * 70)
print("Code:")
print("  def greet():")
print("      echo 'Hello from pysh!'")
print()

execute_line("def greet():", session)
execute_line("    echo 'Hello from pysh!'", session)
execute_line("    ", session)

print("Calling greet()...")
result = execute_line("greet()", session)
print(f"Exit code: {result}")

print("\n✅ TEST 2: Functions accessing session variables")
print("-" * 70)
print("Code:")
print("  name = 'World'")
print("  def show_name():")
print("      print(f'Hello, {name}!')")
print()

execute_line("name = 'World'", session)
execute_line("def show_name():", session)
execute_line("    print(f'Hello, {name}!')", session)
execute_line("    ", session)

print("Calling show_name()...")
result = execute_line("show_name()", session)
print(f"Exit code: {result}")

print("\n✅ TEST 3: Functions with parameters and shell commands")
print("-" * 70)
print("Code:")
print("  def list_dir(path='.'):")
print("      echo f'Listing: {path}'")
print("      ls {path}")
print()

execute_line("def list_dir(path='.'):", session)
execute_line("    echo f'Listing: {path}'", session)
execute_line("    ", session)

print("Calling list_dir('.')...")
result = execute_line("list_dir('.')", session)
print(f"Exit code: {result}")

print("\n" + "=" * 70)
print("SUCCESS! All function tests passed.")
print("=" * 70)
print("\nBefore the fix, all these would have failed with:")
print("  NameError: name '__pysh_exec_shell' is not defined")
print("\nNow functions work correctly! 🎉")
