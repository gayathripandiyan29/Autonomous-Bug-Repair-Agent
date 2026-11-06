"""
Pytest Test Runner and Result Analyzer for Isolated Sandbox.
Executes test suites against code versions, parses pytest outputs,
and detects regressions or successful resolutions.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from debugger.sandbox import ExecutionSandbox, SandboxExecutionResult


@dataclass
class TestCaseResult:
    """Detailed result of an individual test case."""
    __test__ = False
    node_id: str
    status: str       # 'PASSED', 'FAILED', 'ERROR', 'SKIPPED'
    failure_message: Optional[str] = None


@dataclass
class TestSuiteResult:
    """Summary of a pytest run on a test suite."""
    __test__ = False
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_ms: float
    raw_output: str
    test_cases: List[TestCaseResult] = field(default_factory=list)
    failure_details: List[str] = field(default_factory=list)
    exit_code: int = 0
    timed_out: bool = False

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.failed == 0 and self.errors == 0 and not self.timed_out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "duration_ms": self.duration_ms,
            "all_passed": self.all_passed,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "failure_count": len(self.failure_details),
            "test_cases": [{"name": t.node_id, "status": t.status} for t in self.test_cases]
        }


@dataclass
class TestComparison:
    """Comparison between test execution before and after a patch."""
    __test__ = False
    before: TestSuiteResult
    after: TestSuiteResult
    is_fully_resolved: bool
    is_improved: bool
    is_regression: bool
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "is_fully_resolved": self.is_fully_resolved,
            "is_improved": self.is_improved,
            "is_regression": self.is_regression,
            "summary": self.summary,
        }


class TestRunner:
    """Executes pytest inside the sandbox and parses results."""

    SUMMARY_REGEX = re.compile(
        r'(=+)\s*(?:(?P<passed>\d+)\s+passed)?'
        r'(?:[,\s]+(?P<failed>\d+)\s+failed)?'
        r'(?:[,\s]+(?P<errors>\d+)\s+error(?:s)?)?'
        r'(?:[,\s]+(?P<skipped>\d+)\s+skipped)?'
        r'.*?in\s+(?P<duration>[\d.]+)s\s*(=+)',
        re.IGNORECASE
    )

    CASE_LINE_REGEX = re.compile(r'^(.*?::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED)', re.MULTILINE)

    @classmethod
    def parse_pytest_output(cls, execution_result: SandboxExecutionResult) -> TestSuiteResult:
        """Parse raw pytest stdout/stderr into a structured TestSuiteResult."""
        stdout = execution_result.stdout
        stderr = execution_result.stderr
        combined = (stdout + "\n" + stderr).strip()

        passed = 0
        failed = 0
        errors = 0
        skipped = 0

        # Match overall summary line: e.g. "== 2 passed, 1 failed in 0.12s =="
        match = cls.SUMMARY_REGEX.search(combined)
        if match:
            passed = int(match.group("passed") or 0)
            failed = int(match.group("failed") or 0)
            errors = int(match.group("errors") or 0)
            skipped = int(match.group("skipped") or 0)
        else:
            # Fallback simple count if summary regex didn't catch formatted banner
            passed_match = re.search(r'(\d+)\s+passed', combined)
            failed_match = re.search(r'(\d+)\s+failed', combined)
            errors_match = re.search(r'(\d+)\s+error', combined)
            skipped_match = re.search(r'(\d+)\s+skipped', combined)

            if passed_match:
                passed = int(passed_match.group(1))
            if failed_match:
                failed = int(failed_match.group(1))
            if errors_match:
                errors = int(errors_match.group(1))
            if skipped_match:
                skipped = int(skipped_match.group(1))

        # Check individual test line items
        test_cases: List[TestCaseResult] = []
        for case_match in cls.CASE_LINE_REGEX.finditer(combined):
            test_cases.append(TestCaseResult(
                node_id=case_match.group(1),
                status=case_match.group(2).upper()
            ))

        # If pytest failed to run completely (e.g. collection error or syntax error in module)
        if passed == 0 and failed == 0 and errors == 0:
            if "ERRORS" in combined or "ERROR:" in combined or "SyntaxError" in combined:
                errors = 1
            elif execution_result.exit_code != 0:
                failed = 1

        total = passed + failed + errors + skipped

        # Extract failure details / assertion errors
        failure_details: List[str] = []
        in_failures = False
        current_failure = []
        for line in combined.splitlines():
            # Check for failure block headers e.g. "=== FAILURES ==="
            if "FAILURES" in line or "ERRORS" in line:
                in_failures = True
                continue
            if line.startswith("FAILED ") or line.startswith("ERROR "):
                failure_details.append(line.strip())
            if in_failures:
                if line.startswith("====") and ("passed" in line or "failed" in line or "summary" in line):
                    if current_failure:
                        failure_details.append("\n".join(current_failure).strip())
                        current_failure = []
                    in_failures = False
                    continue
                current_failure.append(line)
        if current_failure:
            failure_details.append("\n".join(current_failure).strip())

        # If failures detected but list is still empty, include raw output snippet
        if (failed > 0 or errors > 0) and not failure_details:
            failure_details.append(combined[:500])

        return TestSuiteResult(
            total=total,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration_ms=execution_result.execution_time_ms,
            raw_output=combined,
            test_cases=test_cases,
            failure_details=failure_details,
            exit_code=execution_result.exit_code,
            timed_out=execution_result.timed_out
        )

    @classmethod
    def run_tests_in_sandbox(
        cls,
        sandbox: ExecutionSandbox,
        code_content: str,
        test_content: str,
        code_filename: str = "solution.py",
        test_filename: str = "test_solution.py"
    ) -> TestSuiteResult:
        """Write code and test files into the sandbox and execute pytest."""
        sandbox.write_file(code_filename, code_content)
        sandbox.write_file(test_filename, test_content)

        exec_res = sandbox.run_pytest(test_filename)
        return cls.parse_pytest_output(exec_res)

    @classmethod
    def compare_results(cls, before: TestSuiteResult, after: TestSuiteResult) -> TestComparison:
        """Compare two test suite runs to determine if the bug is resolved or regressed."""
        is_fully_resolved = (after.all_passed and (not before.all_passed or before.failed > 0 or before.errors > 0))
        is_improved = (after.passed > before.passed) or (after.failed < before.failed)
        is_regression = (after.passed < before.passed) or (after.failed > before.failed)

        if is_fully_resolved:
            summary = f"All {after.passed} test(s) passed successfully! Bug is verified fixed."
        elif is_regression:
            summary = f"Regression detected: Passing tests dropped from {before.passed} to {after.passed}."
        elif is_improved:
            summary = f"Partial improvement: {after.passed}/{after.total} tests passing (previously {before.passed}/{before.total})."
        elif after.all_passed and before.all_passed:
            summary = f"Tests continue to pass ({after.passed}/{after.total})."
        else:
            summary = f"Fix did not resolve the test failures ({after.failed} failed, {after.errors} errors)."

        return TestComparison(
            before=before,
            after=after,
            is_fully_resolved=is_fully_resolved,
            is_improved=is_improved,
            is_regression=is_regression,
            summary=summary
        )

    @staticmethod
    def generate_reproduction_test(code: str, error_desc: str = "") -> str:
        """
        Auto-generates a pytest reproduction script when user provides only code or traceback.
        Checks module import and calls any defined top-level test or demo functions.
        """
        import ast
        try:
            tree = ast.parse(code)
            functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
        except Exception:
            functions = []

        test_lines = [
            "import pytest",
            "import solution",
            "",
            "def test_module_syntax_and_import():",
            "    '''Verify module imports cleanly and executes without crashing.'''",
            "    assert solution is not None",
        ]

        # If functions exist, add a basic call check if feasible
        for fn in functions:
            if fn.startswith("test_") or fn == "main":
                test_lines.extend([
                    "",
                    f"def test_{fn}_executes():",
                    f"    solution.{fn}()",
                ])

        return "\n".join(test_lines) + "\n"
