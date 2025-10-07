#!/usr/bin/env python3
"""Tracing where variable expansion happens for function parameters."""

import sys
sys.path.insert(0, 'src')
from ops import ShellSession, execute_line
import os

# Monkey-patch to trace calls
original_expand = None

def trace_expand(line, session, **kwargs):
    print(f"  _expand_vars_in_line called with: {repr(line)}")
    print(f"  session.py_vars keys: {list(session.py_vars.keys())}")
    result = original_expand(line, session, **kwargs)
    print(f"  Result: {repr(result)}")
    return result

# Patch it
import ops
original_expand = ops._expand_vars_in_line
ops._expand_vars_in_line = trace_expand

print("=" * 70)
print("TRACING VARIABLE EXPANSION")
print("=" * 70)

shell = os.environ.get('SHELL', '/bin/sh')
session = ShellSession(shell=shell, inherit_env=False)

print("\nDefining function...")
execute_line('def show(msg):', session)
execute_line('    echo $msg', session)
execute_line('    ', session)

print("\nCalling show('Hello')...")
result = execute_line('show("Hello")', session)
print(f"\nExit code: {result}")
