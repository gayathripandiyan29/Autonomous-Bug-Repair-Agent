"""
Git-based Version Tracker and Rollback Support.
Tracks code revisions within a sandbox, creates diffs, and provides safe rollback capabilities.
Includes a difflib in-memory fallback if the system git CLI is unavailable.
"""

import subprocess
import difflib
from pathlib import Path
from typing import Optional, List, Dict, Any


class GitTracker:
    """
    Manages git version tracking for code revisions in a sandbox directory.
    Provides snapshotting, diff generation, and clean rollback.
    """

    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir
        self.is_git_available = self._check_git()
        self.revision_history: List[Dict[str, Any]] = []
        self._init_repo()

    def _check_git(self) -> bool:
        try:
            import os
            env = os.environ.copy()
            env["GIT_TERMINAL_PROMPT"] = "0"
            res = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=2,
                env=env,
                check=False
            )
            return res.returncode == 0
        except Exception:
            return False

    def _run_git(self, args: List[str]) -> Optional[subprocess.CompletedProcess]:
        if not self.is_git_available:
            return None
        try:
            import os
            env = os.environ.copy()
            env["GIT_TERMINAL_PROMPT"] = "0"
            env["GIT_OPTIONAL_LOCKS"] = "0"
            env["GIT_CONFIG_NOSYSTEM"] = "1"
            res = subprocess.run(
                ["git"] + args,
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=2,
                env=env,
                check=False
            )
            if res.returncode != 0:
                pass
            return res
        except Exception:
            # If git times out or fails, disable git CLI and switch to in-memory fallback
            self.is_git_available = False
            return None

    def _init_repo(self):
        if self.is_git_available:
            try:
                res = self._run_git(["init"])
                if res and res.returncode == 0:
                    self._run_git(["config", "user.name", "BugRepairAgent"])
                    self._run_git(["config", "user.email", "agent@bugrepair.local"])
                    self._run_git(["config", "commit.gpgsign", "false"])
                else:
                    self.is_git_available = False
            except Exception:
                self.is_git_available = False

    def commit_baseline(self, filename: str, content: str) -> bool:
        """Record the initial baseline (buggy) state of the file."""
        self.revision_history.append({
            "label": "baseline",
            "filename": filename,
            "content": content,
            "message": "Initial code baseline"
        })

        if self.is_git_available:
            self._run_git(["add", filename])
            res = self._run_git(["commit", "-m", "baseline: initial buggy code"])
            self._run_git(["tag", "-f", "baseline"])
            return bool(res and res.returncode == 0)
        return True

    def commit_patch(self, filename: str, content: str, iteration: int, message: str = "") -> bool:
        """Record a newly applied patch revision."""
        msg = message or f"patch: iteration {iteration}"
        self.revision_history.append({
            "label": f"patch_iter_{iteration}",
            "filename": filename,
            "content": content,
            "message": msg
        })

        if self.is_git_available:
            self._run_git(["add", filename])
            res = self._run_git(["commit", "-m", msg])
            return bool(res and res.returncode == 0)
        return True

    def rollback_to_baseline(self, filename: str) -> str:
        """Roll back the file to its initial baseline state and return the content."""
        if self.is_git_available:
            # Checkout from baseline tag
            res = self._run_git(["checkout", "baseline", "--", filename])
            target_file = self.repo_dir / filename
            if target_file.exists():
                return target_file.read_text(encoding="utf-8")

        # Fallback to in-memory baseline
        for rev in self.revision_history:
            if rev["label"] == "baseline" and rev["filename"] == filename:
                target_file = self.repo_dir / filename
                target_file.write_text(rev["content"], encoding="utf-8")
                return rev["content"]

        return ""

    def get_diff_from_baseline(self, filename: str) -> str:
        """Generate unified diff between baseline and current state."""
        if self.is_git_available:
            res = self._run_git(["diff", "baseline", "--", filename])
            if res and res.stdout.strip():
                return res.stdout

        # Difflib fallback
        baseline_content = ""
        for rev in self.revision_history:
            if rev["label"] == "baseline" and rev["filename"] == filename:
                baseline_content = rev["content"]
                break

        current_file = self.repo_dir / filename
        current_content = current_file.read_text(encoding="utf-8") if current_file.exists() else ""

        return self.compute_text_diff(baseline_content, current_content, filename)

    @staticmethod
    def compute_text_diff(original: str, modified: str, filename: str = "solution.py") -> str:
        """Generate unified diff string using Python difflib."""
        orig_lines = original.splitlines(keepends=True)
        mod_lines = modified.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile=f"a/{filename} (original)",
            tofile=f"b/{filename} (repaired)",
            n=3
        )
        return "".join(diff)
