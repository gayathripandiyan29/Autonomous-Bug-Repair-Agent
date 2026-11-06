# Autonomous Bug Detection & Repair Agent

An intelligent, autonomous software debugging agent built in Python and Streamlit. The agent inspects Python source code, analyzes runtime errors and tracebacks, performs static AST analysis, isolates root causes, drafts minimal surgical patches, executes unit and regression tests in an isolated sandbox, and tracks revisions with Git rollback support before presenting verified repairs for user approval.

---

## 🌟 Key Features

- **Automated Bug Detection**: Identifies syntax errors, `NameError`, `IndexError`, `TypeError`, `KeyError`, and behavioral logic flaws via static AST parsing and traceback heuristics.
- **Root Cause Analysis (RCA)**: Pinpoints the offending line of code and explains the disparity between *expected behavior* and *actual behavior* in plain English.
- **Isolated Execution Sandbox**: Untrusted code and test suites are executed in an ephemeral, subprocess-isolated environment with restricted permissions, sanitized environment variables (no leaked API keys), and strict timeouts (defending against infinite loops).
- **Git Version Tracking & Clean Rollback**: Tracks each proposed repair revision. If tests fail, the workspace rolls back to the clean baseline snapshot automatically before retrying.
- **Iterative Repair Loop**: If test assertions fail on a candidate patch, test failure details are fed back into the agent for up to $N$ retry iterations (configurable).
- **Honest Test Verification**: Never claims a fix works simply because the code executed without crashing; fixes are verified against passing Pytest assertions.
- **Dual Intelligence Modes**:
  - **Cloud LLM Agent**: Native support for **Google Gemini** (`gemini-2.0-flash`, `gemini-1.5-pro`) and **OpenAI-Compatible** APIs (OpenAI, Groq, OpenRouter, Ollama).
  - **Deterministic Local Engine**: Fully functional offline fallback mode using Python AST analysis, symbol resolution, and rule-based repair templates. Operates out-of-the-box with zero API keys required.
- **SQLite Debugging History**: Persists session metrics, bug categories, SHA-256 code fingerprints, diffs, and verification statuses without storing sensitive source code or credentials.
- **Interactive Streamlit Dashboard**: Code upload/pasting, traceback inspector, side-by-side and unified diff views, before/after test comparison tables, one-click patch approval, and code download.

---

## 🏗️ System Architecture

```
[ User Code + Traceback / Tests ]
               │
               ▼
   [ Workflow Controller ] ──────────────► [ State Machine ]
               │
   ┌───────────┴───────────┐
   ▼                       ▼
[ AST Analyzer ]   [ Traceback Parser ]
   │                       │
   └───────────┬───────────┘
               ▼
   [ Root Cause Diagnosis ] ◄──────────── [ Gemini / OpenAI / Local Rule Engine ]
               │
               ▼
    [ Repair Plan & Patch ]
               │
               ▼
    [ AST Syntax Validator ]
               │
               ▼
 [ Isolated Sandbox (Subprocess) ] ◄───── [ Git Tracker & Baseline Snapshot ]
               │
       [ Pytest Suite ]
       ┌───────┴───────┐
       ▼               ▼
   [ Passed ]      [ Failed ]
       │               │
       │       [ Rollback Git Baseline ]
       │               │
       │      [ Retry Loop (Iter <= N) ]
       │               │
       ▼               ▼
[ Verified Fix ]   [ Honest Unresolved ]
       │
       ▼
 [ Streamlit Dashboard & SQLite History ]
```

---

## 📁 Project Directory Structure

```
autonomous_bug_agent/
│
├── app.py                      # Streamlit debugging dashboard & UI
├── config.py                   # Environment loader & system configuration
├── requirements.txt            # Project dependencies
├── .env.example                # Sample environment variable template
├── .gitignore                  # Git ignore rules for virtualenvs, caches, secrets
├── README.md                   # Complete documentation & usage guide
│
├── agent/                      # Core agent logic
│   ├── __init__.py
│   ├── workflow.py             # Explicit state machine, retry loop & orchestrator
│   ├── tools.py                # Structured debugging tools (AST, sandbox, diffs)
│   ├── prompts.py              # System prompts & structured JSON output schemas
│   └── llm_client.py           # REST client for Gemini, OpenAI & local fallback
│
├── debugger/                   # Inspection, sandbox, and repair modules
│   ├── __init__.py
│   ├── analyzer.py             # AST static analysis & traceback parsing
│   ├── sandbox.py              # Isolated subprocess execution environment & timeouts
│   ├── git_tracker.py          # Git snapshotting, diffs, and rollback support
│   ├── test_runner.py          # Pytest execution & before/after result comparisons
│   └── repair.py               # Deterministic patch templates & diff generator
│
├── database/                   # Persistence layer
│   ├── __init__.py
│   ├── history.py              # SQLite storage for sessions, diffs, and metrics
│   └── bug_agent.db            # Local SQLite database (created on first run)
│
├── samples/                    # Curated sample buggy programs
│   ├── __init__.py
│   └── sample_programs.py      # NameError, SyntaxError, IndexError, Logic bugs
│
└── tests/                      # Automated test suite (31 unit & integration tests)
    ├── __init__.py
    ├── test_analyzer.py        # Tests for AST and traceback parsing
    ├── test_sandbox.py         # Tests for isolation, sanitized env, and timeouts
    ├── test_git_tracker.py     # Tests for git baseline commit & rollback
    ├── test_test_runner.py     # Tests for pytest execution & comparison
    ├── test_repair.py          # Tests for patch validation & deterministic fixes
    ├── test_history.py         # Tests for SQLite persistence & code hashing
    └── test_workflow.py        # 10 Acceptance Criteria integration tests
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- **Python 3.10+** (Tested and verified on Python 3.14)
- **Git** (optional, fallback in-memory engine included)

### 2. Installation
Clone or navigate to the project directory:
```bash
cd "c:\Users\acer\OneDrive\Desktop\err agentic ai"
```

Install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration (Optional)
The application works immediately in **Local Deterministic Mode** without any API keys.

To enable Cloud AI reasoning (e.g., Google Gemini or OpenAI):
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Add your API key:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   # OR
   OPENAI_API_KEY=your_openai_api_key_here
   ```

### 4. Running the Application
Launch the Streamlit web dashboard:
```bash
streamlit run app.py
```
Open your browser to `http://localhost:8501`.

---

## 🧪 Running Automated Tests

Run the complete test suite verifying all 10 acceptance criteria:
```bash
python -m pytest tests/ -v
```

Expected output:
```
tests/test_analyzer.py ......................... PASSED [ 19%]
tests/test_git_tracker.py ...................... PASSED [ 22%]
tests/test_history.py .......................... PASSED [ 29%]
tests/test_repair.py ........................... PASSED [ 48%]
tests/test_sandbox.py .......................... PASSED [ 58%]
tests/test_test_runner.py ...................... PASSED [ 67%]
tests/test_workflow.py ......................... PASSED [100%]

======================= 31 passed in 2.28s ========================
```

---

## 🎯 Verification of Acceptance Criteria

| # | Acceptance Criterion | Test Function | Result |
|---|----------------------|---------------|--------|
| 1 | Detect and explain a `NameError` | `test_ac1_detect_and_explain_name_error` | ✅ PASSED |
| 2 | Detect a syntax error | `test_ac2_detect_syntax_error` | ✅ PASSED |
| 3 | Identify and repair a simple `IndexError` | `test_ac3_identify_and_repair_index_error` | ✅ PASSED |
| 4 | Detect a failing unit test and propose a fix | `test_ac4_detect_failing_unit_test_and_repair` | ✅ PASSED |
| 5 | Show original and repaired code side-by-side | `test_ac5_show_original_and_repaired_code` | ✅ PASSED |
| 6 | Run regression tests and display results | `test_ac6_run_regression_tests` | ✅ PASSED |
| 7 | Preserve original code unmodified | `test_ac7_preserve_original_code` | ✅ PASSED |
| 8 | Store debugging session in SQLite | `test_ac8_store_debugging_session_in_sqlite` | ✅ PASSED |
| 9 | Handle missing API configuration gracefully | `test_ac9_handle_missing_api_configuration` | ✅ PASSED |
| 10 | Distinguish proposed fixes from verified fixes | `test_ac10_distinguish_proposed_from_verified_fixes` | ✅ PASSED |

---

## 🛡️ Safety & Security Considerations

1. **Host Isolation**: Submitted code is never evaluated with `eval()`, `exec()`, or imported into the main Streamlit process.
2. **Sanitized Child Environment**: Sensitive keys matching `KEY`, `TOKEN`, `SECRET`, `AUTH`, `PASS`, or `CREDENTIAL` are purged from the child process's environment variables prior to invocation.
3. **Execution Limits**: All sandbox subprocesses run under an explicit timeout (default: 8s). Infinite loops (`while True: pass`) are killed immediately.
4. **Path Traversal Protection**: Files written within the sandbox are checked against path traversal (`..`) attempts.
5. **No Auto-Overwrite**: Generated patches are presented as diffs and require explicit user clicking on **Approve Fix** before updating the active code editor.

---

## 📋 Limitations & Future Work

- **Multi-File Projects**: The current prototype focuses on single-module Python scripts and their corresponding Pytest test suites. Future versions will support multi-file packages and dependency graph traversal.
- **External C/Rust Extension Isolation**: Code relying on compiled C/Rust Python extensions with memory faults (e.g., segfaults) is caught as a non-zero exit code by the subprocess sandbox, but container-based isolation (Docker/gVisor) would provide an additional security boundary for multi-tenant production hosting.

