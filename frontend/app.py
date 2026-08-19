"""
NorthPeak Retail — Brand Landing & Operational Overview.
Introduces NorthPeak Retail and provides direct access to the AI Chat Console.
"""
import streamlit as st
from style import header, inject

st.set_page_config(
    page_title="NorthPeak Retail | Intelligence Platform",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject()

# Brand Header Banner (First Page Brand Prefix Active)
header(
    "RETAIL INTELLIGENCE PLATFORM",
    "Precision Performance Outdoor Gear · Autonomous Support & Analytics Engine",
    is_first_page=True,
)

# --- SECTION 1: BRAND BACKGROUND & HERO INTRO ---
st.markdown(
    """
    <div class="coa-card" style="text-align: center; padding: 2.5rem 2rem; margin-bottom: 2rem;">
        <h2 style="font-size: 1.8rem; font-weight: 300; margin-bottom: 1rem; letter-spacing: 0.05em;">
            ENGINEERED FOR THE WILD. POWERED BY INTELLIGENCE.
        </h2>
        <p style="max-width: 750px; margin: 0 auto; line-height: 1.6; font-size: 0.95rem;">
            Founded in the Pacific Northwest, <b>NorthPeak Retail</b> crafts elite technical apparel and mountain equipment built to withstand extreme conditions. 
            This portal integrates our autonomous <b>Supervisor AI Agent</b> to deliver real-time order tracking, policy intelligence, and merchandising analytics for both our valued outdoor community and internal retail operations.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- SECTION 2: WHAT THIS PLATFORM PROVIDES ---
st.markdown("<h3 style='font-weight: 400; text-align: center; margin-bottom: 1.5rem;'>Platform Capabilities</h3>", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3, gap="medium")

with col1:
    st.markdown(
        """
        <div class="coa-card" style="height: 100%;">
            <div style="font-size: 1.8rem; margin-bottom: 0.5rem;">🎒</div>
            <h4 style="margin-bottom: 0.5rem;">Customer Care Assistant</h4>
            <p style="font-size: 0.85rem; line-height: 1.5;">
                Instant status updates for orders, shipments, returns processing, and automated policy guidance grounded in NorthPeak knowledge graphs.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        """
        <div class="coa-card" style="height: 100%;">
            <div style="font-size: 1.8rem; margin-bottom: 0.5rem;">📊</div>
            <h4 style="margin-bottom: 0.5rem;">Merchandising & Inventory</h4>
            <p style="font-size: 0.85rem; line-height: 1.5;">
                Real-time reporting on SKU sales velocity, stock allocations across fulfillment centers, and catalog margin insights.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        """
        <div class="coa-card" style="height: 100%;">
            <div style="font-size: 1.8rem; margin-bottom: 0.5rem;">🛡️</div>
            <h4 style="margin-bottom: 0.5rem;">Secure HITL Operations</h4>
            <p style="font-size: 0.85rem; line-height: 1.5;">
                Enterprise-grade security featuring Human-in-the-Loop review gates for high-value refunds and NeMo prompt guardrails.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# --- SECTION 3: CALL TO ACTION (CTA) BAR ---
st.markdown(
    """
    <div class="coa-card" style="text-align: center; padding: 2rem; background: linear-gradient(180deg, #FFFFFF 0%, #F7F3EE 100%);">
        <h3 style="margin-bottom: 0.5rem; font-weight: 400;">Ready to get started?</h3>
        <p style="margin-bottom: 1.5rem; font-size: 0.9rem;">
            Ask about your order status, explore product return policies, or query inventory analytics with our NorthPeak AI Assistant.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Centered Navigation Button to Chat Console
btn_col1, btn_col2, btn_col3 = st.columns([1, 2, 1])
with btn_col2:
    if st.button("✨ Launch Customer Assistant", use_container_width=True):
        st.switch_page("pages/1_Chat_Console.py")