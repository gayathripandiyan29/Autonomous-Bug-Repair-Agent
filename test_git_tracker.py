"""Unit tests for git version tracking and rollback."""

import pytest
import tempfile
from pathlib import Path
from debugger.git_tracker import GitTracker


def test_git_tracker_baseline_and_rollback():
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir)
        tracker = GitTracker(repo_dir)

        orig_code = "x = 1\n"
        test_file = repo_dir / "code.py"
        test_file.write_text(orig_code, encoding="utf-8")

        # Commit baseline
        tracker.commit_baseline("code.py", orig_code)

        # Apply a patch
        patched_code = "x = 2\n"
        test_file.write_text(patched_code, encoding="utf-8")
        tracker.commit_patch("code.py", patched_code, iteration=1)

        diff = tracker.get_diff_from_baseline("code.py")
        assert "-x = 1" in diff or "-1" in diff
        assert "+x = 2" in diff or "+2" in diff

        # Rollback to baseline
        rolled_back = tracker.rollback_to_baseline("code.py")
        assert rolled_back.strip() == "x = 1"
        assert test_file.read_text(encoding="utf-8").strip() == "x = 1"

