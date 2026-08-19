"""
CommerceOps AI — Chat Console (NorthPeak Web Support).
"""
import streamlit as st

from api_client import (
    get_response,
    get_status,
    new_session_id,
    stream_status_events,
    submit_chat,
)
from style import header, inject, status_pill

st.set_page_config(
    page_title="NorthPeak | Customer Assistant",
    page_icon="🏔️",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject()

# FIRST PAGE HEADER: Includes brand prefix "NORTHPEAK · CUSTOMER ASSISTANT"
header(
    "CUSTOMER ASSISTANT",
    "Direct Support · Orders, Returns, Policy & Analytics · Managed by NorthPeak Supervisor Orchestrator",
    is_first_page=True,
)

NODE_LABELS = {
    "input_guard": "Screening message (NeMo Guardrails)",
    "pii_redact": "Redacting PII & cost queries (Presidio)",
    "intent_router": "Classifying intent (Lightweight Router)",
    "support_crew": "Processing support ticket (CrewAI)",
    "knowledge_agent": "Searching NorthPeak policy library & knowledge graph",
    "merchandising_agent": "Querying inventory & sales metrics",
    "market_intel_agent": "Analyzing market trends",
    "off_topic": "Off-topic query detected",
    "assemble_response": "Validating output safety (Guardrails AI)",
    "human_approval_gate": "Paused at Human Approval Gate",
    "finalize": "Finalizing output",
}

CUSTOMERS = {
    "CUST-001": "Jamie Rivera",
    "CUST-002": "Alex Chen",
    "CUST-003": "Morgan Ellis",
}

# --- NORTHPEAK E-COMMERCE SIDEBAR ---
with st.sidebar:
    st.markdown("### Active Customer Session")
    customer_id = st.selectbox(
        "Select Customer Account",
        options=list(CUSTOMERS.keys()),
        format_func=lambda c: f"{c} — {CUSTOMERS[c]}",
    )
    order_id = st.text_input("Active Order ID Context", value="NP-88213")

    st.divider()

    st.markdown("### Quick Inquiry Chips")

    sample_prompts = [
        "Where is my order NP-88213?",
        "I'd like a $340 refund for order NP-77410, it arrived damaged.",
        "What is your return policy on worn Denali hiking boots?",
        "Which SKUs have been returned more than once this month?",
    ]

    for p in sample_prompts:
        if st.button(p, key=f"btn_{hash(p)}", use_container_width=True):
            st.session_state["preset_message"] = p

# --- CHAT HISTORY RENDER ---
if "coa_chat_history" not in st.session_state:
    st.session_state.coa_chat_history = []

for turn in st.session_state.coa_chat_history:
    avatar_icon = "👤" if turn["role"] == "user" else "✨"
    with st.chat_message(turn["role"], avatar=avatar_icon):
        st.markdown(turn["content"])

default_input = st.session_state.pop("preset_message", "")
message = st.chat_input("Ask NorthPeak Assistant about orders, returns, or policies...")
active_prompt = message or default_input

if active_prompt:
    st.session_state.coa_chat_history.append({"role": "user", "content": active_prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(active_prompt)

    session_id = new_session_id()
    submit_chat(active_prompt, session_id, customer_id, order_id)

    with st.chat_message("assistant", avatar="✨"):
        status_box = st.container()
        
        with status_box:
            progress_bar = st.progress(0)
            status_line = st.empty()
            node_log = st.expander("Supervisor Routing Trace", expanded=False)
            seen_nodes = []

            for event in stream_status_events(session_id):
                pct = event.get("progress_pct", 0)
                node = event.get("current_node")
                status = event.get("status")

                progress_bar.progress(min(pct, 100) / 100)
                status_line.markdown(
                    f"{status_pill(status)} &nbsp;·&nbsp; <small style='color:#8C8581;'>Node: {node or 'initializing'}</small>",
                    unsafe_allow_html=True,
                )

                if node and node not in seen_nodes:
                    seen_nodes.append(node)
                    with node_log:
                        st.caption(f"✓ {NODE_LABELS.get(node, node)}")

                if status in ("completed", "failed", "rejected"):
                    break
                    
                if status == "awaiting_approval":
                    st.warning(
                        "⚠️ **Human Review Gate:** This request exceeds auto-approval limits "
                        "and has been routed to our Operations Team for manual approval."
                    )
                    break

        progress_bar.empty()

        final = get_status(session_id)
        if final["status"] == "completed":
            resp = get_response(session_id)
            answer = resp["final_response_text"] if resp else "(No response generated)"
            st.markdown(answer)
            st.session_state.coa_chat_history.append({"role": "assistant", "content": answer})

        elif final["status"] == "rejected":
            error_msg = final.get('error', 'Guardrail policy enforcement.')
            st.error(f"🛡️ **Security Rail Enforcement:** {error_msg}")
            st.session_state.coa_chat_history.append(
                {"role": "assistant", "content": f"🛡️ **Security Rail Enforcement:** {error_msg}"}
            )

        elif final["status"] == "awaiting_approval":
            st.session_state.coa_chat_history.append(
                {"role": "assistant", "content": "⏳ *Routed to Approval Queue — awaiting staff sign-off.*"}
            )

    st.session_state["last_session_id"] = session_id

if "last_session_id" in st.session_state:
    st.markdown(
        f"<div style='text-align: right; color: #8C8581; font-size: 0.75rem; margin-top: 1rem;'>"
        f"Active Session ID: <code>{st.session_state['last_session_id']}</code></div>",
        unsafe_allow_html=True,
    )