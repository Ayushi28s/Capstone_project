import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import get_guardrail_events, health, list_sessions
from style import STATUS_COLORS, header, inject

st.set_page_config(
    page_title="NorthPeak Retail Employee Portal",
    page_icon="🏔️",
    layout="wide",
)
inject()

# --- CUSTOM CSS FOR CLEAN CARDS & ALIGNMENT ---
st.markdown(
    """
    <style>
    /* Vertical centering for column blocks */
    div[data-testid="stColumn"] {
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .profile-heading {
        font-size: 1.25rem;
        font-weight: 700;
        color: #0f172a;
        margin: 0;
        padding: 0;
        line-height: 1.2;
    }
    .profile-sub {
        font-size: 0.95rem;
        color: #334155;
        margin: 0;
        padding: 0;
        line-height: 1.2;
    }
    .portal-tile-white {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        min-height: 150px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        margin-bottom: 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.03);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .portal-tile-white:hover {
        border-color: #cbd5e1;
        box-shadow: 0 4px 12px rgba(0,0,0,0.06);
    }
    .tile-title-clean {
        font-size: 1.15rem;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 6px;
    }
    .tile-desc-clean {
        font-size: 0.875rem;
        color: #64748b;
        line-height: 1.4;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- INITIALIZE SESSION STATE DEFAULTS ---
if "user_role" not in st.session_state:
    st.session_state["user_role"] = None
if "coa_employee_name" not in st.session_state:
    st.session_state["coa_employee_name"] = None
if "profile_initialized" not in st.session_state:
    st.session_state["profile_initialized"] = False

# --- ONBOARDING POP-UP (MODAL) ---
@st.dialog("Welcome to NorthPeak Employee Portal")
def initialize_user_modal():
    st.write("Please enter your name and select your role.")
    
    name_input = st.text_input(
        "Full Name:",
        value=st.session_state.get("coa_employee_name") or "",
        placeholder="Enter your full name...",
    )
    
    role_options = [
        "Operations Manager (Full Access)",
        "Tier 1 Support Specialist",
        "Merchandising Analyst",
    ]
    
    current_role = st.session_state.get("user_role")
    default_index = role_options.index(current_role) if current_role in role_options else 0
    
    role_input = st.selectbox(
        "Select Your Role / Persona:",
        options=role_options,
        index=default_index,
    )
    
    if st.button("Continue to Portal", use_container_width=True, type="primary"):
        if not name_input.strip():
            st.error("Please enter your name to proceed.")
        else:
            st.session_state["coa_employee_name"] = name_input.strip()
            st.session_state["user_role"] = role_input
            st.session_state["profile_initialized"] = True
            st.rerun()

# Trigger modal if identity hasn't been set yet
if not st.session_state["profile_initialized"]:
    initialize_user_modal()

# Check API Health
try:
    api_status = health()
    api_ok = True
except Exception:
    api_status = {}
    api_ok = False

# --- MAIN PORTAL HEADER ---
header(
    "🏔️ NorthPeak Retail Employee Portal",
    "Central internal operations hub for support, merchandising, analytics, and workflow management.",
)

if not api_ok:
    st.error("⚠️ Cannot reach CommerceOps AI API. Ensure the backend server (`uvicorn app.main:app`) is running.")

# --- ACTIVE PROFILE BAR (CENTERED CONTAINER) ---
with st.container(border=True):
    col_prof1, col_prof2, col_prof3 = st.columns([2.5, 2.5, 1.2], vertical_alignment="center")

    with col_prof1:
        user_name = st.session_state.get('coa_employee_name') or "Not Set"
        st.markdown(f'<div class="profile-heading">Welcome back, {user_name}</div>', unsafe_allow_html=True)

    with col_prof2:
        active_role = st.session_state.get('user_role') or "Not Set"
        st.markdown(f'<div class="profile-sub"><b>Active Persona:</b> <code>{active_role}</code></div>', unsafe_allow_html=True)

    with col_prof3:
        if st.button("Switch Persona", use_container_width=True):
            initialize_user_modal()

st.divider()


# --- MODULE NAVIGATION GRID (5 CLEAN WHITE CARDS) ---
st.markdown("### Operational Modules")

row1_col1, row1_col2, row1_col3 = st.columns(3)

with row1_col1:
    st.markdown(
        """
        <div class="portal-tile-white">
            <div>
                <div class="tile-title-clean"> Chat Console</div>
                <div class="tile-desc-clean">Customer triage, order inquiries, policy lookups, and automated agent routing.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open Chat Console →", key="btn_chat", use_container_width=True):
        st.switch_page("pages/1_Chat_Console.py")

with row1_col2:
    st.markdown(
        """
        <div class="portal-tile-white">
            <div>
                <div class="tile-title-clean"> Approval Queue</div>
                <div class="tile-desc-clean">Manager review for high-value refund approvals and risk overrides.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open Approval Queue →", key="btn_appr", use_container_width=True):
        st.switch_page("pages/2_Approval_Queue.py")

with row1_col3:
    st.markdown(
        """
        <div class="portal-tile-white">
            <div>
                <div class="tile-title-clean"> Merchandising Analytics</div>
                <div class="tile-desc-clean">Self-serve queries for sales performance, inventory levels, and product margins.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open Merchandising →", key="btn_merch", use_container_width=True):
        st.switch_page("pages/3_Merchandising_Analytics.py")

row2_col1, row2_col2, _ = st.columns(3)

with row2_col1:
    st.markdown(
        """
        <div class="portal-tile-white">
            <div>
                <div class="tile-title-clean"> Market Intelligence</div>
                <div class="tile-desc-clean">Competitive benchmarking and trend research reports powered by Deep Agent.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open Market Intel →", key="btn_market", use_container_width=True):
        st.switch_page("pages/4_Market_Intelligence.py")

with row2_col2:
    st.markdown(
        """
        <div class="portal-tile-white">
            <div>
                <div class="tile-title-clean"> Observability</div>
                <div class="tile-desc-clean">Telemetry logs, system health metrics, NeMo guardrail events, and execution state.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open Observability →", key="btn_obs", use_container_width=True):
        st.switch_page("pages/5_Observability.py")

# --- SIDEBAR PANEL ---
with st.sidebar:
    st.markdown("## NorthPeak Portal")
    st.caption(f"API Connection: {'🟢 Online' if api_ok else '🔴 Offline'}")
    st.caption(f"Engine Model: `{api_status.get('model', '—')}`")
    st.caption(f"Environment: {api_status.get('env', '—')}")
    st.divider()
    
    if st.session_state.get("profile_initialized"):
        st.markdown(f"**Logged User:**\n`{st.session_state['coa_employee_name']}`")
        st.markdown(f"**Role Privileges:**\n`{st.session_state['user_role']}`")
    else:
        st.caption("Identity not configured.")