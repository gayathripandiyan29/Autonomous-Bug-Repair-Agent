"""Unit tests for isolated execution sandbox."""

import pytest
import os
from debugger.sandbox import ExecutionSandbox


def test_sandbox_file_creation_and_execution():
    with ExecutionSandbox(timeout_seconds=5) as sandbox:
        script = "print('HELLO_FROM_SANDBOX')"
        sandbox.write_file("test.py", script)
        res = sandbox.run_python_script("test.py")
        assert res.is_success
        assert "HELLO_FROM_SANDBOX" in res.stdout.strip()
        assert not res.timed_out


def test_sandbox_timeout_handling():
    with ExecutionSandbox(timeout_seconds=2) as sandbox:
        # Script with infinite loop
        script = "import time\nwhile True:\n    time.sleep(0.1)"
        sandbox.write_file("loop.py", script)
        res = sandbox.run_python_script("loop.py")
        assert res.timed_out
        assert not res.is_success
        assert "timed out" in res.error_message.lower()


def test_sandbox_environment_sanitization():
    # Set a sensitive fake key in host environment
    os.environ["FAKE_TEST_API_KEY"] = "super_secret_token_12345"
    with ExecutionSandbox(timeout_seconds=3) as sandbox:
        safe_env = sandbox._build_safe_env()
        # Verify sensitive key was stripped
        assert "FAKE_TEST_API_KEY" not in safe_env
    # Clean up test env var
    os.environ.pop("FAKE_TEST_API_KEY", None)

