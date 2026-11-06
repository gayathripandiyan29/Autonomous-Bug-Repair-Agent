"""
Static and Dynamic Code Analyzer for Python Code.
Performs AST parsing, scope inspection, common bug heuristic checks,
and structured traceback parsing.
"""

import ast
import re
import builtins
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set


@dataclass
class CodeLocation:
    """Represents a specific location in code with context lines."""
    line_number: Optional[int]
    column_offset: Optional[int] = None
    line_content: Optional[str] = None
    context_before: List[str] = field(default_factory=list)
    context_after: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_number": self.line_number,
            "column_offset": self.column_offset,
            "line_content": self.line_content,
            "context_before": self.context_before,
            "context_after": self.context_after,
        }


@dataclass
class BugFinding:
    """Represents an individual detected bug or code issue."""
    category: str              # e.g., 'SyntaxError', 'NameError', 'IndexError', 'LogicalError'
    confidence: str            # 'CONFIRMED' or 'SUSPECTED'
    message: str               # Human-readable explanation
    location: CodeLocation
    suggested_fix_hint: str = ""
    severity: str = "ERROR"    # 'ERROR', 'WARNING', 'INFO'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "confidence": self.confidence,
            "message": self.message,
            "location": self.location.to_dict(),
            "suggested_fix_hint": self.suggested_fix_hint,
            "severity": self.severity,
        }


@dataclass
class TracebackFrame:
    """Represents a single stack frame from a traceback."""
    filename: str
    line_number: int
    function_name: str
    code_line: str


@dataclass
class TracebackInfo:
    """Parsed traceback details."""
    exception_type: str
    exception_message: str
    frames: List[TracebackFrame] = field(default_factory=list)
    primary_frame: Optional[TracebackFrame] = None
    raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exception_type": self.exception_type,
            "exception_message": self.exception_message,
            "primary_line": self.primary_frame.line_number if self.primary_frame else None,
            "primary_function": self.primary_frame.function_name if self.primary_frame else None,
            "primary_code": self.primary_frame.code_line if self.primary_frame else None,
            "frame_count": len(self.frames),
        }


@dataclass
class AnalysisReport:
    """Complete static and traceback analysis report for submitted code."""
    is_valid_syntax: bool
    syntax_error: Optional[BugFinding] = None
    traceback_info: Optional[TracebackInfo] = None
    confirmed_bugs: List[BugFinding] = field(default_factory=list)
    suspected_bugs: List[BugFinding] = field(default_factory=list)
    total_lines: int = 0
    symbols_defined: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return not self.is_valid_syntax or len(self.confirmed_bugs) > 0 or len(self.suspected_bugs) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid_syntax": self.is_valid_syntax,
            "syntax_error": self.syntax_error.to_dict() if self.syntax_error else None,
            "traceback_info": self.traceback_info.to_dict() if self.traceback_info else None,
            "confirmed_bugs": [b.to_dict() for b in self.confirmed_bugs],
            "suspected_bugs": [b.to_dict() for b in self.suspected_bugs],
            "total_lines": self.total_lines,
            "symbols_defined": self.symbols_defined,
            "imports": self.imports,
        }


class CodeContextExtractor:
    """Extracts line contents and surrounding context from code."""
    @staticmethod
    def get_context(code: str, target_line: Optional[int], context_lines: int = 3) -> CodeLocation:
        if not code or not target_line:
            return CodeLocation(line_number=target_line)

        lines = code.splitlines()
        total = len(lines)
        if target_line < 1 or target_line > total:
            return CodeLocation(line_number=target_line)

        idx = target_line - 1
        line_content = lines[idx]
        start_before = max(0, idx - context_lines)
        end_after = min(total, idx + 1 + context_lines)

        context_before = lines[start_before:idx]
        context_after = lines[idx + 1:end_after]

        return CodeLocation(
            line_number=target_line,
            line_content=line_content,
            context_before=context_before,
            context_after=context_after
        )


class ScopeInspector(ast.NodeVisitor):
    """
    Inspects Python AST to discover symbol definitions, usages, and potential
    NameErrors or dangerous patterns.
    """
    def __init__(self, code_lines: List[str]):
        self.code_lines = code_lines
        self.defined_globals: Set[str] = set(dir(builtins))
        self.defined_symbols: Set[str] = set()
        self.imports: Set[str] = set()
        self.suspected_bugs: List[BugFinding] = []
        self.scope_stack: List[Set[str]] = [set()]  # Global scope at index 0

    def _current_scope(self) -> Set[str]:
        return self.scope_stack[-1]

    def _is_defined(self, name: str) -> bool:
        if name in self.defined_globals or name in self.imports:
            return True
        for scope in reversed(self.scope_stack):
            if name in scope:
                return True
        return False

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.asname or alias.name
            self.imports.add(name.split('.')[0])
            self._current_scope().add(name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        for alias in node.names:
            name = alias.asname or alias.name
            self.imports.add(name)
            self._current_scope().add(name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._current_scope().add(node.name)
        self.defined_symbols.add(node.name)

        # Check for mutable default arguments
        for default in node.args.defaults + node.args.kw_defaults:
            if default and isinstance(default, (ast.List, ast.Dict, ast.Set)):
                loc = CodeContextExtractor.get_context("\n".join(self.code_lines), node.lineno)
                self.suspected_bugs.append(BugFinding(
                    category="LogicalError",
                    confidence="SUSPECTED",
                    severity="WARNING",
                    message=f"Function '{node.name}' uses a mutable default argument ({type(default).__name__}), which retains mutations across calls.",
                    location=loc,
                    suggested_fix_hint="Use None as default value and initialize the mutable object inside the function body."
                ))

        # Push new local scope
        local_scope = set()
        for arg in node.args.args + node.args.kwonlyargs:
            local_scope.add(arg.arg)
            self.defined_symbols.add(arg.arg)
        if node.args.vararg:
            local_scope.add(node.args.vararg.arg)
            self.defined_symbols.add(node.args.vararg.arg)
        if node.args.kwarg:
            local_scope.add(node.args.kwarg.arg)
            self.defined_symbols.add(node.args.kwarg.arg)

        self.scope_stack.append(local_scope)
        for stmt in node.body:
            self.visit(stmt)
        self.scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        # Treat async similarly
        self.visit_FunctionDef(node)  # type: ignore

    def visit_ClassDef(self, node: ast.ClassDef):
        self._current_scope().add(node.name)
        self.defined_symbols.add(node.name)
        self.scope_stack.append(set())
        for stmt in node.body:
            self.visit(stmt)
        self.scope_stack.pop()

    def visit_Assign(self, node: ast.Assign):
        # Register assigned variables into current scope
        for target in node.targets:
            self._register_target(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        self._register_target(node.target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign):
        self._register_target(node.target)
        self.generic_visit(node)

    def _register_target(self, target: ast.AST):
        if isinstance(target, ast.Name):
            self._current_scope().add(target.id)
            self.defined_symbols.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._register_target(elt)

    def visit_For(self, node: ast.For):
        self._register_target(node.target)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            if not self._is_defined(node.id):
                # Suggest potential spelling correction
                all_known = list(self.defined_symbols.union(self.imports).union(self._current_scope()))
                suggestion = ""
                import difflib
                matches = difflib.get_close_matches(node.id, all_known, n=1, cutoff=0.6)
                if matches:
                    suggestion = f"Did you mean '{matches[0]}'?"

                loc = CodeContextExtractor.get_context("\n".join(self.code_lines), node.lineno)
                self.suspected_bugs.append(BugFinding(
                    category="NameError",
                    confidence="SUSPECTED",
                    severity="ERROR",
                    message=f"Name '{node.id}' is used before definition or is not imported. {suggestion}".strip(),
                    location=loc,
                    suggested_fix_hint=suggestion or f"Define or import '{node.id}' before using it."
                ))
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript):
        # Check for potential out-of-bounds pattern: arr[len(arr)]
        if isinstance(node.slice, ast.Call):
            if isinstance(node.slice.func, ast.Name) and node.slice.func.id == "len":
                loc = CodeContextExtractor.get_context("\n".join(self.code_lines), node.lineno)
                self.suspected_bugs.append(BugFinding(
                    category="IndexError",
                    confidence="SUSPECTED",
                    severity="ERROR",
                    message="Indexing with len(sequence) will raise IndexError because Python uses zero-based indexing.",
                    location=loc,
                    suggested_fix_hint="Use len(sequence) - 1 for the last element or negative indexing [-1]."
                ))
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp):
        # Check for division by constant zero
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            if isinstance(node.right, ast.Constant) and node.right.value == 0:
                loc = CodeContextExtractor.get_context("\n".join(self.code_lines), node.lineno)
                self.suspected_bugs.append(BugFinding(
                    category="ZeroDivisionError",
                    confidence="CONFIRMED",
                    severity="ERROR",
                    message="Division or modulo by literal zero detected.",
                    location=loc,
                    suggested_fix_hint="Ensure the divisor is non-zero before performing division."
                ))
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare):
        # Check for 'x == None' instead of 'x is None'
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comparator, ast.Constant) and comparator.value is None:
                loc = CodeContextExtractor.get_context("\n".join(self.code_lines), node.lineno)
                op_str = "==" if isinstance(op, ast.Eq) else "!="
                rec_str = "is None" if isinstance(op, ast.Eq) else "is not None"
                self.suspected_bugs.append(BugFinding(
                    category="LogicalError",
                    confidence="SUSPECTED",
                    severity="WARNING",
                    message=f"Comparison with None using '{op_str}' (PEP 8 recommends '{rec_str}').",
                    location=loc,
                    suggested_fix_hint=f"Use '{rec_str}' instead of '{op_str} None'."
                ))
        self.generic_visit(node)


class TracebackAnalyzer:
    """Parses standard Python tracebacks and isolates the offending error."""

    # Matches lines like: File "main.py", line 12, in <module>
    FRAME_REGEX = re.compile(r'File\s+["\']([^"\']+)["\'],\s+line\s+(\d+)(?:,\s+in\s+([^\n\r]+))?')
    # Matches the trailing exception line: NameError: name 'foo' is not defined
    EXCEPTION_REGEX = re.compile(r'^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning|Interrupt)?):\s*(.*)$', re.MULTILINE)

    @classmethod
    def parse(cls, traceback_text: str) -> Optional[TracebackInfo]:
        if not traceback_text or not traceback_text.strip():
            return None

        lines = traceback_text.strip().splitlines()
        frames: List[TracebackFrame] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            match = cls.FRAME_REGEX.search(line)
            if match:
                filename = match.group(1)
                lineno = int(match.group(2))
                func_name = match.group(3) or "<unknown>"
                code_line = ""
                if i + 1 < len(lines) and not lines[i + 1].strip().startswith("File "):
                    code_line = lines[i + 1].strip()
                    i += 1
                frames.append(TracebackFrame(
                    filename=filename,
                    line_number=lineno,
                    function_name=func_name,
                    code_line=code_line
                ))
            i += 1

        # Locate exception type and message
        exc_type = "RuntimeError"
        exc_msg = ""
        for line in reversed(lines):
            line_str = line.strip()
            match = cls.EXCEPTION_REGEX.match(line_str)
            if match:
                exc_type = match.group(1)
                exc_msg = match.group(2)
                break
            elif ": " in line_str and not line_str.startswith("File "):
                parts = line_str.split(": ", 1)
                if parts[0].endswith("Error") or parts[0].endswith("Exception"):
                    exc_type = parts[0]
                    exc_msg = parts[1]
                    break

        # If no regex match found, check simple format e.g. "IndexError: list index out of range"
        if not exc_msg and lines:
            last = lines[-1].strip()
            if ": " in last:
                t, m = last.split(": ", 1)
                exc_type = t
                exc_msg = m
            else:
                exc_msg = last

        primary_frame = frames[-1] if frames else None

        return TracebackInfo(
            exception_type=exc_type,
            exception_message=exc_msg,
            frames=frames,
            primary_frame=primary_frame,
            raw_text=traceback_text.strip()
        )


class CodeAnalyzer:
    """Main analyzer combining AST static analysis and traceback inspection."""

    @classmethod
    def analyze(cls, code: str, traceback_text: Optional[str] = None) -> AnalysisReport:
        if not code:
            code = ""

        code_lines = code.splitlines()
        total_lines = len(code_lines)

        confirmed_bugs: List[BugFinding] = []
        suspected_bugs: List[BugFinding] = []
        syntax_finding: Optional[BugFinding] = None
        is_valid_syntax = True
        symbols: List[str] = []
        imports_list: List[str] = []

        # 1. Parse AST for Syntax Errors
        try:
            tree = ast.parse(code, filename="<user_code>")
        except SyntaxError as e:
            is_valid_syntax = False
            err_line = e.lineno or 1
            loc = CodeContextExtractor.get_context(code, err_line)
            loc.column_offset = e.offset

            syntax_finding = BugFinding(
                category="SyntaxError",
                confidence="CONFIRMED",
                severity="ERROR",
                message=f"Syntax Error on line {err_line}: {e.msg}",
                location=loc,
                suggested_fix_hint="Check for missing colons (:), unclosed parentheses/quotes, or malformed statements."
            )
            confirmed_bugs.append(syntax_finding)
            return AnalysisReport(
                is_valid_syntax=False,
                syntax_error=syntax_finding,
                traceback_info=TracebackAnalyzer.parse(traceback_text) if traceback_text else None,
                confirmed_bugs=confirmed_bugs,
                suspected_bugs=[],
                total_lines=total_lines
            )

        # 2. Scope & Static Heuristics Inspection
        inspector = ScopeInspector(code_lines)
        try:
            inspector.visit(tree)
            suspected_bugs.extend(inspector.suspected_bugs)
            symbols = sorted(list(inspector.defined_symbols))
            imports_list = sorted(list(inspector.imports))
        except Exception:
            # Fallback if visitor encounters unexpected AST node
            pass

        # 3. Traceback Inspection (if provided)
        tb_info = None
        if traceback_text and traceback_text.strip():
            tb_info = TracebackAnalyzer.parse(traceback_text)
            if tb_info and tb_info.primary_frame:
                pf = tb_info.primary_frame
                # If primary line falls within user code line range
                target_line = pf.line_number if (1 <= pf.line_number <= total_lines) else None
                loc = CodeContextExtractor.get_context(code, target_line)
                if not loc.line_content and pf.code_line:
                    loc.line_content = pf.code_line

                confirmed_from_tb = BugFinding(
                    category=tb_info.exception_type,
                    confidence="CONFIRMED",
                    severity="ERROR",
                    message=f"{tb_info.exception_type}: {tb_info.exception_message}",
                    location=loc,
                    suggested_fix_hint=cls._infer_fix_hint(tb_info.exception_type, tb_info.exception_message)
                )
                # Avoid duplicate with suspected bugs
                suspected_bugs = [
                    s for s in suspected_bugs 
                    if not (s.category == confirmed_from_tb.category and s.location.line_number == target_line)
                ]
                confirmed_bugs.append(confirmed_from_tb)

        return AnalysisReport(
            is_valid_syntax=is_valid_syntax,
            syntax_error=None,
            traceback_info=tb_info,
            confirmed_bugs=confirmed_bugs,
            suspected_bugs=suspected_bugs,
            total_lines=total_lines,
            symbols_defined=symbols,
            imports=imports_list
        )

    @staticmethod
    def _infer_fix_hint(exception_type: str, message: str) -> str:
        """Infer a simple rule-based hint based on the exception."""
        if exception_type == "NameError":
            match = re.search(r"name '([^']+)' is not defined", message)
            var_name = match.group(1) if match else "variable"
            return f"Define '{var_name}' or check for typos in the name before referencing it."
        elif exception_type == "IndexError":
            return "Verify collection boundary lengths before accessing indices or use safe lookup."
        elif exception_type == "KeyError":
            match = re.search(r"'([^']+)'", message)
            key_name = match.group(1) if match else "key"
            return f"Ensure dictionary contains key '{key_name}' or use .get('{key_name}', default)."
        elif exception_type == "TypeError":
            return "Ensure operands and argument types match expected types (e.g. str vs int conversions)."
        elif exception_type == "ZeroDivisionError":
            return "Check if the denominator is zero before division."
        elif exception_type == "AttributeError":
            return "Check object methods and attributes or ensure object is not None."
        return "Review the offending line and verify preconditions."
