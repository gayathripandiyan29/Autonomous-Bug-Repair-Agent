"""Unit tests for pytest execution and comparison in sandbox."""

import pytest
from debugger.sandbox import ExecutionSandbox
from debugger.test_runner import TestRunner, TestSuiteResult


def test_test_runner_pass():
    code = "def add(a, b):\n    return a + b\n"
    tests = "import pytest\nfrom solution import add\ndef test_add():\n    assert add(2, 3) == 5\n"

    with ExecutionSandbox(timeout_seconds=8) as sandbox:
        res = TestRunner.run_tests_in_sandbox(sandbox, code, tests)
        assert res.all_passed
        assert res.passed == 1
        assert res.failed == 0


def test_test_runner_fail():
    code = "def add(a, b):\n    return a - b\n"
    tests = "import pytest\nfrom solution import add\ndef test_add():\n    assert add(2, 3) == 5\n"

    with ExecutionSandbox(timeout_seconds=8) as sandbox:
        res = TestRunner.run_tests_in_sandbox(sandbox, code, tests)
        assert not res.all_passed
        assert res.failed == 1
        assert len(res.failure_details) > 0


def test_test_runner_comparison():
    before = TestSuiteResult(total=1, passed=0, failed=1, errors=0, skipped=0, duration_ms=10, raw_output="")
    after = TestSuiteResult(total=1, passed=1, failed=0, errors=0, skipped=0, duration_ms=10, raw_output="")
    comp = TestRunner.compare_results(before, after)
    assert comp.is_fully_resolved
    assert not comp.is_regression
    assert "verified fixed" in comp.summary.lower()

