"""
End-to-End Workflow Tests verifying all 10 Acceptance Criteria.
Verifies NameError, SyntaxError, IndexError, Failing Test Repair,
Diff Display, Regression Checks, Code Preservation, SQLite Storage,
Graceful Offline Fallback, and Honest Test Verification.
"""

import pytest
import tempfile
from pathlib import Path
from agent.workflow import AutonomousBugRepairAgent, WorkflowResult
from agent.llm_client import LLMClient
from database.history import HistoryDatabase
from samples.sample_programs import SAMPLE_PROGRAMS


def get_test_agent() -> AutonomousBugRepairAgent:
    """Creates an agent operating in deterministic local mode for offline test reproducibility."""
    client = LLMClient(provider="local")
    return AutonomousBugRepairAgent(llm_client=client, max_iterations=3, sandbox_timeout=6)


def test_ac1_detect_and_explain_name_error():
    """Criterion 1: Detect and explain a NameError."""
    sample = SAMPLE_PROGRAMS["name_error"]
    agent = get_test_agent()
    result = agent.run(
        code=sample.code,
        traceback_text=sample.traceback,
        test_code=sample.test_code
    )
    assert result.bug_category == "NameError"
    assert "tax_rat" in result.root_cause["root_cause_explanation"] or "tax_rate" in result.root_cause["root_cause_explanation"]
    assert result.root_cause["offending_line_number"] in [2, 3]


def test_ac2_detect_syntax_error():
    """Criterion 2: Detect a syntax error."""
    sample = SAMPLE_PROGRAMS["syntax_error"]
    agent = get_test_agent()
    result = agent.run(
        code=sample.code,
        traceback_text=sample.traceback,
        test_code=sample.test_code
    )
    assert result.bug_category == "SyntaxError"
    assert result.root_cause["offending_line_number"] == 1
    assert "syntax" in result.root_cause["root_cause_explanation"].lower()


def test_ac3_identify_and_repair_index_error():
    """Criterion 3: Identify and repair a simple IndexError."""
    sample = SAMPLE_PROGRAMS["index_error"]
    agent = get_test_agent()
    result = agent.run(
        code=sample.code,
        traceback_text=sample.traceback,
        test_code=sample.test_code
    )
    assert result.bug_category == "IndexError"
    assert result.status == "VERIFIED_SUCCESS"
    assert result.is_verified
    assert "[-1]" in result.repaired_code or "len(items) - 1" in result.repaired_code


def test_ac4_detect_failing_unit_test_and_repair():
    """Criterion 4: Detect a failing unit test and propose a fix."""
    sample = SAMPLE_PROGRAMS["logic_error"]
    agent = get_test_agent()
    result = agent.run(
        code=sample.code,
        traceback_text=sample.traceback,
        test_code=sample.test_code
    )
    assert result.status == "VERIFIED_SUCCESS"
    assert result.is_verified
    assert result.test_comparison is not None
    assert result.test_comparison.after.all_passed


def test_ac5_show_original_and_repaired_code():
    """Criterion 5: Show the original and repaired code."""
    sample = SAMPLE_PROGRAMS["name_error"]
    agent = get_test_agent()
    result = agent.run(code=sample.code, traceback_text=sample.traceback, test_code=sample.test_code)
    assert result.original_code == sample.code
    assert result.repaired_code is not None
    assert result.original_code != result.repaired_code
    assert len(result.applied_diff) > 0


def test_ac6_run_regression_tests():
    """Criterion 6: Run regression tests and display their results."""
    sample = SAMPLE_PROGRAMS["name_error"]
    agent = get_test_agent()
    result = agent.run(code=sample.code, traceback_text=sample.traceback, test_code=sample.test_code)
    assert result.test_comparison is not None
    # Baseline failed or had issues, patched passed all
    assert result.test_comparison.after.all_passed
    assert result.test_comparison.after.passed >= 2


def test_ac7_preserve_original_code():
    """Criterion 7: Preserve the original code (never mutate input code string)."""
    original_code_copy = str(SAMPLE_PROGRAMS["name_error"].code)
    agent = get_test_agent()
    result = agent.run(
        code=original_code_copy,
        traceback_text=SAMPLE_PROGRAMS["name_error"].traceback,
        test_code=SAMPLE_PROGRAMS["name_error"].test_code
    )
    # Original string is preserved intact
    assert original_code_copy == SAMPLE_PROGRAMS["name_error"].code
    assert result.original_code == original_code_copy


def test_ac8_store_debugging_session_in_sqlite():
    """Criterion 8: Store the debugging session in SQLite."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_sessions.db"
        test_db = HistoryDatabase(db_path)

        agent = get_test_agent()
        sample = SAMPLE_PROGRAMS["name_error"]
        result = agent.run(code=sample.code, traceback_text=sample.traceback, test_code=sample.test_code)

        sess_id = test_db.save_session(
            bug_category=result.bug_category,
            original_code=result.original_code,
            repair_status=result.status,
            is_verified=result.is_verified,
            iterations_used=result.iterations_used,
            execution_time_ms=result.execution_time_ms,
            summary=result.root_cause.get("root_cause_explanation", ""),
            tests_passed=result.test_comparison.after.passed if result.test_comparison else 0,
            tests_total=result.test_comparison.after.total if result.test_comparison else 0,
            proposed_diff=result.applied_diff
        )
        assert sess_id > 0
        record = test_db.get_session_by_id(sess_id)
        assert record is not None
        assert record["bug_category"] == "NameError"
        assert record["is_verified"] == 1


def test_ac9_handle_missing_api_configuration():
    """Criterion 9: Handle missing API configuration without crashing."""
    # Explicitly clear API keys
    client = LLMClient(provider="gemini", gemini_api_key="", openai_api_key="")
    assert client.is_local_mode
    agent = AutonomousBugRepairAgent(llm_client=client)

    sample = SAMPLE_PROGRAMS["syntax_error"]
    result = agent.run(code=sample.code, traceback_text=sample.traceback, test_code=sample.test_code)
    # Must not crash, should succeed in local mode
    assert result.status in ["VERIFIED_SUCCESS", "PROPOSED_UNVERIFIED"]
    assert result.bug_category == "SyntaxError"


def test_ac10_distinguish_proposed_from_verified_fixes():
    """Criterion 10: Clearly distinguish proposed fixes from fixes verified by tests."""
    agent = get_test_agent()

    # Case A: Code with tests -> Verified fix
    sample_with_tests = SAMPLE_PROGRAMS["name_error"]
    res_verified = agent.run(
        code=sample_with_tests.code,
        traceback_text=sample_with_tests.traceback,
        test_code=sample_with_tests.test_code,
        auto_generate_tests=False
    )
    assert res_verified.status == "VERIFIED_SUCCESS"
    assert res_verified.is_verified is True

    # Case B: Code WITHOUT tests -> Proposed unverified fix
    code_without_tests = "def is_positive(x)\n    return x > 0"
    res_unverified = agent.run(
        code=code_without_tests,
        traceback_text="",
        test_code="",
        auto_generate_tests=False
    )
    assert res_unverified.status == "PROPOSED_UNVERIFIED"
    assert res_unverified.is_verified is False

