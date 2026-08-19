"""
CommerceOps AI — Market Intelligence.
Autonomous competitive research and pricing synthesis.
"""
import streamlit as st

from api_client import (
    get_response,
    get_status,
    new_session_id,
    stream_status_events,
    submit_chat,
)
from style import header, inject

st.set_page_config(
    page_title="Market Intelligence",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject()

# SUB-PAGE HEADER: Clean title without brand prefix
header(
    "MARKET INTELLIGENCE",
    "Competitive research, market trend analysis, and pricing synthesis",
    is_first_page=False,
)

with st.sidebar:
    st.markdown("### Example Topics")
    
    research_prompts = [
        "Summarize competitor pricing trends in outdoor apparel this quarter.",
        "How does hiking boot pricing compare across major outdoor brands?",
    ]
    
    for rp in research_prompts:
        if st.button(rp, key=f"intel_{hash(rp)}", use_container_width=True):
            st.session_state["intel_input"] = rp

default_intel = st.session_state.pop("intel_input", "")
query = st.chat_input("Request competitive intelligence or market analysis...")
active_intel = query or default_intel

if active_intel:
    with st.chat_message("user", avatar="👤"):
        st.markdown(active_intel)

    session_id = new_session_id()
    submit_chat(active_intel, session_id, customer_id="STAFF-MARKETING")

    with st.chat_message("assistant", avatar="🌐"):
        progress_bar = st.progress(0)
        status_box = st.empty()

        for event in stream_status_events(session_id):
            pct = min(event.get("progress_pct", 0), 100)
            progress_bar.progress(pct / 100)
            status_box.caption(f"Analyzing market data... Node: `{event.get('current_node', 'planning')}`")
            
            if event.get("status") in ("completed", "failed", "rejected"):
                break

        progress_bar.empty()
        status_box.empty()

        final = get_status(session_id)
        if final["status"] == "completed":
            resp = get_response(session_id)
            st.markdown(resp["final_response_text"] if resp else "(No report text generated)")
        else:
            st.error(f"**Research Error:** Status `{final['status']}` — {final.get('error', 'Execution interrupted.')}")