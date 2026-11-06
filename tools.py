"""
Agent Tool Declarations and Execution Interfaces.
Provides structured debugging tools for AST inspection, traceback analysis,
sandbox test execution, patch validation, and diff generation.
"""

from typing import Dict, Any, Optional
from debugger.analyzer import CodeAnalyzer, TracebackAnalyzer
from debugger.sandbox import ExecutionSandbox
from debugger.test_runner import TestRunner, TestSuiteResult
from debugger.repair import PatchValidator, DiffGenerator


class AgentTools:
    """Registry of debugging tools callable by the agent or LLM."""

    @staticmethod
    def tool_inspect_code_ast(code: str) -> Dict[str, Any]:
        """Inspects Python code AST for syntax validity, undefined names, and structure."""
        report = CodeAnalyzer.analyze(code)
        return {
            "status": "success",
            "is_valid_syntax": report.is_valid_syntax,
            "syntax_error": report.syntax_error.to_dict() if report.syntax_error else None,
            "confirmed_bugs": [b.to_dict() for b in report.confirmed_bugs],
            "suspected_bugs": [b.to_dict() for b in report.suspected_bugs],
            "symbols_defined": report.symbols_defined,
            "imports": report.imports,
            "total_lines": report.total_lines
        }

    @staticmethod
    def tool_parse_traceback(traceback_text: str) -> Dict[str, Any]:
        """Parses a raw traceback to locate the failing line and exception message."""
        info = TracebackAnalyzer.parse(traceback_text)
        if not info:
            return {"status": "empty", "message": "No valid traceback content provided."}
        return {
            "status": "success",
            "exception_type": info.exception_type,
            "exception_message": info.exception_message,
            "primary_line": info.primary_frame.line_number if info.primary_frame else None,
            "primary_function": info.primary_frame.function_name if info.primary_frame else None,
            "primary_code": info.primary_frame.code_line if info.primary_frame else None,
            "frame_count": len(info.frames)
        }

    @staticmethod
    def tool_run_sandbox_tests(code: str, test_code: str, timeout: int = 8) -> Dict[str, Any]:
        """Executes pytest in an isolated sandbox against the code."""
        with ExecutionSandbox(timeout_seconds=timeout) as sandbox:
            res: TestSuiteResult = TestRunner.run_tests_in_sandbox(
                sandbox=sandbox,
                code_content=code,
                test_content=test_code
            )
            return {
                "status": "success",
                "all_passed": res.all_passed,
                "total": res.total,
                "passed": res.passed,
                "failed": res.failed,
                "errors": res.errors,
                "skipped": res.skipped,
                "timed_out": res.timed_out,
                "duration_ms": res.duration_ms,
                "failure_details": res.failure_details[:3],  # Truncate to top 3 failures
                "exit_code": res.exit_code
            }

    @staticmethod
    def tool_validate_patch_syntax(candidate_code: str) -> Dict[str, Any]:
        """Validates that candidate code is syntactically valid Python."""
        is_valid, err_msg = PatchValidator.validate_syntax(candidate_code)
        return {
            "status": "success",
            "is_valid": is_valid,
            "error_message": err_msg
        }

    @staticmethod
    def tool_compute_diff(original_code: str, candidate_code: str) -> Dict[str, Any]:
        """Generates a unified diff comparing original and candidate code."""
        diff = DiffGenerator.generate_unified_diff(original_code, candidate_code)
        return {
            "status": "success",
            "unified_diff": diff,
            "has_changes": bool(diff.strip())
        }

    @staticmethod
    def tool_execute_script_sandbox(code: str, timeout: int = 5) -> Dict[str, Any]:
        """Runs the script directly in the sandbox to observe runtime behavior and crashes."""
        with ExecutionSandbox(timeout_seconds=timeout) as sandbox:
            sandbox.write_file("main.py", code)
            exec_res = sandbox.run_python_script("main.py")
            return {
                "status": "success",
                "exit_code": exec_res.exit_code,
                "is_success": exec_res.is_success,
                "stdout": exec_res.stdout,
                "stderr": exec_res.stderr,
                "timed_out": exec_res.timed_out,
                "duration_ms": exec_res.execution_time_ms
            }

    @classmethod
    def get_tool_definitions(cls) -> list:
        """Returns JSON schema definitions for tool-calling LLMs."""
        return [
            {
                "name": "inspect_code_ast",
                "description": "Inspects Python code AST for syntax validity, undefined names, and structure.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python source code"}
                    },
                    "required": ["code"]
                }
            },
            {
                "name": "parse_traceback",
                "description": "Parses raw traceback to locate the failing line and exception message.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "traceback_text": {"type": "string", "description": "Raw traceback text"}
                    },
                    "required": ["traceback_text"]
                }
            },
            {
                "name": "run_sandbox_tests",
                "description": "Runs pytest in an isolated sandbox against the code and test suite.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python source code"},
                        "test_code": {"type": "string", "description": "Pytest test code"}
                    },
                    "required": ["code", "test_code"]
                }
            },
            {
                "name": "validate_patch_syntax",
                "description": "Validates that a proposed code patch has valid Python syntax.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_code": {"type": "string", "description": "Proposed repaired Python source code"}
                    },
                    "required": ["candidate_code"]
                }
            }
        ]

