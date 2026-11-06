"""
LLM Client and Fallback Dispatcher for Autonomous Bug Repair Agent.
Provides REST-based integration with Gemini and OpenAI APIs, with robust JSON extraction
and automatic fallback to the local deterministic rule engine.
"""

import json
import re
import requests
from typing import Dict, Any, Optional, Tuple
from config import Config
from debugger.analyzer import AnalysisReport
from debugger.repair import LocalDeterministicRepairEngine, ProposedPatch, PatchValidator, DiffGenerator
from agent.prompts import SYSTEM_PROMPT, ROOT_CAUSE_PROMPT, REPAIR_PATCH_PROMPT


def clean_json_text(text: str) -> str:
    """Strip markdown code fence wrappers from LLM responses."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


class LLMClient:
    """Manages LLM API calls with graceful fallback to the local deterministic engine."""

    def __init__(
        self,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        openai_base_url: Optional[str] = None
    ):
        self.gemini_key = gemini_api_key or Config.GEMINI_API_KEY or ""
        self.openai_key = openai_api_key or Config.OPENAI_API_KEY or ""
        self.openai_base_url = openai_base_url or Config.OPENAI_BASE_URL
        self.model_name = model_name or Config.DEFAULT_MODEL_NAME

        # Determine active provider
        if provider:
            self.provider = provider
        elif self.gemini_key:
            self.provider = "gemini"
        elif self.openai_key:
            self.provider = "openai"
        else:
            self.provider = "local"

    @property
    def is_local_mode(self) -> bool:
        return self.provider == "local" or (self.provider == "gemini" and not self.gemini_key) or (self.provider == "openai" and not self.openai_key)

    def get_mode_description(self) -> str:
        if self.is_local_mode:
            return "Local Deterministic Engine (No API key required - Offline & Fast)"
        if self.provider == "gemini":
            return f"Gemini Cloud AI ({self.model_name})"
        if self.provider == "openai":
            return f"OpenAI Compatible AI ({self.model_name})"
        return "Local Deterministic Engine"

    def _call_gemini(self, system_instruction: str, user_prompt: str) -> Tuple[bool, str]:
        """Send prompt to Google Gemini via standard REST API using requests."""
        if not self.gemini_key:
            return False, "Gemini API key is not configured."

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.gemini_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_instruction}\n\n{user_prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        try:
            resp = requests.post(url, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return True, text
            else:
                return False, f"Gemini API returned HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, f"Gemini connection failed: {str(e)}"

    def _call_openai(self, system_instruction: str, user_prompt: str) -> Tuple[bool, str]:
        """Send prompt to OpenAI compatible endpoint via REST API."""
        if not self.openai_key:
            return False, "OpenAI API key is not configured."

        url = f"{self.openai_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model_name if self.model_name and "gemini" not in self.model_name else "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                return True, text
            else:
                return False, f"OpenAI API returned HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, f"OpenAI connection failed: {str(e)}"

    def _dispatch_prompt(self, system_instruction: str, user_prompt: str) -> Tuple[bool, str]:
        """Dispatches to active cloud LLM provider."""
        if self.provider == "gemini":
            return self._call_gemini(system_instruction, user_prompt)
        elif self.provider == "openai":
            return self._call_openai(system_instruction, user_prompt)
        return False, "Local mode active."

    def analyze_root_cause(
        self,
        code: str,
        traceback_text: str,
        report: AnalysisReport
    ) -> Dict[str, Any]:
        """Performs root cause analysis via LLM or local deterministic fallback."""
        # Try cloud LLM if configured
        if not self.is_local_mode:
            static_desc = []
            if not report.is_valid_syntax and report.syntax_error:
                static_desc.append(f"SyntaxError: {report.syntax_error.message} on line {report.syntax_error.location.line_number}")
            for b in report.confirmed_bugs:
                static_desc.append(f"Confirmed {b.category}: {b.message} (Line {b.location.line_number})")
            for b in report.suspected_bugs:
                static_desc.append(f"Suspected {b.category}: {b.message} (Line {b.location.line_number})")

            prompt = ROOT_CAUSE_PROMPT.format(
                code=code,
                traceback=traceback_text or "No traceback provided.",
                static_findings="\n".join(static_desc) if static_desc else "No static anomalies found."
            )

            success, raw_resp = self._dispatch_prompt(SYSTEM_PROMPT, prompt)
            if success:
                try:
                    data = json.loads(clean_json_text(raw_resp))
                    data["analysis_source"] = f"LLM ({self.provider})"
                    return data
                except Exception:
                    pass  # Fall through to deterministic analyzer

        # Local Deterministic Fallback
        return self._local_root_cause_analysis(code, traceback_text, report)

    def _local_root_cause_analysis(
        self,
        code: str,
        traceback_text: str,
        report: AnalysisReport
    ) -> Dict[str, Any]:
        """Deterministic root-cause reasoning based on AST and traceback parsing."""
        if not report.is_valid_syntax and report.syntax_error:
            loc = report.syntax_error.location
            return {
                "bug_category": "SyntaxError",
                "severity": "HIGH",
                "offending_line_number": loc.line_number,
                "root_cause_explanation": f"The Python interpreter failed to parse the file due to invalid syntax on line {loc.line_number}: {report.syntax_error.message}",
                "expected_behavior": "Valid Python statement adhering to language grammar specifications.",
                "actual_behavior": f"SyntaxError raised on line {loc.line_number}: '{loc.line_content}'.",
                "repair_strategy": "Correct statement syntax (e.g. add missing colon, balance parentheses, or correct assignment).",
                "analysis_source": "Local Deterministic Engine"
            }

        # Check confirmed bugs from traceback
        if report.confirmed_bugs:
            primary = report.confirmed_bugs[0]
            loc = primary.location
            line_no = loc.line_number
            cat = primary.category

            explanation = primary.message
            expected = "Execution without runtime exceptions."
            actual = f"Raised {cat}: {primary.message}"

            if cat == "NameError":
                expected = "Referenced identifier must be defined in the local/global scope or imported before use."
                actual = f"Attempted to access undefined symbol on line {line_no}."
            elif cat == "IndexError":
                expected = "Index must be strictly within range 0 <= index < len(sequence)."
                actual = f"Sequence index accessed out of range on line {line_no}."
            elif cat == "TypeError":
                expected = "Compatible operand types for operations."
                actual = f"Type mismatch or invalid operation on line {line_no}."

            return {
                "bug_category": cat,
                "severity": "HIGH",
                "offending_line_number": line_no,
                "root_cause_explanation": explanation,
                "expected_behavior": expected,
                "actual_behavior": actual,
                "repair_strategy": primary.suggested_fix_hint or "Refactor code to satisfy preconditions.",
                "analysis_source": "Local Deterministic Engine"
            }

        # Check suspected bugs
        if report.suspected_bugs:
            sus = report.suspected_bugs[0]
            return {
                "bug_category": sus.category,
                "severity": sus.severity,
                "offending_line_number": sus.location.line_number,
                "root_cause_explanation": sus.message,
                "expected_behavior": "Adherence to Python clean code and safe execution conventions.",
                "actual_behavior": f"Static inspection detected suspected issue on line {sus.location.line_number}.",
                "repair_strategy": sus.suggested_fix_hint or "Review and fix suspected issue.",
                "analysis_source": "Local Deterministic Engine"
            }

        # Fallback general
        return {
            "bug_category": "LogicalError",
            "severity": "MEDIUM",
            "offending_line_number": None,
            "root_cause_explanation": "Code has no static syntax errors; bug is likely an assertion failure or behavioral logic defect.",
            "expected_behavior": "Code logic produces results matching test expectations.",
            "actual_behavior": "Assertion failure or incorrect runtime computation.",
            "repair_strategy": "Inspect function formulas, condition branches, and return values against test criteria.",
            "analysis_source": "Local Deterministic Engine"
        }

    def generate_repair_patch(
        self,
        code: str,
        traceback_text: str,
        root_cause: Dict[str, Any],
        report: AnalysisReport,
        test_failure_msg: str = "",
        iteration: int = 1
    ) -> Optional[ProposedPatch]:
        """Proposes a code patch using LLM or local deterministic rule engine."""
        # Try cloud LLM if configured
        if not self.is_local_mode:
            retry_context = ""
            if test_failure_msg:
                retry_context = f"### Previous Patch Test Failure (Attempt {iteration - 1}):\n```text\n{test_failure_msg}\n```\nPlease modify the fix to resolve this test failure."

            prompt = REPAIR_PATCH_PROMPT.format(
                code=code,
                traceback=traceback_text or "None",
                root_cause_json=json.dumps(root_cause, indent=2),
                retry_context=retry_context
            )

            success, raw_resp = self._dispatch_prompt(SYSTEM_PROMPT, prompt)
            if success:
                try:
                    data = json.loads(clean_json_text(raw_resp))
                    repaired_code = data.get("repaired_code", "")
                    explanation = data.get("explanation", "Repaired by AI agent.")
                    changes = data.get("changes_made", [])

                    if repaired_code:
                        valid, err = PatchValidator.validate_syntax(repaired_code)
                        diff = DiffGenerator.generate_unified_diff(code, repaired_code)
                        return ProposedPatch(
                            original_code=code,
                            repaired_code=repaired_code,
                            explanation=explanation,
                            changes_made=changes if isinstance(changes, list) else [str(changes)],
                            unified_diff=diff,
                            is_syntactically_valid=valid,
                            syntax_error_details=err,
                            iteration=iteration
                        )
                except Exception:
                    pass  # Fall through to local deterministic engine

        # Local Deterministic Engine
        patch = LocalDeterministicRepairEngine.repair(code, report, test_failure_msg)
        if patch:
            patch.iteration = iteration
        return patch

