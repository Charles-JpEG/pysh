# Bug Fix Report: Function Scope Issue

## Summary
Fixed the critical bug where Python functions defined in pysh could not execute shell commands or access session variables.

## The Problem
Functions defined in pysh failed with `NameError: name '__pysh_exec_shell' is not defined` when trying to execute shell commands or access variables.

### Root Cause
The helper function `__pysh_exec_shell` was created in the **local namespace** (`exec_locals`) during function definition, but Python functions capture their global namespace at definition time. Since `exec_globals` didn't contain `__pysh_exec_shell`, functions couldn't find it when called later.

Similarly, session variables were not available to functions because they were not in the function's global namespace.

## The Fix
Changed `src/ops.py` lines 398-403 to include both `__pysh_exec_shell` and session variables in `exec_globals`:

### Before (Buggy):
```python
exec_locals['__pysh_exec_shell'] = lambda cmd: pysh_exec_shell_with_locals(cmd, exec_locals)

exec(code, {"__builtins__": __builtins__}, exec_locals)
```

### After (Fixed):
```python
# Create exec_globals with __pysh_exec_shell and session variables
# so functions can access both shell execution context and session variables
exec_globals = dict(session.py_vars)
exec_globals["__builtins__"] = __builtins__
exec_globals["__pysh_exec_shell"] = lambda cmd: pysh_exec_shell_with_locals(cmd, exec_locals)

exec(code, exec_globals, exec_locals)
```

## Test Results

### Before Fix:
- **418 passed, 5 xfailed** (all xfails related to this bug)

### After Fix:
- **421 passed, 3 xfailed** ✅
- **2 tests fixed and now passing:**
  1. `test_function_with_shell_command` - Functions can now execute shell commands
  2. `test_function_accesses_variable` - Functions can now access session variables

### Remaining xfails (unrelated issues):
1. `test_function_with_return` - Multiline handling issue with `return` statements
2. `test_nested_function_calls` - Nested functions with return statements  
3. `test_function_with_if` - Functions with if statements containing shell commands

## Verification

Test that now works:
```python
# Define function with shell command
def test_func():
    echo "hello"

# Call it
test_func()  # ✅ Now prints "hello" instead of NameError
```

Test that now works:
```python
# Define variable
x = 42

# Define function that accesses it
def show_x():
    print(x)

# Call it  
show_x()  # ✅ Now prints "42" instead of NameError
```

## Impact
This fix enables a core feature of pysh: **Python functions that can execute shell commands and access session state**. Functions are now usable for scripting, which significantly improves pysh's practicality as a shell.

---
*Fixed: 2025-10-07*
*Files changed: `src/ops.py`, `tests/test_control_structures.py`*
