"""Unit tests for patch generation, diff calculation, and validation."""

import pytest
from debugger.repair import PatchValidator, DiffGenerator, LocalDeterministicRepairEngine
from debugger.analyzer import CodeAnalyzer


def test_patch_validator_valid():
    valid_code = "def add(a, b):\n    return a + b"
    is_valid, err = PatchValidator.validate_syntax(valid_code)
    assert is_valid
    assert err is None


def test_patch_validator_invalid():
    invalid_code = "def add(a, b\n    return a + b"
    is_valid, err = PatchValidator.validate_syntax(invalid_code)
    assert not is_valid
    assert "SyntaxError" in err


def test_diff_generator_unified():
    orig = "def foo():\n    return 1\n"
    repaired = "def foo():\n    return 2\n"
    diff = DiffGenerator.generate_unified_diff(orig, repaired, "foo.py")
    assert "-    return 1" in diff
    assert "+    return 2" in diff


def test_local_repair_syntax_error():
    buggy = "def is_even(n)\n    return n % 2 == 0"
    report = CodeAnalyzer.analyze(buggy)
    patch = LocalDeterministicRepairEngine.repair(buggy, report)
    assert patch is not None
    assert patch.is_syntactically_valid
    assert "def is_even(n):" in patch.repaired_code


def test_local_repair_name_error():
    buggy = "def total(subtotal, tax_rate):\n    return subtotal * tax_rat"
    tb = "NameError: name 'tax_rat' is not defined. Did you mean: 'tax_rate'?"
    report = CodeAnalyzer.analyze(buggy, tb)
    patch = LocalDeterministicRepairEngine.repair(buggy, report)
    assert patch is not None
    assert patch.is_syntactically_valid
    assert "tax_rate" in patch.repaired_code


def test_local_repair_index_error():
    buggy = "def last(arr):\n    return arr[len(arr)]"
    tb = "IndexError: list index out of range"
    report = CodeAnalyzer.analyze(buggy, tb)
    patch = LocalDeterministicRepairEngine.repair(buggy, report)
    assert patch is not None
    assert patch.is_syntactically_valid
    assert "[-1]" in patch.repaired_code

