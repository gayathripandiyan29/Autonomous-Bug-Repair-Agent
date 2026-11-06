"""
Code Repair and Patch Management Engine.
Handles AST syntax validation, patch formatting, unified and side-by-side diffs,
and deterministic local repair templates for common Python bugs.
"""

import ast
import re
import difflib
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from debugger.analyzer import AnalysisReport, BugFinding


@dataclass
class ProposedPatch:
    """Represents a proposed code repair."""
    original_code: str
    repaired_code: str
    explanation: str
    changes_made: List[str]
    unified_diff: str
    is_syntactically_valid: bool
    syntax_error_details: Optional[str] = None
    iteration: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repaired_code": self.repaired_code,
            "explanation": self.explanation,
            "changes_made": self.changes_made,
            "unified_diff": self.unified_diff,
            "is_syntactically_valid": self.is_syntactically_valid,
            "syntax_error_details": self.syntax_error_details,
            "iteration": self.iteration,
        }


class PatchValidator:
    """Validates that proposed code is syntactically correct Python."""

    @staticmethod
    def validate_syntax(code: str) -> Tuple[bool, Optional[str]]:
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError on line {e.lineno}: {e.msg}"
        except Exception as e:
            return False, f"Parsing error: {str(e)}"


class DiffGenerator:
    """Generates unified diffs and side-by-side line comparisons."""

    @staticmethod
    def generate_unified_diff(original: str, modified: str, filename: str = "code.py") -> str:
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

    @staticmethod
    def generate_side_by_side(original: str, modified: str) -> List[Dict[str, Any]]:
        """
        Creates aligned rows for side-by-side rendering in Streamlit.
        Returns a list of dicts: {orig_line_no, orig_text, mod_line_no, mod_text, change_type}
        """
        orig_lines = original.splitlines()
        mod_lines = modified.splitlines()

        matcher = difflib.SequenceMatcher(None, orig_lines, mod_lines)
        rows: List[Dict[str, Any]] = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for o_idx, m_idx in zip(range(i1, i2), range(j1, j2)):
                    rows.append({
                        "orig_line": o_idx + 1,
                        "orig_text": orig_lines[o_idx],
                        "mod_line": m_idx + 1,
                        "mod_text": mod_lines[m_idx],
                        "status": "unchanged"
                    })
            elif tag == 'replace':
                len_orig = i2 - i1
                len_mod = j2 - j1
                max_len = max(len_orig, len_mod)
                for offset in range(max_len):
                    o_idx = i1 + offset if offset < len_orig else None
                    m_idx = j1 + offset if offset < len_mod else None
                    rows.append({
                        "orig_line": (o_idx + 1) if o_idx is not None else "",
                        "orig_text": orig_lines[o_idx] if o_idx is not None else "",
                        "mod_line": (m_idx + 1) if m_idx is not None else "",
                        "mod_text": mod_lines[m_idx] if m_idx is not None else "",
                        "status": "modified"
                    })
            elif tag == 'delete':
                for o_idx in range(i1, i2):
                    rows.append({
                        "orig_line": o_idx + 1,
                        "orig_text": orig_lines[o_idx],
                        "mod_line": "",
                        "mod_text": "",
                        "status": "removed"
                    })
            elif tag == 'insert':
                for m_idx in range(j1, j2):
                    rows.append({
                        "orig_line": "",
                        "orig_text": "",
                        "mod_line": m_idx + 1,
                        "mod_text": mod_lines[m_idx],
                        "status": "added"
                    })
        return rows


class LocalDeterministicRepairEngine:
    """
    Deterministic rule-based repair engine.
    Used when no LLM API key is present or as an offline fast-path.
    """

    @classmethod
    def repair(cls, code: str, report: AnalysisReport, test_failure_msg: str = "") -> Optional[ProposedPatch]:
        lines = code.splitlines()

        # 1. Handle Syntax Errors
        if not report.is_valid_syntax and report.syntax_error:
            repaired_lines = list(lines)
            err_line = report.syntax_error.location.line_number or 1
            idx = err_line - 1

            if 0 <= idx < len(repaired_lines):
                target_line = repaired_lines[idx]

                # Case A: Missing colon on def, if, for, while, class, elif, else, try, except, finally
                colon_keywords = ("def ", "if ", "for ", "while ", "class ", "elif ", "else", "try", "except", "finally")
                stripped = target_line.rstrip()
                if any(stripped.lstrip().startswith(kw) for kw in colon_keywords) and not stripped.endswith(":"):
                    repaired_lines[idx] = stripped + ":"
                    new_code = "\n".join(repaired_lines)
                    valid, err = PatchValidator.validate_syntax(new_code)
                    if valid:
                        diff = DiffGenerator.generate_unified_diff(code, new_code)
                        return ProposedPatch(
                            original_code=code,
                            repaired_code=new_code,
                            explanation=f"Added missing colon ':' to statement header on line {err_line}.",
                            changes_made=[f"Line {err_line}: Appended ':' at end of line."],
                            unified_diff=diff,
                            is_syntactically_valid=True
                        )

                # Case B: Assignment '=' inside 'if' or 'while' condition: 'if x = 1:'
                if re.search(r'\b(if|while)\s+[^=!<>]=[^=]', target_line):
                    fixed_line = re.sub(r'(\b(?:if|while)\s+[^=!<>]?)\s*=\s*([^=])', r'\1 == \2', target_line)
                    repaired_lines[idx] = fixed_line
                    new_code = "\n".join(repaired_lines)
                    valid, err = PatchValidator.validate_syntax(new_code)
                    if valid:
                        diff = DiffGenerator.generate_unified_diff(code, new_code)
                        return ProposedPatch(
                            original_code=code,
                            repaired_code=new_code,
                            explanation=f"Replaced assignment '=' with equality check '==' on line {err_line}.",
                            changes_made=[f"Line {err_line}: Changed '=' comparison to '=='."],
                            unified_diff=diff,
                            is_syntactically_valid=True
                        )

                # Case C: Unclosed parenthesis / bracket
                if target_line.count('(') > target_line.count(')'):
                    missing_closing = ')' * (target_line.count('(') - target_line.count(')'))
                    repaired_lines[idx] = target_line + missing_closing
                    new_code = "\n".join(repaired_lines)
                    valid, err = PatchValidator.validate_syntax(new_code)
                    if valid:
                        diff = DiffGenerator.generate_unified_diff(code, new_code)
                        return ProposedPatch(
                            original_code=code,
                            repaired_code=new_code,
                            explanation=f"Appended missing closing parenthesis ')' on line {err_line}.",
                            changes_made=[f"Line {err_line}: Closed unclosed parenthesis."],
                            unified_diff=diff,
                            is_syntactically_valid=True
                        )

        # 2. Handle NameError (typo or missing definition)
        for bug in report.confirmed_bugs + report.suspected_bugs:
            if bug.category == "NameError":
                match = re.search(r"name '([^']+)' is not defined", bug.message)
                if not match and "Did you mean" in bug.message:
                    match = re.search(r"Name '([^']+)' is used", bug.message)
                
                bad_var = match.group(1) if match else None
                if bad_var:
                    # Check for Python's "Did you mean: '...'?" directly
                    did_you_mean = re.search(r"Did you mean: '([^']+)'\?", bug.message)
                    replacement = did_you_mean.group(1) if did_you_mean else None

                    if not replacement:
                        # Look for closest match among defined symbols or words in code
                        all_words = set(report.symbols_defined + report.imports + re.findall(r'\b[a-zA-Z_]\w*\b', code))
                        if bad_var in all_words:
                            all_words.remove(bad_var)
                        closest = difflib.get_close_matches(bad_var, list(all_words), n=1, cutoff=0.5)
                        if closest:
                            replacement = closest[0]

                    if replacement:
                        # Replace bad_var with replacement
                        new_code = re.sub(r'\b' + re.escape(bad_var) + r'\b', replacement, code)
                        valid, err = PatchValidator.validate_syntax(new_code)
                        if valid and new_code != code:
                            diff = DiffGenerator.generate_unified_diff(code, new_code)
                            return ProposedPatch(
                                original_code=code,
                                repaired_code=new_code,
                                explanation=f"Corrected identifier typo '{bad_var}' to defined variable '{replacement}'.",
                                changes_made=[f"Replaced '{bad_var}' with '{replacement}'."],
                                unified_diff=diff,
                                is_syntactically_valid=True
                            )

                    # Check if it's a common standard library module like 'math', 'sys', 'os', 'json', 're'
                    std_libs = ["math", "sys", "os", "json", "re", "time", "random"]
                    if bad_var in std_libs:
                        new_code = f"import {bad_var}\n" + code
                        diff = DiffGenerator.generate_unified_diff(code, new_code)
                        return ProposedPatch(
                            original_code=code,
                            repaired_code=new_code,
                            explanation=f"Added missing import 'import {bad_var}'.",
                            changes_made=[f"Added 'import {bad_var}' at top of file."],
                            unified_diff=diff,
                            is_syntactically_valid=True
                        )

        # 3. Handle IndexError (Off-by-one error or len(x) index)
        for bug in report.confirmed_bugs + report.suspected_bugs:
            if bug.category == "IndexError":
                err_line = bug.location.line_number
                repaired_lines = list(lines)
                if err_line and 0 < err_line <= len(repaired_lines):
                    target = repaired_lines[err_line - 1]
                    # Pattern 1: arr[len(arr)] -> arr[len(arr) - 1] or arr[-1]
                    if re.search(r'\[\s*len\(([^)]+)\)\s*\]', target):
                        fixed = re.sub(r'\[\s*len\(([^)]+)\)\s*\]', r'[-1]', target)
                        repaired_lines[err_line - 1] = fixed
                        new_code = "\n".join(repaired_lines)
                        diff = DiffGenerator.generate_unified_diff(code, new_code)
                        return ProposedPatch(
                            original_code=code,
                            repaired_code=new_code,
                            explanation=f"Fixed IndexError on line {err_line}: Replaced out-of-bounds index [len(...)] with [-1].",
                            changes_made=[f"Line {err_line}: Changed out-of-bounds index to [-1]."],
                            unified_diff=diff,
                            is_syntactically_valid=True
                        )
                    # Pattern 2: range(0, len(arr) + 1) -> range(len(arr))
                    if "range" in target and "+ 1" in target:
                        fixed = re.sub(r'range\(([^,]+),\s*len\(([^)]+)\)\s*\+\s*1\)', r'range(\1, len(\2))', target)
                        if fixed != target:
                            repaired_lines[err_line - 1] = fixed
                            new_code = "\n".join(repaired_lines)
                            diff = DiffGenerator.generate_unified_diff(code, new_code)
                            return ProposedPatch(
                                original_code=code,
                                repaired_code=new_code,
                                explanation=f"Fixed off-by-one loop boundary on line {err_line}.",
                                changes_made=[f"Line {err_line}: Corrected loop range to avoid out-of-bounds index."],
                                unified_diff=diff,
                                is_syntactically_valid=True
                            )
                
                # Check entire code for arr[len(arr)] if line wasn't pinpointed
                if re.search(r'\[\s*len\(([^)]+)\)\s*\]', code):
                    new_code = re.sub(r'\[\s*len\(([^)]+)\)\s*\]', r'[-1]', code)
                    diff = DiffGenerator.generate_unified_diff(code, new_code)
                    return ProposedPatch(
                        original_code=code,
                        repaired_code=new_code,
                        explanation="Fixed IndexError: Replaced out-of-bounds indexing [len(...)] with [-1].",
                        changes_made=["Changed '[len(...)]' to '[-1]'."],
                        unified_diff=diff,
                        is_syntactically_valid=True
                    )

        # 4. Handle TypeError (e.g., str concatenation with non-str)
        for bug in report.confirmed_bugs + report.suspected_bugs:
            if bug.category == "TypeError":
                err_line = bug.location.line_number
                if err_line and 0 < err_line <= len(lines):
                    target = lines[err_line - 1]
                    # If target concatenates string with a variable: e.g. "Result: " + val
                    cat_match = re.search(r'("[^"]*"\s*\+\s*([a-zA-Z_][a-zA-Z0-9_]*))', target)
                    if cat_match:
                        full_expr = cat_match.group(1)
                        var = cat_match.group(2)
                        fixed = target.replace(full_expr, full_expr.replace(var, f"str({var})"))
                        repaired_lines = list(lines)
                        repaired_lines[err_line - 1] = fixed
                        new_code = "\n".join(repaired_lines)
                        diff = DiffGenerator.generate_unified_diff(code, new_code)
                        return ProposedPatch(
                            original_code=code,
                            repaired_code=new_code,
                            explanation=f"Fixed TypeError on line {err_line}: Explicitly converted '{var}' to str before concatenation.",
                            changes_made=[f"Line {err_line}: Wrapped '{var}' in str()."],
                            unified_diff=diff,
                            is_syntactically_valid=True
                        )

        # 5. Handle failing test message hint or logic bug patterns (e.g. discount logic or return value)
        if test_failure_msg or "discount" in code.lower() or (report.traceback_info and "AssertionError" in report.traceback_info.exception_type):
            # Check for common logic bugs
            # E.g. off-by-one in return or discount formula: price - discount vs price * (1 - discount)
            if "discount" in code.lower() and "-" in code:
                # E.g. price - discount instead of price * (1 - discount / 100) or price - (price * discount)
                match = re.search(r'([a-zA-Z_]\w*)\s*-\s*([a-zA-Z_]*discount\w*)', code)
                if match:
                    price_var, disc_var = match.group(1), match.group(2)
                    fixed_code = re.sub(
                        rf'\b{price_var}\s*-\s*{disc_var}\b',
                        f"{price_var} - ({price_var} * {disc_var})",
                        code
                    )
                    valid, err = PatchValidator.validate_syntax(fixed_code)
                    if valid and fixed_code != code:
                        diff = DiffGenerator.generate_unified_diff(code, fixed_code)
                        return ProposedPatch(
                            original_code=code,
                            repaired_code=fixed_code,
                            explanation=f"Fixed discount calculation logic: applied fractional percentage discount properly.",
                            changes_made=[f"Changed '{price_var} - {disc_var}' to '{price_var} - ({price_var} * {disc_var})'."],
                            unified_diff=diff,
                            is_syntactically_valid=True
                        )

        # Fallback: No deterministic pattern matched
        return None
