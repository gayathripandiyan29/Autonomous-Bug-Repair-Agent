"""
Streamlit Web Interface for Autonomous Bug Detection & Repair Agent.
Provides interactive code submission, traceback analysis, agent workflow visualization,
side-by-side diff comparison, test verification, approval actions, and debugging history.
"""

import streamlit as st
import pandas as pd
import json
from pathlib import Path
from typing import Optional

# Import local modules
from config import Config
from agent.workflow import AutonomousBugRepairAgent, WorkflowResult, WorkflowState
from agent.llm_client import LLMClient
from debugger.repair import DiffGenerator
from database.history import HistoryDatabase
from samples.sample_programs import SAMPLE_PROGRAMS, get_sample_list, get_sample_by_id

# Page configuration
st.set_page_config(
    page_title="Autonomous Bug Repair Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS styling for cards, pills, diff highlights, and clean typography
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.2rem;
    }
    .badge-verified {
        background-color: #DEF7EC;
        color: #03543F;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .badge-unverified {
        background-color: #FEF08A;
        color: #854D0E;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .badge-failed {
        background-color: #FDE8E8;
        color: #9B1C1C;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .metric-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
    .step-box {
        border-left: 3px solid #3B82F6;
        padding-left: 12px;
        margin-bottom: 8px;
        font-size: 0.9rem;
    }
    .code-container {
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 0.88rem;
    }
</style>
""", unsafe_allow_html=True)


# Initialize Database
db = HistoryDatabase()


# Session State Initialization
if "current_code" not in st.session_state:
    st.session_state.current_code = SAMPLE_PROGRAMS["name_error"].code
if "current_traceback" not in st.session_state:
    st.session_state.current_traceback = SAMPLE_PROGRAMS["name_error"].traceback
if "current_tests" not in st.session_state:
    st.session_state.current_tests = SAMPLE_PROGRAMS["name_error"].test_code
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "applied_code" not in st.session_state:
    st.session_state.applied_code = None
if "approved_fix" not in st.session_state:
    st.session_state.approved_fix = False


# Sidebar Configuration
with st.sidebar:
    st.title("🤖 Agent Settings")
    
    # Provider & Mode selection
    st.subheader("LLM Configuration")
    provider_options = ["Auto-Detect", "Gemini", "OpenAI-Compatible", "Local Deterministic Mode"]
    chosen_provider = st.selectbox("Intelligence Engine", provider_options, index=0)
    
    custom_gemini_key = st.text_input(
        "Gemini API Key",
        value=Config.GEMINI_API_KEY or "",
        type="password",
        help="Google Gemini API key. If empty, the agent uses local deterministic mode."
    )
    custom_openai_key = st.text_input(
        "OpenAI API Key",
        value=Config.OPENAI_API_KEY or "",
        type="password",
        help="OpenAI API key. If empty, local deterministic mode is used."
    )
    model_name = st.text_input("Model Name", value=Config.DEFAULT_MODEL_NAME)
    
    st.divider()
    st.subheader("Execution Parameters")
    max_retries = st.slider("Max Repair Iterations", min_value=1, max_value=5, value=Config.MAX_REPAIR_ITERATIONS)
    sandbox_timeout = st.slider("Sandbox Timeout (s)", min_value=2, max_value=20, value=Config.SANDBOX_TIMEOUT_SECONDS)
    auto_generate_tests = st.checkbox("Auto-generate tests if missing", value=True)

    # Active engine status badge
    st.divider()
    active_mode = "Local Deterministic Engine"
    if chosen_provider == "Gemini" and custom_gemini_key:
        active_mode = f"Gemini ({model_name})"
    elif chosen_provider == "OpenAI-Compatible" and custom_openai_key:
        active_mode = f"OpenAI ({model_name})"
    elif chosen_provider == "Auto-Detect":
        if custom_gemini_key:
            active_mode = f"Gemini ({model_name})"
        elif custom_openai_key:
            active_mode = f"OpenAI ({model_name})"

    st.info(f"**Active Mode:**\n\n{active_mode}")


# Main Content Area
st.markdown("<div class='main-header'>Autonomous Bug Detection & Repair Agent</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>AI-powered static code analysis, root cause diagnosis, isolated sandbox testing, and automated patch verification.</div>", unsafe_allow_html=True)

tabs = st.tabs(["🛠️ Debugging Workbench", "📚 Preloaded Bug Samples", "📜 Debugging History", "ℹ️ Architecture & Safety"])

# ==========================================
# TAB 1: WORKBENCH
# ==========================================
with tabs[0]:
    col_input, col_meta = st.columns([3, 2])
    
    with col_input:
        st.subheader("1. Python Code Input")
        
        # File upload option
        uploaded_file = st.file_uploader("Upload Python File (.py)", type=["py"], key="file_uploader")
        if uploaded_file is not None:
            try:
                content = uploaded_file.read().decode("utf-8")
                st.session_state.current_code = content
                st.success(f"Loaded file: {uploaded_file.name}")
            except Exception as e:
                st.error(f"Error reading file: {e}")

        # Code editor text area
        code_input = st.text_area(
            "Source Code (Edit or Paste)",
            value=st.session_state.current_code,
            height=200,
            key="code_area"
        )
        st.session_state.current_code = code_input

    with col_meta:
        st.subheader("2. Error Details & Tests")
        traceback_input = st.text_area(
            "Error Message / Traceback (Optional)",
            value=st.session_state.current_traceback,
            height=95,
            key="tb_area",
            placeholder="Paste standard Python traceback or exception message here..."
        )
        st.session_state.current_traceback = traceback_input

        test_code_input = st.text_area(
            "Pytest Test Suite (Optional)",
            value=st.session_state.current_tests,
            height=95,
            key="test_area",
            placeholder="def test_example():\n    assert solution.func() == expected"
        )
        st.session_state.current_tests = test_code_input

    # Action Button
    st.write("")
    btn_col1, btn_col2 = st.columns([1, 4])
    with btn_col1:
        analyze_clicked = st.button("🚀 Analyze & Repair Bug", type="primary", use_container_width=True)

    # Workflow Execution
    if analyze_clicked:
        st.session_state.approved_fix = False
        st.session_state.applied_code = None
        
        with st.status("Agent executing autonomous repair workflow...", expanded=True) as status_box:
            # Prepare LLM client
            prov = "local" if chosen_provider == "Local Deterministic Mode" else (
                "gemini" if (chosen_provider == "Gemini" or (chosen_provider == "Auto-Detect" and custom_gemini_key)) else (
                    "openai" if (chosen_provider == "OpenAI-Compatible" or (chosen_provider == "Auto-Detect" and custom_openai_key)) else "local"
                )
            )

            client = LLMClient(
                provider=prov,
                model_name=model_name,
                gemini_api_key=custom_gemini_key,
                openai_api_key=custom_openai_key
            )

            agent = AutonomousBugRepairAgent(
                llm_client=client,
                max_iterations=max_retries,
                sandbox_timeout=sandbox_timeout
            )

            result: WorkflowResult = agent.run(
                code=st.session_state.current_code,
                traceback_text=st.session_state.current_traceback,
                test_code=st.session_state.current_tests,
                auto_generate_tests=auto_generate_tests
            )
            st.session_state.last_result = result

            # Save session to SQLite
            summary_text = result.root_cause.get("root_cause_explanation", "Autonomous analysis complete.")
            tests_passed = result.test_comparison.after.passed if result.test_comparison else 0
            tests_total = result.test_comparison.after.total if result.test_comparison else 0

            db.save_session(
                bug_category=result.bug_category,
                original_code=st.session_state.current_code,
                repair_status=result.status,
                is_verified=result.is_verified,
                iterations_used=result.iterations_used,
                execution_time_ms=result.execution_time_ms,
                summary=summary_text,
                tests_passed=tests_passed,
                tests_total=tests_total,
                proposed_diff=result.applied_diff
            )

            status_box.update(label=f"Workflow finished: Status {result.status}", state="complete", expanded=False)

    # Display Workflow Results
    res: Optional[WorkflowResult] = st.session_state.last_result
    if res:
        st.divider()
        st.subheader("3. Autonomous Agent Findings & Repair Plan")

        # Status Banner
        badge_html = ""
        if res.status == "VERIFIED_SUCCESS":
            badge_html = "<span class='badge-verified'>✅ FIX VERIFIED BY PASSING TESTS</span>"
        elif res.status == "PROPOSED_UNVERIFIED":
            badge_html = "<span class='badge-unverified'>⚠️ PROPOSED FIX (Syntactically Valid, No Test Suite Provided)</span>"
        else:
            badge_html = "<span class='badge-failed'>❌ UNRESOLVED (Tests failed within retry limit)</span>"

        st.markdown(f"### Status: {badge_html}", unsafe_allow_html=True)
        st.caption(f"Category: **{res.bug_category}** | Iterations used: **{res.iterations_used}/{res.max_iterations}** | Total time: **{res.execution_time_ms} ms**")

        # Root Cause Analysis Box
        with st.expander("🔍 Root Cause Analysis & Reasoning", expanded=True):
            rc = res.root_cause
            rc_col1, rc_col2 = st.columns(2)
            with rc_col1:
                st.markdown(f"**Likely Cause:**\n\n{rc.get('root_cause_explanation', 'N/A')}")
                if rc.get("offending_line_number"):
                    st.markdown(f"**Location:** Line {rc.get('offending_line_number')}")
            with rc_col2:
                st.markdown(f"**Expected Behavior:**\n\n{rc.get('expected_behavior', 'N/A')}")
                st.markdown(f"**Actual Behavior:**\n\n{rc.get('actual_behavior', 'N/A')}")
            if rc.get("repair_strategy"):
                st.info(f"**Proposed Repair Strategy:** {rc.get('repair_strategy')}")

        # Test Results Comparison
        if res.test_comparison:
            comp = res.test_comparison
            with st.expander("🧪 Sandbox Test Results (Before vs After)", expanded=True):
                st.write(f"**Summary:** {comp.summary}")
                t_col1, t_col2 = st.columns(2)
                with t_col1:
                    st.markdown("#### Baseline Test Run (Before Fix)")
                    st.metric("Passed Tests", f"{comp.before.passed} / {comp.before.total}")
                    st.metric("Failed / Errors", f"{comp.before.failed + comp.before.errors}")
                with t_col2:
                    st.markdown("#### Patched Test Run (After Fix)")
                    st.metric("Passed Tests", f"{comp.after.passed} / {comp.after.total}", delta=comp.after.passed - comp.before.passed)
                    st.metric("Failed / Errors", f"{comp.after.failed + comp.after.errors}", delta=-(comp.before.failed - comp.after.failed))

        # Code Diff and Proposal
        if res.repair_patch and res.repaired_code:
            st.subheader("4. Proposed Code Patch")
            diff_tab1, diff_tab2 = st.tabs(["Side-by-Side Comparison", "Unified Diff View"])
            
            with diff_tab1:
                col_orig, col_mod = st.columns(2)
                with col_orig:
                    st.markdown("**Original Code**")
                    st.code(res.original_code, language="python", line_numbers=True)
                with col_mod:
                    st.markdown("**Repaired Code**")
                    st.code(res.repaired_code, language="python", line_numbers=True)

            with diff_tab2:
                st.code(res.applied_diff or "No changes detected.", language="diff")

            # Explanation of changes
            if res.repair_patch.explanation:
                st.markdown(f"**Explanation:** {res.repair_patch.explanation}")
            if res.repair_patch.changes_made:
                st.markdown("**Changes Made:**")
                for ch in res.repair_patch.changes_made:
                    st.markdown(f"- {ch}")

            # Safety and Approval Actions
            st.write("")
            act_col1, act_col2, act_col3 = st.columns([1.5, 1.5, 2])
            
            with act_col1:
                if st.button("✅ Approve Fix & Apply to Workspace", type="primary", use_container_width=True):
                    st.session_state.approved_fix = True
                    st.session_state.current_code = res.repaired_code
                    st.success("Fix explicitly approved and loaded into current workbench!")
                    st.rerun()

            with act_col2:
                st.download_button(
                    label="💾 Download Repaired Code (.py)",
                    data=res.repaired_code,
                    file_name="repaired_solution.py",
                    mime="text/x-python",
                    use_container_width=True
                )

            with act_col3:
                if st.button("🔄 Rollback to Original Code", use_container_width=True):
                    st.session_state.current_code = res.original_code
                    st.session_state.last_result = None
                    st.info("Rolled back to initial code state.")
                    st.rerun()

        # Agent Workflow Steps Log
        with st.expander("📋 Detailed Agent Workflow Log & Tool Calls", expanded=False):
            for step in res.workflow_steps:
                st.markdown(f"**Step {step.step_number} [{step.state}]** ({step.elapsed_ms} ms)")
                st.write(step.description)
                if step.tool_called:
                    st.caption(f"🔧 Invoked Tool: `{step.tool_called}`")
                    if step.tool_output:
                        with st.expander(f"Output of {step.tool_called}", expanded=False):
                            st.json(step.tool_output)
                st.divider()


# ==========================================
# TAB 2: PRELOADED SAMPLES
# ==========================================
with tabs[1]:
    st.subheader("Curated Buggy Sample Programs")
    st.markdown("Select an educational sample program to test the autonomous agent's capabilities across error types.")

    sample_list = get_sample_list()
    sample_titles = [f"{s.title} ({s.category})" for s in sample_list]
    selected_idx = st.selectbox("Choose Sample Program", range(len(sample_list)), format_func=lambda i: sample_titles[i])
    selected_sample = sample_list[selected_idx]

    st.markdown(f"**Description:** {selected_sample.description}")
    st.info(f"**Expected Fix:** {selected_sample.expected_fix_summary}")

    samp_col1, samp_col2 = st.columns(2)
    with samp_col1:
        st.markdown("**Buggy Python Source Code:**")
        st.code(selected_sample.code, language="python")
    with samp_col2:
        st.markdown("**Associated Pytest Test Suite:**")
        st.code(selected_sample.test_code, language="python")

    if st.button("📥 Load Selected Sample into Workbench", type="primary"):
        st.session_state.current_code = selected_sample.code
        st.session_state.current_traceback = selected_sample.traceback
        st.session_state.current_tests = selected_sample.test_code
        st.session_state.last_result = None
        st.success(f"Loaded '{selected_sample.title}' into Workbench! Switch to Tab 1 to run.")


# ==========================================
# TAB 3: DEBUGGING HISTORY
# ==========================================
with tabs[2]:
    st.subheader("Historical Debugging Sessions (SQLite)")
    stats = db.get_statistics()
    
    # Stats overview
    st_col1, st_col2, st_col3 = st.columns(3)
    st_col1.metric("Total Sessions", stats["total_sessions"])
    st_col2.metric("Verified Repairs", stats["verified_repairs"])
    st_col3.metric("Fix Rate", f"{stats['success_rate_percent']}%")

    st.write("")
    filter_col1, filter_col2, filter_col3 = st.columns([2, 2, 1])
    with filter_col1:
        cat_filter = st.selectbox("Filter Category", ["All", "NameError", "SyntaxError", "IndexError", "LogicalError", "TypeError"])
    with filter_col2:
        stat_filter = st.selectbox("Filter Status", ["All", "VERIFIED_SUCCESS", "PROPOSED_UNVERIFIED", "UNRESOLVED"])
    with filter_col3:
        st.write("")
        if st.button("🗑️ Clear History", use_container_width=True):
            db.clear_history()
            st.success("Cleared debugging history database.")
            st.rerun()

    sessions = db.search_sessions(category=cat_filter, status=stat_filter)
    if sessions:
        df = pd.DataFrame(sessions)
        display_df = df[["id", "timestamp", "bug_category", "repair_status", "is_verified", "iterations_used", "execution_time_ms", "summary"]]
        st.dataframe(display_df, use_container_width=True)

        st.subheader("Inspect Historical Session")
        selected_id = st.selectbox("Select Session ID to view diff", df["id"].tolist())
        sess_record = db.get_session_by_id(selected_id)
        if sess_record and sess_record.get("proposed_diff"):
            st.markdown(f"**Summary:** {sess_record.get('summary')}")
            st.code(sess_record["proposed_diff"], language="diff")
    else:
        st.info("No debugging sessions recorded yet. Run a repair in Tab 1 to record history!")


# ==========================================
# TAB 4: ARCHITECTURE & SAFETY
# ==========================================
with tabs[3]:
    st.subheader("System Architecture & Safety Isolation")
    st.markdown("""
### Safety Isolation Model
- **No In-Process Execution**: Code submitted by users or suggested by the agent is never executed in the host Streamlit process.
- **Isolated Subprocess Sandbox**: All code is executed in dedicated temporary directories created via `tempfile.mkdtemp()`.
- **Environment Sanitization**: API keys, credentials, and authentication tokens are actively stripped from the child process environment before execution.
- **Execution Timeouts**: Subprocesses are bound to a strict timeout (default: 8s) to neutralize infinite loops (`while True: pass`).
- **Git Version Tracking & Clean Rollback**: Temporary Git repositories snapshot the initial baseline code. If a candidate patch fails test assertions, Git rolls back to baseline cleanly before attempting the next iteration.
- **Explicit User Approval**: Proposed patches never overwrite user files automatically. Patches require explicit user review and approval.
    """)

    st.divider()
    st.markdown("""
### Agent Workflow Architecture
1. **Input Inspection**: User code AST is analyzed using Python's `ast` module.
2. **Traceback Parsing**: Regex-guided parsing extracts error types, line numbers, and stack traces.
3. **Root Cause Analysis**: LLM or local deterministic rule engine infers root causes and expected vs actual behavior.
4. **Patch Proposal**: Candidate fix is drafted and verified for valid Python grammar using `ast.parse()`.
5. **Sandbox Pytest Verification**: Pytest runs in the isolated sandbox, testing against assertions.
6. **Iterative Repair Loop**: If tests fail, failure messages are fed back into the agent for up to $N$ iterations.
7. **Verified Delivery**: Clear distinction between fixes verified by tests vs unverified proposals.
    """)

