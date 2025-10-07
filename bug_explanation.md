# The Function Scope Bug in pysh

## Problem Summary
Python functions defined in pysh cannot access `__pysh_exec_shell`, causing all shell commands within functions to fail with `NameError`.

## Root Cause: Python's Function Closure Mechanism

### How pysh Executes Python Code

When you define a function in pysh:

```python
def test_func():
    echo "hello"   # This is a shell command
```

#### Step 1: Code Transformation
The shell command gets transformed to use `__pysh_exec_shell`:
```python
def test_func():
    __pysh_exec_shell('echo "hello"')
```

#### Step 2: Execution with exec()
In `src/ops.py:398-401`, pysh executes this code:

```python
exec_locals['__pysh_exec_shell'] = lambda cmd: pysh_exec_shell_with_locals(cmd, exec_locals)

exec(code, {"__builtins__": __builtins__}, exec_locals)
#          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^^^^
#          GLOBALS dict (minimal)            LOCALS dict (has __pysh_exec_shell)
```

#### Step 3: The Problem - Function's __globals__
When Python's `def` statement creates a function object:
- **The function's `__globals__` attribute points to the GLOBALS dict from exec()**
- In pysh's case: `{"__builtins__": __builtins__}` - **DOES NOT CONTAIN __pysh_exec_shell**
- `__pysh_exec_shell` is in LOCALS, not GLOBALS

```
┌─────────────────────────────────────────────────────────────┐
│  exec() Call                                                │
│                                                             │
│  GLOBALS = {"__builtins__": __builtins__}                  │
│            ↑                                                │
│            │ Function.__globals__ points here              │
│            │ (does NOT have __pysh_exec_shell)             │
│                                                             │
│  LOCALS = {                                                 │
│      "__pysh_exec_shell": <lambda>,  ← Defined here        │
│      "test_func": <function>         ← Function defined    │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
```

#### Step 4: Function Call Fails
When `test_func()` is called:
1. Python looks for `__pysh_exec_shell` in the function's scope
2. Not found locally in function
3. Checks function's `__globals__` → Only has `__builtins__`
4. **NameError: name '__pysh_exec_shell' is not defined**

## Proof of Bug

Run this test:
```bash
$ cd /home/charles/Projects/pysh
$ python3 debug_function.py
```

Output shows:
```
Function __globals__ keys: ['__builtins__']
Has __pysh_exec_shell in globals? False

pysh(py-eval): name '__pysh_exec_shell' is not defined
```

## Why This Happens

**Python closure rule**: Functions capture variables from:
1. Local scope (function's own variables)
2. **Enclosing scope (`__globals__` - set at function DEFINITION time)**
3. Built-ins

The `exec()` call uses **different namespaces for globals and locals**:
- `__pysh_exec_shell` goes into **locals** (exec_locals)
- But function's `__globals__` is set to the **globals** dict
- **Locals are NOT searched when function is called later!**

## Affected Functionality

All 5 xfail tests document this bug:

1. ✗ `test_function_with_return` - Functions returning values that use shell context
2. ✗ `test_function_with_shell_command` - Functions containing shell commands  
3. ✗ `test_function_accesses_variable` - Functions accessing session variables
4. ✗ `test_nested_function_calls` - Nested function calls
5. ✗ `test_function_with_if` - Functions with if statements containing shell commands

## Solution Options

### Option 1: Put __pysh_exec_shell in globals (RECOMMENDED)
```python
# In try_python(), line 398-401:
exec_globals = {"__builtins__": __builtins__, "__pysh_exec_shell": ...}
exec(code, exec_globals, exec_locals)
```

### Option 2: Use a single namespace
```python
# Merge globals and locals
namespace = {"__builtins__": __builtins__}
namespace['__pysh_exec_shell'] = lambda cmd: pysh_exec_shell_with_locals(cmd, namespace)
exec(code, namespace, namespace)
```

### Option 3: Inject into session.py_vars and use as globals
```python
# Make session.py_vars the global namespace
session.py_vars['__pysh_exec_shell'] = ...
exec(code, session.py_vars, exec_locals)
```

## Impact

This is a **critical bug** that breaks a core feature of pysh:
- Per the spec: "within functions, loops or if-else conditions, pysh will look for variables and functions first"
- Functions are supposed to work like Python functions but have access to shell commands
- Currently, **all functions with shell commands fail**

## Test Status

- **419 tests pass** (basic functionality works)
- **5 tests xfail** (all document this same bug)
- Bug prevents pysh from being a practical shell for scripting

---

*Analysis Date: 2025-10-07*
*pysh Version: From cleanup_tests branch*
