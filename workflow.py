"""
Autonomous Bug Detection & Repair Agent Workflow Engine.
Implements an explicit state-machine driven workflow with tool calls,
sandbox isolation, git version tracking, automated testing, and retry loops.
"""

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from debugger.analyzer import CodeAnalyzer, AnalysisReport
from debugger.sandbox import ExecutionSandbox
from debugger.git_tracker import GitTracker
from debugger.test_runner import TestRunner, TestSuiteResult, TestComparison
from debugger.repair import ProposedPatch, PatchValidator, DiffGenerator
from agent.tools import AgentTools
from agent.llm_client import LLMClient
from config import Config


class WorkflowState(str, Enum):
    IDLE = "IDLE"
    INITIALIZING = "INITIALIZING"
    TOOL_INSPECTION = "TOOL_INSPECTION"
    ROOT_CAUSE_ANALYSIS = "ROOT_CAUSE_ANALYSIS"
    REPAIR_PLANNING = "REPAIR_PLANNING"
    PATCH_GENERATION = "PATCH_GENERATION"
    SANDBOX_TESTING = "SANDBOX_TESTING"
    INSPECT_TEST_RESULTS = "INSPECT_TEST_RESULTS"
    RETRYING = "RETRYING"
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    PROPOSED_UNVERIFIED = "PROPOSED_UNVERIFIED"
    UNRESOLVED_LIMIT_REACHED = "UNRESOLVED_LIMIT_REACHED"
    FAILED_ERROR = "FAILED_ERROR"


@dataclass
class WorkflowStep:
    """Log record of a single step or tool invocation within the agent workflow."""
    step_number: int
    state: str
    tool_called: Optional[str]
    tool_input: Optional[Dict[str, Any]]
    tool_output: Optional[Dict[str, Any]]
    description: str
    elapsed_ms: float


@dataclass
class WorkflowResult:
    """Final outcome and complete trace of the autonomous repair workflow."""
    status: str                         # 'VERIFIED_SUCCESS', 'PROPOSED_UNVERIFIED', 'UNRESOLVED', 'ERROR'
    original_code: str
    repaired_code: Optional[str]
    root_cause: Dict[str, Any]
    repair_patch: Optional[ProposedPatch]
    test_comparison: Optional[TestComparison]
    workflow_steps: List[WorkflowStep] = field(default_factory=list)
    iterations_used: int = 0
    max_iterations: int = 3
    execution_time_ms: float = 0.0
    bug_category: str = "Unknown"
    is_verified: bool = False
    error_message: Optional[str] = None
    applied_diff: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "bug_category": self.bug_category,
            "is_verified": self.is_verified,
            "iterations_used": self.iterations_used,
            "execution_time_ms": self.execution_time_ms,
            "root_cause": self.root_cause,
            "has_repaired_code": bool(self.repaired_code),
            "test_comparison": self.test_comparison.to_dict() if self.test_comparison else None,
            "error_message": self.error_message,
        }


class AutonomousBugRepairAgent:
    """
    Autonomous Bug Detection & Repair Agent.
    Coordinates tool invocation, AST & traceback analysis, patch proposal,
    isolated sandbox testing, git version snapshotting, and iterative repair.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        max_iterations: int = Config.MAX_REPAIR_ITERATIONS,
        sandbox_timeout: int = Config.SANDBOX_TIMEOUT_SECONDS,
        step_callback: Optional[Callable[[WorkflowStep], None]] = None
    ):
        self.llm_client = llm_client or LLMClient()
        self.max_iterations = max_iterations
        self.sandbox_timeout = sandbox_timeout
        self.step_callback = step_callback
        self.current_state = WorkflowState.IDLE
        self.workflow_steps: List[WorkflowStep] = []
        self._start_time: float = 0.0

    def _log_step(
        self,
        state: WorkflowState,
        description: str,
        tool_called: Optional[str] = None,
        tool_input: Optional[Dict[str, Any]] = None,
        tool_output: Optional[Dict[str, Any]] = None
    ):
        """Append and notify step progress."""
        self.current_state = state
        step_num = len(self.workflow_steps) + 1
        elapsed = (time.perf_counter() - self._start_time) * 1000

        step = WorkflowStep(
            step_number=step_num,
            state=state.value,
            tool_called=tool_called,
            tool_input=tool_input,
            tool_output=tool_output,
            description=description,
            elapsed_ms=round(elapsed, 2)
        )
        self.workflow_steps.append(step)
        if self.step_callback:
            try:
                self.step_callback(step)
            except Exception:
                pass

    def run(
        self,
        code: str,
        traceback_text: str = "",
        test_code: str = "",
        auto_generate_tests: bool = True
    ) -> WorkflowResult:
        """
        Executes the autonomous bug repair lifecycle.
        """
        self._start_time = time.perf_counter()
        self.workflow_steps = []
        self._log_step(WorkflowState.INITIALIZING, "Received user code and error inputs. Validating input.")

        # 1. Input Validation
        if not code or not code.strip():
            self._log_step(WorkflowState.FAILED_ERROR, "Input code is empty. Aborting workflow.")
            return WorkflowResult(
                status="ERROR",
                original_code=code,
                repaired_code=None,
                root_cause={},
                repair_patch=None,
                test_comparison=None,
                workflow_steps=self.workflow_steps,
                error_message="Provided code is empty."
            )

        # 2. Tool-based Code Inspection & Traceback Parsing
        self._log_step(
            WorkflowState.TOOL_INSPECTION,
            "Invoking inspection tools: AST parser and Traceback Analyzer.",
            tool_called="inspect_code_ast",
            tool_input={"code_length": len(code)}
        )
        ast_result = AgentTools.tool_inspect_code_ast(code)
        self._log_step(
            WorkflowState.TOOL_INSPECTION,
            f"AST inspection complete. Valid syntax: {ast_result['is_valid_syntax']}.",
            tool_called="inspect_code_ast",
            tool_output=ast_result
        )

        tb_result = None
        if traceback_text and traceback_text.strip():
            self._log_step(
                WorkflowState.TOOL_INSPECTION,
                "Parsing provided traceback details.",
                tool_called="parse_traceback",
                tool_input={"traceback_preview": traceback_text[:120]}
            )
            tb_result = AgentTools.tool_parse_traceback(traceback_text)
            self._log_step(
                WorkflowState.TOOL_INSPECTION,
                f"Traceback parsed: {tb_result.get('exception_type', 'None')} on line {tb_result.get('primary_line', 'unknown')}.",
                tool_called="parse_traceback",
                tool_output=tb_result
            )

        # Combine into unified AnalysisReport
        report = CodeAnalyzer.analyze(code, traceback_text)

        # Determine if test suite is available or needs auto-synthesis
        effective_tests = test_code.strip()
        if not effective_tests and auto_generate_tests and report.is_valid_syntax:
            effective_tests = TestRunner.generate_reproduction_test(code, traceback_text)
            self._log_step(
                WorkflowState.TOOL_INSPECTION,
                "No explicit tests supplied. Auto-generated verification test suite.",
                tool_input={"tests": effective_tests}
            )

        # 3. Root Cause Analysis
        self._log_step(
            WorkflowState.ROOT_CAUSE_ANALYSIS,
            f"Performing root cause analysis using {self.llm_client.get_mode_description()}."
        )
        root_cause = self.llm_client.analyze_root_cause(code, traceback_text, report)
        bug_category = root_cause.get("bug_category", "Unknown")
        self._log_step(
            WorkflowState.ROOT_CAUSE_ANALYSIS,
            f"Root cause identified: [{bug_category}] {root_cause.get('root_cause_explanation', '')[:100]}...",
            tool_output=root_cause
        )

        # 4. Baseline Testing (Run tests against buggy code to confirm failure)
        initial_test_result: Optional[TestSuiteResult] = None
        if effective_tests and report.is_valid_syntax:
            self._log_step(
                WorkflowState.SANDBOX_TESTING,
                "Running initial test suite against baseline (unmodified) code in isolated sandbox.",
                tool_called="run_sandbox_tests",
                tool_input={"code_filename": "solution.py", "test_filename": "test_solution.py"}
            )
            initial_test_dict = AgentTools.tool_run_sandbox_tests(code, effective_tests, timeout=self.sandbox_timeout)
            initial_test_result = TestSuiteResult(
                total=initial_test_dict["total"],
                passed=initial_test_dict["passed"],
                failed=initial_test_dict["failed"],
                errors=initial_test_dict["errors"],
                skipped=initial_test_dict["skipped"],
                duration_ms=initial_test_dict["duration_ms"],
                raw_output="",
                failure_details=initial_test_dict["failure_details"],
                exit_code=initial_test_dict["exit_code"],
                timed_out=initial_test_dict["timed_out"]
            )
            self._log_step(
                WorkflowState.INSPECT_TEST_RESULTS,
                f"Baseline test run complete: {initial_test_result.passed} passed, {initial_test_result.failed} failed, {initial_test_result.errors} errors.",
                tool_output=initial_test_dict
            )

        # 5. Iterative Repair Loop
        iteration = 1
        current_code = code
        last_patch: Optional[ProposedPatch] = None
        last_comparison: Optional[TestComparison] = None
        test_failure_context = ""
        if initial_test_result and initial_test_result.failure_details:
            test_failure_context = "\n".join(initial_test_result.failure_details)

        # Create isolated working sandbox with git tracking
        with ExecutionSandbox(timeout_seconds=self.sandbox_timeout) as sandbox:
            git = GitTracker(sandbox.create())
            git.commit_baseline("solution.py", code)

            while iteration <= self.max_iterations:
                self._log_step(
                    WorkflowState.PATCH_GENERATION,
                    f"Iteration {iteration}/{self.max_iterations}: Generating candidate repair patch."
                )

                patch = self.llm_client.generate_repair_patch(
                    code=code,
                    traceback_text=traceback_text,
                    root_cause=root_cause,
                    report=report,
                    test_failure_msg=test_failure_context,
                    iteration=iteration
                )

                if not patch or not patch.repaired_code:
                    self._log_step(
                        WorkflowState.PATCH_GENERATION,
                        f"Iteration {iteration}: No valid patch could be generated by engine."
                    )
                    break

                last_patch = patch

                # Validate Patch Syntax
                val_res = AgentTools.tool_validate_patch_syntax(patch.repaired_code)
                self._log_step(
                    WorkflowState.PATCH_GENERATION,
                    f"Patch syntax check: {'PASSED' if val_res['is_valid'] else 'FAILED'}.",
                    tool_called="validate_patch_syntax",
                    tool_output=val_res
                )

                if not val_res["is_valid"]:
                    self._log_step(
                        WorkflowState.RETRYING,
                        f"Patch contains syntax errors: {val_res['error_message']}. Attempting retry."
                    )
                    test_failure_context = f"Generated patch had SyntaxError: {val_res['error_message']}"
                    iteration += 1
                    continue

                # Record patch revision in Git
                git.commit_patch("solution.py", patch.repaired_code, iteration)

                # If no test suite exists, we can only verify syntax
                if not effective_tests:
                    self._log_step(
                        WorkflowState.PROPOSED_UNVERIFIED,
                        "Patch is syntactically valid. No test suite available for dynamic assertion verification."
                    )
                    elapsed_total = (time.perf_counter() - self._start_time) * 1000
                    return WorkflowResult(
                        status="PROPOSED_UNVERIFIED",
                        original_code=code,
                        repaired_code=patch.repaired_code,
                        root_cause=root_cause,
                        repair_patch=patch,
                        test_comparison=None,
                        workflow_steps=self.workflow_steps,
                        iterations_used=iteration,
                        max_iterations=self.max_iterations,
                        execution_time_ms=round(elapsed_total, 2),
                        bug_category=bug_category,
                        is_verified=False,
                        applied_diff=patch.unified_diff
                    )

                # Run Tests in Sandbox against Patched Code
                self._log_step(
                    WorkflowState.SANDBOX_TESTING,
                    f"Iteration {iteration}: Executing test suite against patched code in sandbox.",
                    tool_called="run_sandbox_tests"
                )
                patched_test_dict = AgentTools.tool_run_sandbox_tests(
                    code=patch.repaired_code,
                    test_code=effective_tests,
                    timeout=self.sandbox_timeout
                )
                patched_test_result = TestSuiteResult(
                    total=patched_test_dict["total"],
                    passed=patched_test_dict["passed"],
                    failed=patched_test_dict["failed"],
                    errors=patched_test_dict["errors"],
                    skipped=patched_test_dict["skipped"],
                    duration_ms=patched_test_dict["duration_ms"],
                    raw_output="",
                    failure_details=patched_test_dict["failure_details"],
                    exit_code=patched_test_dict["exit_code"],
                    timed_out=patched_test_dict["timed_out"]
                )

                # Compare before and after test results
                comparison = TestRunner.compare_results(
                    before=initial_test_result or TestSuiteResult(
                        total=1, passed=0, failed=1, errors=0, skipped=0, duration_ms=0, raw_output=""
                    ),
                    after=patched_test_result
                )
                last_comparison = comparison

                self._log_step(
                    WorkflowState.INSPECT_TEST_RESULTS,
                    f"Test inspection: {comparison.summary}",
                    tool_output=comparison.to_dict()
                )

                # Check if all tests pass
                if patched_test_result.all_passed:
                    self._log_step(
                        WorkflowState.VERIFIED_SUCCESS,
                        f"All {patched_test_result.passed} test(s) passed successfully! Bug verified resolved."
                    )
                    elapsed_total = (time.perf_counter() - self._start_time) * 1000
                    return WorkflowResult(
                        status="VERIFIED_SUCCESS",
                        original_code=code,
                        repaired_code=patch.repaired_code,
                        root_cause=root_cause,
                        repair_patch=patch,
                        test_comparison=comparison,
                        workflow_steps=self.workflow_steps,
                        iterations_used=iteration,
                        max_iterations=self.max_iterations,
                        execution_time_ms=round(elapsed_total, 2),
                        bug_category=bug_category,
                        is_verified=True,
                        applied_diff=patch.unified_diff
                    )

                # If tests failed, roll back git to baseline and prepare for next iteration
                self._log_step(
                    WorkflowState.RETRYING,
                    f"Iteration {iteration} tests failed ({patched_test_result.failed} failed). Rolling back to baseline."
                )
                git.rollback_to_baseline("solution.py")
                test_failure_context = "\n".join(patched_test_result.failure_details)
                iteration += 1

        # Max iterations reached without clean pass
        self._log_step(
            WorkflowState.UNRESOLVED_LIMIT_REACHED,
            f"Exceeded max repair iterations ({self.max_iterations}). Reporting unresolved state honestly."
        )
        elapsed_total = (time.perf_counter() - self._start_time) * 1000
        return WorkflowResult(
            status="UNRESOLVED",
            original_code=code,
            repaired_code=last_patch.repaired_code if last_patch else None,
            root_cause=root_cause,
            repair_patch=last_patch,
            test_comparison=last_comparison,
            workflow_steps=self.workflow_steps,
            iterations_used=self.max_iterations,
            max_iterations=self.max_iterations,
            execution_time_ms=round(elapsed_total, 2),
            bug_category=bug_category,
            is_verified=False,
            error_message="Could not verify clean test pass within configured retry limit."
        )

