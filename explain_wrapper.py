#!/usr/bin/env python3
"""Explaining where __pysh_exec_shell lives and why it causes a bug."""

print("=" * 70)
print("WHERE IS __pysh_exec_shell?")
print("=" * 70)

# Simulating what pysh does
print("\n1. DURING FUNCTION DEFINITION (in try_python function)")
print("-" * 70)

# This is what pysh does (simplified):
exec_locals = {}
exec_globals = {"__builtins__": __builtins__}

# Create the temporary wrapper
exec_locals['__pysh_exec_shell'] = lambda cmd: f"Would execute: {cmd}"

print(f"exec_globals keys: {list(exec_globals.keys())}")
print(f"exec_locals keys: {list(exec_locals.keys())}")

# Define function using exec (like pysh does)
code = """
def test_func():
    return __pysh_exec_shell("echo hello")
"""

exec(code, exec_globals, exec_locals)
print(f"\nAfter exec, exec_locals keys: {list(exec_locals.keys())}")

# Get the function
test_func = exec_locals['test_func']
print(f"\nFunction defined: {test_func}")
print(f"Function's __globals__ keys: {list(test_func.__globals__.keys())}")
print(f"__pysh_exec_shell in function's __globals__? {('__pysh_exec_shell' in test_func.__globals__)}")

print("\n2. AFTER FUNCTION DEFINITION")
print("-" * 70)
print("exec_locals is discarded (it was just a temporary dict)")
print("The function 'test_func' is saved to session.py_vars")
print("But __pysh_exec_shell is LOST - it was only in exec_locals!")

print("\n3. WHEN FUNCTION IS CALLED LATER")
print("-" * 70)
print("Trying to call test_func()...")
try:
    result = test_func()
    print(f"Result: {result}")
except NameError as e:
    print(f"❌ ERROR: {e}")
    print("\nWhy? Because:")
    print("  - __pysh_exec_shell was in exec_locals (temporary)")
    print("  - Function's __globals__ only has __builtins__")
    print("  - exec_locals was thrown away after the def statement")
    print("  - Now __pysh_exec_shell doesn't exist anywhere!")

print("\n" + "=" * 70)
print("THE BUG SUMMARY")
print("=" * 70)
print("""
__pysh_exec_shell is a TEMPORARY wrapper function that:
  ✓ EXISTS during the 'def' statement execution (in exec_locals)
  ✗ DOES NOT EXIST when the function is called later
  
The function needs it but can't find it because:
  - It's not in the function's __globals__ (only __builtins__ is there)
  - exec_locals where it was defined is temporary and discarded
  
FIX: Put __pysh_exec_shell in exec_globals instead of exec_locals
     so it becomes part of the function's __globals__
""")

print("\n" + "=" * 70)
print("PROOF OF FIX")
print("=" * 70)

# The fix:
exec_locals_fixed = {}
exec_globals_fixed = {
    "__builtins__": __builtins__,
    "__pysh_exec_shell": lambda cmd: f"Would execute: {cmd}"  # Now in globals!
}

exec(code, exec_globals_fixed, exec_locals_fixed)
test_func_fixed = exec_locals_fixed['test_func']

print(f"Fixed function's __globals__ keys: {list(test_func_fixed.__globals__.keys())}")
print(f"__pysh_exec_shell in function's __globals__? {('__pysh_exec_shell' in test_func_fixed.__globals__)}")

print("\nCalling fixed function...")
result = test_func_fixed()
print(f"✓ SUCCESS: {result}")
