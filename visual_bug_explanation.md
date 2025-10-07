## The __pysh_exec_shell Bug - Visual Explanation

### What is `__pysh_exec_shell`?

It's a **temporary wrapper function** that pysh creates to execute shell commands from within Python code. It's NOT related to the `echo` command itself.

### The Bug in 3 Acts

```
┌─────────────────────────────────────────────────────────────────┐
│ ACT 1: DEFINING THE FUNCTION                                    │
│                                                                 │
│ You type:                                                       │
│   def test_func():                                              │
│       echo "hello"                                              │
│                                                                 │
│ Pysh transforms it to:                                          │
│   def test_func():                                              │
│       __pysh_exec_shell("echo 'hello'")                         │
│                           ↑                                     │
│                           'echo' is just a string argument      │
│                                                                 │
│ Pysh executes using exec():                                     │
│                                                                 │
│   exec_globals = {"__builtins__": ...}                          │
│   exec_locals = {}                                              │
│                                                                 │
│   # Create temporary wrapper (WRONG LOCATION!)                 │
│   exec_locals['__pysh_exec_shell'] = λ                          │
│                                                                 │
│   exec(code, exec_globals, exec_locals)                         │
│              ^^^^^^^^^^^^  ^^^^^^^^^^^                          │
│              These are     __pysh_exec_shell                    │
│              what function is HERE temporarily                  │
│              will see                                           │
│                                                                 │
│ Result:                                                         │
│   ┌─────────────────────────────────────┐                      │
│   │ test_func.__globals__               │                      │
│   │ ┌───────────────────────────────┐   │                      │
│   │ │ __builtins__: <module>        │   │                      │
│   │ │ (NO __pysh_exec_shell here!)  │   │                      │
│   │ └───────────────────────────────┘   │                      │
│   └─────────────────────────────────────┘                      │
│                                                                 │
│   exec_locals is DISCARDED after exec() completes              │
│   __pysh_exec_shell is LOST!                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ ACT 2: SAVING THE FUNCTION                                      │
│                                                                 │
│ Pysh saves test_func to session.py_vars:                        │
│                                                                 │
│   session.py_vars['test_func'] = <function test_func>           │
│                                                                 │
│ But __pysh_exec_shell is NOT saved anywhere!                    │
│ It was only in exec_locals, which is now gone.                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ ACT 3: CALLING THE FUNCTION (LATER)                             │
│                                                                 │
│ You type:                                                       │
│   test_func()                                                   │
│                                                                 │
│ Execution:                                                      │
│   1. test_func runs                                             │
│   2. It tries to call: __pysh_exec_shell("echo 'hello'")        │
│   3. Python searches for __pysh_exec_shell:                     │
│                                                                 │
│      Search order:                                              │
│      ┌─────────────────────────────────────────┐               │
│      │ 1. Local scope (function variables)    │               │
│      │    ❌ Not found                         │               │
│      │                                         │               │
│      │ 2. Function's __globals__               │               │
│      │    ❌ Not found (only __builtins__)     │               │
│      │                                         │               │
│      │ 3. Built-ins                            │               │
│      │    ❌ Not found                         │               │
│      └─────────────────────────────────────────┘               │
│                                                                 │
│   4. ❌ NameError: name '__pysh_exec_shell' is not defined      │
│                                                                 │
│ Why it fails:                                                   │
│   - __pysh_exec_shell was created in exec_locals (temporary)    │
│   - Function's __globals__ doesn't have it                      │
│   - exec_locals was discarded after function definition         │
│   - The wrapper is GONE when the function tries to use it!      │
└─────────────────────────────────────────────────────────────────┘
```

### The Key Points

1. **`echo` is NOT stored as a function** - it's just a string: `"echo 'hello'"`

2. **`__pysh_exec_shell` IS a function** - a temporary wrapper that executes shell commands

3. **The Bug**: `__pysh_exec_shell` is created in the **wrong place**:
   - ❌ Created in `exec_locals` (temporary, discarded after `def`)
   - ✅ Should be in `exec_globals` (persistent, part of function's scope)

4. **When the function is called later**:
   - It needs `__pysh_exec_shell` to execute the shell command
   - But `__pysh_exec_shell` doesn't exist anymore
   - Result: NameError

### The Fix (One Line Change)

In `src/ops.py` line 398-401:

**BEFORE (buggy):**
```python
exec_locals['__pysh_exec_shell'] = lambda cmd: pysh_exec_shell_with_locals(cmd, exec_locals)
#           ^^^^^^^ Wrong place!
exec(code, {"__builtins__": __builtins__}, exec_locals)
```

**AFTER (fixed):**
```python
exec_globals = {
    "__builtins__": __builtins__,
    "__pysh_exec_shell": lambda cmd: pysh_exec_shell_with_locals(cmd, exec_locals)
    #                    ^^^^^^^ Right place!
}
exec(code, exec_globals, exec_locals)
```

Now `__pysh_exec_shell` will be in the function's `__globals__` and accessible when the function is called!
