"""
Isolated Sandbox Execution Environment for Untrusted Python Code.
Runs code and test suites in separate subprocesses with strict timeouts,
sanitized environment variables, and temporary workspace isolation.
"""

import os
import sys
import time
import shutil
import tempfile
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, List, Any


@dataclass
class SandboxExecutionResult:
    """Outcome of running code or commands in the isolated sandbox."""
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    execution_time_ms: float
    error_message: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "execution_time_ms": self.execution_time_ms,
            "is_success": self.is_success,
            "error_message": self.error_message,
        }


class ExecutionSandbox:
    """
    Manages an isolated temporary directory and runs subprocesses with resource limits.
    Guarantees no execution in the host process and removes sensitive credentials.
    """

    # Sensitive environment key fragments to purge
    SENSITIVE_KEY_FRAGMENTS = [
        "KEY", "TOKEN", "SECRET", "AUTH", "PASS", "CREDENTIAL", "COOKIE", "AGENTAPI"
    ]

    def __init__(self, timeout_seconds: int = 8, max_output_chars: int = 15000):
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars
        self.sandbox_dir: Optional[Path] = None

    def __enter__(self):
        self.create()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def create(self) -> Path:
        """Create a fresh temporary sandbox directory."""
        if not self.sandbox_dir:
            temp_dir = tempfile.mkdtemp(prefix="agent_sb_")
            self.sandbox_dir = Path(temp_dir).resolve()
        return self.sandbox_dir

    def cleanup(self):
        """Remove the sandbox directory and all temporary files."""
        if self.sandbox_dir and self.sandbox_dir.exists():
            try:
                shutil.rmtree(self.sandbox_dir, ignore_errors=True)
            except Exception as e:
                print(f"Warning: Failed to clean sandbox dir {self.sandbox_dir}: {e}")
            finally:
                self.sandbox_dir = None

    def write_file(self, relative_path: str, content: str) -> Path:
        """Safely write a file inside the sandbox."""
        if not self.sandbox_dir:
            self.create()
        assert self.sandbox_dir is not None

        # Resolve path safely and ensure no path traversal outside sandbox
        dest = (self.sandbox_dir / relative_path).resolve()
        if not str(dest).startswith(str(self.sandbox_dir)):
            raise ValueError("Path traversal attempt detected in sandbox.")

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        return dest

    def read_file(self, relative_path: str) -> str:
        """Read a file from within the sandbox."""
        if not self.sandbox_dir:
            raise RuntimeError("Sandbox not initialized.")
        dest = (self.sandbox_dir / relative_path).resolve()
        if not str(dest).startswith(str(self.sandbox_dir)):
            raise ValueError("Path traversal attempt detected in sandbox.")
        if not dest.exists():
            raise FileNotFoundError(f"File not found in sandbox: {relative_path}")
        return dest.read_text(encoding="utf-8")

    def _build_safe_env(self) -> Dict[str, str]:
        """
        Create a sanitized environment dictionary without API keys, secrets,
        or unauthorized environment variables.
        """
        safe_env = {}
        # Retain necessary system paths for python execution (Windows + POSIX/Linux)
        allowed_vars = [
            "SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", 
            "USERPROFILE", "HOMEPATH", "HOMEDRIVE", "NUMBER_OF_PROCESSORS",
            "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "TERM"
        ]

        for k, v in os.environ.items():
            k_upper = k.upper()
            # Skip any sensitive tokens
            if any(frag in k_upper for frag in self.SENSITIVE_KEY_FRAGMENTS):
                continue
            if k_upper in allowed_vars:
                safe_env[k] = v

        # Isolated Python configurations
        safe_env["PYTHONDONTWRITEBYTECODE"] = "1"
        safe_env["PYTHONUNBUFFERED"] = "1"
        safe_env["PYTHONIOENCODING"] = "utf-8"
        # Isolate sys.path so sandbox directory is the primary search path
        if self.sandbox_dir:
            safe_env["PYTHONPATH"] = str(self.sandbox_dir)

        return safe_env

    def run_command(self, cmd_args: List[str]) -> SandboxExecutionResult:
        """Run an isolated subprocess inside the sandbox directory."""
        if not self.sandbox_dir:
            self.create()
        assert self.sandbox_dir is not None

        env = self._build_safe_env()
        start_time = time.perf_counter()

        try:
            process = subprocess.run(
                cmd_args,
                cwd=str(self.sandbox_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                shell=False
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            stdout = process.stdout or ""
            stderr = process.stderr or ""

            # Truncate excessive outputs
            if len(stdout) > self.max_output_chars:
                stdout = stdout[:self.max_output_chars] + f"\n... [Truncated: exceeded {self.max_output_chars} chars]"
            if len(stderr) > self.max_output_chars:
                stderr = stderr[:self.max_output_chars] + f"\n... [Truncated: exceeded {self.max_output_chars} chars]"

            return SandboxExecutionResult(
                exit_code=process.returncode,
                stdout=stdout,
                stderr=stderr,
                timed_out=False,
                execution_time_ms=round(elapsed_ms, 2)
            )

        except subprocess.TimeoutExpired as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
            stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
            return SandboxExecutionResult(
                exit_code=-1,
                stdout=stdout,
                stderr=stderr + f"\n[Process killed: Execution timed out after {self.timeout_seconds}s]",
                timed_out=True,
                execution_time_ms=round(elapsed_ms, 2),
                error_message=f"Execution timed out after {self.timeout_seconds} seconds (possible infinite loop)."
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return SandboxExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                timed_out=False,
                execution_time_ms=round(elapsed_ms, 2),
                error_message=f"Failed to execute process in sandbox: {e}"
            )

    def run_python_script(self, script_filename: str) -> SandboxExecutionResult:
        """Run a Python script file using the isolated Python interpreter."""
        cmd = [sys.executable, "-B", script_filename]
        return self.run_command(cmd)

    def run_pytest(self, test_filename: str, extra_args: Optional[List[str]] = None) -> SandboxExecutionResult:
        """Run pytest on a specified test file in the sandbox."""
        cmd = [sys.executable, "-m", "pytest", test_filename, "-v", "--tb=short"]
        if extra_args:
            cmd.extend(extra_args)
        return self.run_command(cmd)

