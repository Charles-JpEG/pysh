#!/usr/bin/env python3

"""
Main module for pysh:
    - Main shell loop
    - Tokenize and group commands
"""
    

from dataclasses import dataclass
import os
import shlex
import sys

OPERATORS = {"|", "||", "&&", ";", "&"}

@dataclass
class CommandGroup:
    parts: list[str]

@dataclass
class OperatorGroup:
    op: str

Group = CommandGroup | OperatorGroup


# Line to Tokens
def tokenize(line: str) -> list[str]:
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


# Tokens to Groups
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


# Line to Groups
def split_line(line: str) -> list[Group]:
    return group_tokens(tokenize(line))


# Format groups for display <TEST>
def format_groups(groups: list[Group]) -> str:
    lines: list[str] = []
    for g in groups:
        if isinstance(g, CommandGroup):
            lines.append("CMD  " + ' '.join(g.parts))
        else:
            lines.append("OP   " + g.op)
    return "\n".join(lines) if lines else "<empty>"


def main():
    if len(sys.argv) > 1:
        line = ' '.join(sys.argv[1:])
        print(format_groups(split_line(line)))
        return
    print("pysh <dry run>\n")   # <FIXME>
    # main loop
    while True:
        try:
            cwd = os.getcwd()
            home = os.path.expanduser('~')
            if cwd.startswith(home):
                cwd = cwd.replace(home, '~', 1)
            line = input(f"{cwd}> ")    # TODO: Use template from env or config
        except EOFError:
            sys.exit(0)
        except KeyboardInterrupt:
            print()
            continue
        line = line.strip()
        if not line:
            continue
        groups = split_line(line)
        # Display Command <TEST>
        print(format_groups(groups))

if __name__ == '__main__':
    main()