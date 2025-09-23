"""Grouping and tokenization utilities for pysh.

This module defines the data structures representing parsed shell line
components (commands and control operators) and helper functions to
convert a raw input line into a sequence of these groups.
"""
from __future__ import annotations

from dataclasses import dataclass
import shlex
from typing import Iterable

# Recognized control operators (subset for now)
OPERATORS = {"|", "||", "&&", ";", "&"}

@dataclass
class CommandGroup:
    """A simple command with its argv tokens (argv[0] is the program)."""
    parts: list[str]

@dataclass
class OperatorGroup:
    """A control operator separating commands (e.g., |, &&, ;)."""
    op: str

# Discriminated union type alias
Group = CommandGroup | OperatorGroup

# --- Tokenization ---

def tokenize(line: str) -> list[str]:
    """Split an input line into shell-like tokens plus control operators.

    We leverage shlex with punctuation_chars to keep operators separate,
    then post-process to merge doubled operators like &&, ||.
    """
    lexer = shlex.shlex(line, posix=True, punctuation_chars=';&|')
    lexer.commenters = ''
    lexer.whitespace_split = True
    raw = list(lexer)
    out: list[str] = []
    i = 0
    while i < len(raw):
        t = raw[i]
        if t in ('&', '|') and i + 1 < len(raw) and raw[i + 1] == t:
            out.append(t * 2)
            i += 2
            continue
        out.append(t)
        i += 1
    return out

# --- Grouping ---

def group_tokens(tokens: list[str]) -> list[Group]:
    groups: list[Group] = []
    buf: list[str] = []
    def flush():
        nonlocal buf
        if buf:
            groups.append(CommandGroup(buf))
            buf = []
    for tok in tokens:
        if tok in OPERATORS:
            flush()
            groups.append(OperatorGroup(tok))
        else:
            buf.append(tok)
    flush()
    return groups

# --- Public helpers ---

def split_line(line: str) -> list[Group]:
    return group_tokens(tokenize(line))

# --- Formatting (debug / test aid) ---

def format_groups(groups: Iterable[Group]) -> str:
    lines: list[str] = []
    for g in groups:
        if isinstance(g, CommandGroup):
            lines.append("CMD  " + ' '.join(g.parts))
        else:
            lines.append("OP   " + g.op)
    return "\n".join(lines) if lines else "<empty>"
