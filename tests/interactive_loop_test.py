#!/usr/bin/env python3
"""Integration tests validating interactive loop handling in pysh."""

from __future__ import annotations

import pytest  # type: ignore

from test_framework import PyshTester


@pytest.fixture()
def tester():
    with PyshTester() as instance:
        yield instance


def test_for_loop_executes_after_blank_line(tester: PyshTester) -> None:
    first = tester.run("for i in range(3):")
    assert first.stderr == ""
    assert first.stdout == ""
    assert first.prompt == tester.continuation_prompt

    second = tester.run("    print(i)")
    assert second.stderr == ""
    assert second.stdout == ""
    assert second.prompt == tester.continuation_prompt

    finisher = tester.run("")
    assert finisher.stderr == ""
    assert finisher.prompt == tester.prompt
    assert finisher.stdout == "0\n1\n2\n"


def test_while_loop_updates_state(tester: PyshTester) -> None:
    init = tester.run("i = 0")
    assert init.stderr == ""
    assert init.prompt == tester.prompt

    header = tester.run("while i < 3:")
    assert header.stderr == ""
    assert header.stdout == ""
    assert header.prompt == tester.continuation_prompt

    body_one = tester.run("    print(i)")
    assert body_one.stderr == ""
    assert body_one.stdout == ""
    assert body_one.prompt == tester.continuation_prompt

    body_two = tester.run("    i += 1")
    assert body_two.stderr == ""
    assert body_two.stdout == ""
    assert body_two.prompt == tester.continuation_prompt

    finisher = tester.run("")
    assert finisher.stderr == ""
    assert finisher.prompt == tester.prompt
    assert finisher.stdout == "0\n1\n2\n"

    # Verify loop variable mutated across iterations
    final = tester.run("i")
    assert final.stderr == ""
    assert final.prompt == tester.prompt
    assert final.stdout.strip() == "3"


def test_nested_loops_respect_indentation(tester: PyshTester) -> None:
    outer = tester.run("for i in range(2):")
    assert outer.prompt == tester.continuation_prompt

    inner = tester.run("    for j in range(2):")
    assert inner.prompt == tester.continuation_prompt

    body = tester.run("        print(f'{i}{j}')")
    assert body.stderr == ""
    assert body.stdout == ""
    assert body.prompt == tester.continuation_prompt

    finisher = tester.run("")
    assert finisher.stderr == ""
    assert finisher.prompt == tester.prompt
    assert finisher.stdout == "00\n01\n10\n11\n"