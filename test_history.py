"""Unit tests for SQLite debugging history."""

import pytest
import tempfile
from pathlib import Path
from database.history import HistoryDatabase


def test_history_save_and_retrieve():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_history.db"
        db = HistoryDatabase(db_path)

        session_id = db.save_session(
            bug_category="NameError",
            original_code="print(x)",
            repair_status="VERIFIED_SUCCESS",
            is_verified=True,
            iterations_used=1,
            execution_time_ms=120.5,
            summary="Corrected undefined variable x",
            tests_passed=1,
            tests_total=1,
            proposed_diff="--- a\n+++ b"
        )
        assert session_id > 0

        # Retrieve record
        rec = db.get_session_by_id(session_id)
        assert rec is not None
        assert rec["bug_category"] == "NameError"
        assert rec["repair_status"] == "VERIFIED_SUCCESS"
        assert rec["is_verified"] == 1
        assert rec["tests_passed"] == 1

        # Check stats
        stats = db.get_statistics()
        assert stats["total_sessions"] == 1
        assert stats["verified_repairs"] == 1
        assert stats["success_rate_percent"] == 100.0


def test_history_code_hash_determinism():
    h1 = HistoryDatabase.compute_code_hash("def f(): pass")
    h2 = HistoryDatabase.compute_code_hash("def f(): pass")
    h3 = HistoryDatabase.compute_code_hash("def g(): pass")
    assert h1 == h2
    assert h1 != h3

