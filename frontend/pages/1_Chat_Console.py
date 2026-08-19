"""
CommerceOps AI — Chat Console.

Internal tool: a NorthPeak employee (support, merchandising, or
operations staff) types a request on behalf of a customer, or asks an
internal question directly. The Supervisor Orchestrator classifies
intent and routes to the right agent automatically — the employee
never picks which agent handles it, they just describe what they need.
"""
import streamlit as st

from api_client import get_response, get_status, new_session_id, stream_status_events, submit_chat
from style import header, inject, status_pill

st.set_page_config(page_title="CommerceOps AI | Chat Console", page_icon="💬", layout="wide")
inject()
header(
    " Chat Console — NorthPeak Employee Tool",
    "For support, merchandising, and operations staff. Look up an order, process a refund, "
    "check a policy, or ask an internal question — the Supervisor routes it automatically.",
)

NODE_LABELS = {
    "input_guard": "Screening input (NeMo Guardrails)",
    "pii_redact": "Redacting PII & checking for cost-data requests (Presidio)",
    "intent_router": "Classifying intent (lightweight classifier)",
    "support_crew": "Support Triage Crew working (CrewAI)",
    "knowledge_agent": "Knowledge Agent searching policy docs / knowledge graph",
    "merchandising_agent": "Merchandising Analytics Agent querying sales data",
    "market_intel_agent": "Market Intelligence Agent researching (plan → research → reflect)",
    "off_topic": "Off-topic — declining politely",
    "assemble_response": "Validating output (Guardrails AI)",
    "human_approval_gate": "Awaiting human approval",
    "finalize": "Finalizing response",
}

CUSTOMERS = {
    "CUST-001": "Jamie Rivera", "CUST-002": "Alex Chen", "CUST-003": "Morgan Ellis",
    "CUST-004": "Sam Patel", "CUST-005": "Taylor Brooks", "CUST-006": "Casey Kim",
}

with st.sidebar:
    st.markdown("### 👤 Active Persona")
    st.selectbox(
        "Select Demo Role:",
        [
            "Operations Manager (Full Access)",
            "Tier 1 Support Specialist",
            "Merchandising Analyst",
        ],
        key="user_role",
    )
    st.divider()

    st.markdown("### You're signed in as")
    employee_name = st.text_input(
        "Your name", value=st.session_state.get("coa_employee_name", ""),
        placeholder="e.g. Priya Shah", key="employee_name_input",
    )
    st.session_state["coa_employee_name"] = employee_name
    st.divider()
    st.markdown("### Looking up")
    customer_id = st.selectbox(
        "Customer", options=list(CUSTOMERS.keys()), format_func=lambda c: f"{c} — {CUSTOMERS[c]}"
    )
    order_id = st.text_input("Order ID (optional context)", placeholder="e.g. NP-88213")
    st.divider()
    st.markdown("### Try asking")
    st.code("Where is order NP-88213 for customer CUST-001?", language="text")
    st.code("Process a $340 refund for order NP-77410 (CUST-002) — arrived damaged.", language="text")
    st.code("What's our return policy on worn hiking boots?", language="text")
    st.code("Which customers have returned SKU-88213 more than once?", language="text")
    st.code("What's our escalation procedure for a customer threatening a chargeback?", language="text")
    st.code("What fulfillment center ships to EU addresses and what carrier do they use?", language="text")

if "coa_chat_history" not in st.session_state:
    st.session_state.coa_chat_history = []

for turn in st.session_state.coa_chat_history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])

message = st.chat_input("Ask about an order, refund, billing, policy, analytics, or market trends...")

if message and not employee_name:
    st.error("Enter your name in the sidebar before submitting a request — every action here is logged against an employee.")
elif message:
    st.session_state.coa_chat_history.append({"role": "user", "content": message})
    with st.chat_message("user"):
        st.markdown(message)

    session_id = new_session_id()
    submit_chat(message, session_id, employee_name, customer_id, order_id)

    with st.chat_message("assistant"):
        progress_bar = st.progress(0)
        status_line = st.empty()
        node_log = st.container()
        seen_nodes = []

        for event in stream_status_events(session_id):
            pct = event.get("progress_pct", 0)
            node = event.get("current_node")
            status = event.get("status")
            progress_bar.progress(min(pct, 100) / 100)
            status_line.markdown(f"{status_pill(status)}  ·  `{node or '—'}`", unsafe_allow_html=True)

            if node and node not in seen_nodes:
                seen_nodes.append(node)
                with node_log:
                    st.caption(f"✅ {NODE_LABELS.get(node, node)}")

            if status in ("completed", "failed", "rejected"):
                break
            if status == "awaiting_approval":
                st.warning(
                    "⚠️ This request exceeds the auto-approval threshold and has been routed to the "
                    "**Approval Queue** for manager sign-off. It will resume automatically once decided."
                )
                break

        final = get_status(session_id)
        if final["status"] in ("completed",):
            resp = get_response(session_id)
            answer = resp["final_response_text"] if resp else "(no response text)"
            st.markdown("---")
            st.markdown(answer)
            st.session_state.coa_chat_history.append({"role": "assistant", "content": answer})
        elif final["status"] == "rejected":
            st.error(f"Request blocked: {final.get('error', 'guardrail rejection')}")
            st.session_state.coa_chat_history.append(
                {"role": "assistant", "content": f"🚫 Blocked: {final.get('error', '')}"}
            )
        elif final["status"] == "failed":
            st.error(f"Something went wrong: {final.get('error', 'unknown error')}")
        elif final["status"] == "awaiting_approval":
            st.session_state.coa_chat_history.append(
                {"role": "assistant", "content": "⏳ Routed to the Approval Queue — awaiting manager sign-off."}
            )

    st.session_state["last_session_id"] = session_id

if "last_session_id" in st.session_state:
    st.caption(f"Last session ID: `{st.session_state['last_session_id']}`  ·  Logged under: `{employee_name or '—'}`")