"""Unit tests for AST and Traceback analyzer."""

import pytest
from debugger.analyzer import CodeAnalyzer, TracebackAnalyzer, CodeContextExtractor


def test_syntax_error_detection():
    buggy_code = "def bad_func(x)\n    return x * 2"
    report = CodeAnalyzer.analyze(buggy_code)
    assert not report.is_valid_syntax
    assert report.syntax_error is not None
    assert report.syntax_error.category == "SyntaxError"
    assert report.syntax_error.location.line_number == 1
    assert "Syntax Error on line 1" in report.syntax_error.message


def test_valid_syntax_code():
    valid_code = "def good_func(x):\n    return x * 2"
    report = CodeAnalyzer.analyze(valid_code)
    assert report.is_valid_syntax
    assert report.syntax_error is None


def test_name_error_detection():
    code_with_typo = "def calc(subtotal, tax_rate):\n    return subtotal * tax_rat"
    report = CodeAnalyzer.analyze(code_with_typo)
    assert report.is_valid_syntax
    # Should detect unused / undefined 'tax_rat'
    suspected_names = [b for b in report.suspected_bugs if b.category == "NameError"]
    assert len(suspected_names) > 0
    assert "tax_rat" in suspected_names[0].message


def test_traceback_parsing_name_error():
    tb_text = """Traceback (most recent call last):
  File "solution.py", line 2, in calc
    return subtotal * tax_rat
NameError: name 'tax_rat' is not defined. Did you mean: 'tax_rate'?
"""
    tb_info = TracebackAnalyzer.parse(tb_text)
    assert tb_info is not None
    assert tb_info.exception_type == "NameError"
    assert "tax_rat" in tb_info.exception_message
    assert tb_info.primary_frame is not None
    assert tb_info.primary_frame.line_number == 2


def test_traceback_parsing_index_error():
    tb_text = """Traceback (most recent call last):
  File "solution.py", line 5, in get_item
    return items[10]
IndexError: list index out of range
"""
    tb_info = TracebackAnalyzer.parse(tb_text)
    assert tb_info is not None
    assert tb_info.exception_type == "IndexError"
    assert tb_info.primary_frame.line_number == 5


def test_context_extractor():
    code = "line1\nline2\nline3\nline4\nline5"
    ctx = CodeContextExtractor.get_context(code, 3, context_lines=1)
    assert ctx.line_number == 3
    assert ctx.line_content == "line3"
    assert ctx.context_before == ["line2"]
    assert ctx.context_after == ["line4"]

