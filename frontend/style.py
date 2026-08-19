"""
NorthPeak Retail — Aesthetic Minimalist Web Identity.
Inspired by modern luxury storefront designs (Assemble palette).
"""
import streamlit as st

# Assemble Aesthetic Warm Palette
BG_HERO = "#D8C4BC"            # Warm dusty blush top accent
BG_CANVAS = "#FDFBF7"          # Warm alabaster main canvas
BG_SURFACE = "#FFFFFF"         # Soft white containers
TEXT_MAIN = "#333130"          # Dark charcoal (instead of harsh black)
TEXT_MUTED = "#8C8581"         # Warm taupe caption text
ACCENT_DARK = "#4A4543"        # Deep slate taupe for buttons

STATUS_COLORS = {
    "completed": "#5B7C61",
    "running": "#8A9A86",
    "queued": TEXT_MUTED,
    "awaiting_approval": "#C89D66",
    "failed": "#A8524B",
    "rejected": "#A8524B",
}


def inject() -> None:
    """Injects the global Assemble minimalist CSS into the Streamlit session."""
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

        /* Global Page Background */
        html, body, [data-testid="stAppViewContainer"], .main {{
            background-color: {BG_CANVAS} !important;
            color: {TEXT_MAIN} !important;
            font-family: 'Inter', -apple-system, sans-serif;
        }}

        header[data-testid="stHeader"] {{
            background-color: rgba(253, 251, 247, 0.8) !important;
            backdrop-filter: blur(8px);
        }}

        /* Sidebar Minimalist Design */
        [data-testid="stSidebar"] {{
            background-color: #F7F3EE !important;
            border-right: 1px solid #EBE5DF !important;
        }}
        [data-testid="stSidebar"] * {{
            color: {TEXT_MAIN} !important;
        }}

        /* Hero / Header Section Styled Like "ASSEMBLE" Banner */
        .assemble-hero {{
            background: linear-gradient(180deg, {BG_HERO} 0%, #E3D5CD 100%);
            border-radius: 16px;
            padding: 3.5rem 2rem;
            text-align: center;
            margin-bottom: 2rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.03);
        }}
        .assemble-hero h1 {{
            color: #FFFFFF !important;
            font-size: 2.8rem !important;
            font-weight: 300 !important;
            letter-spacing: 0.18em !important;
            text-transform: uppercase;
            margin: 0 0 0.5rem 0 !important;
        }}
        .assemble-hero p {{
            color: rgba(255, 255, 255, 0.9) !important;
            font-size: 0.95rem !important;
            font-weight: 300;
            letter-spacing: 0.04em;
            margin: 0 !important;
        }}

        /* Clean Card Layouts */
        .coa-card {{
            background: {BG_SURFACE};
            border: 1px solid #EBE5DF;
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02);
            margin-bottom: 1.25rem;
        }}
        .coa-card h1, .coa-card h2, .coa-card h3, .coa-card h4 {{
            color: {TEXT_MAIN} !important;
            font-weight: 500;
            letter-spacing: -0.01em;
        }}
        .coa-card p {{
            color: {TEXT_MUTED} !important;
        }}

        /* Chat Messages Container */
        [data-testid="stChatMessage"] {{
            background-color: {BG_SURFACE} !important;
            border: 1px solid #EBE5DF !important;
            border-radius: 12px !important;
            padding: 1.2rem !important;
            margin-bottom: 0.85rem !important;
            box-shadow: 0 2px 6px rgba(0,0,0,0.015) !important;
        }}

        /* Bottom Fixed Chat Bar */
        [data-testid="stBottom"], [data-testid="stBottom"] > div {{
            background-color: {BG_CANVAS} !important;
        }}
        [data-testid="stChatInput"] {{
            background-color: {BG_SURFACE} !important;
            border: 1px solid #E2DCD5 !important;
            border-radius: 8px !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.03) !important;
        }}
        [data-testid="stChatInput"]:focus-within {{
            border-color: {ACCENT_DARK} !important;
        }}

        /* Minimalist Buttons */
        div.stButton > button {{
            background-color: {BG_SURFACE} !important;
            color: {TEXT_MAIN} !important;
            border: 1px solid #E2DCD5 !important;
            border-radius: 6px !important;
            font-size: 0.82rem !important;
            font-weight: 400 !important;
            letter-spacing: 0.02em !important;
            padding: 0.5rem 1rem !important;
            transition: all 0.2s ease !important;
        }}
        div.stButton > button:hover {{
            background-color: {ACCENT_DARK} !important;
            color: #FFFFFF !important;
            border-color: {ACCENT_DARK} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def header(title: str, subtitle: str = "", is_first_page: bool = False) -> None:
    """
    Renders an 'Assemble' styled aesthetic hero banner.
    If is_first_page is True, it prefixes with the brand name 'NORTHPEAK'.
    Sub-pages render only their functional page title.
    """
    display_title = f"NORTHPEAK · {title}" if is_first_page else title
    st.markdown(
        f"""
        <div class="assemble-hero">
            <h1>{display_title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value: str) -> None:
    """Renders a minimalist KPI tile."""
    st.markdown(
        f"""
        <div class="coa-card">
            <div style="font-size: 2.2rem; font-weight: 300; color: {TEXT_MAIN}; line-height: 1.1;">{value}</div>
            <div style="font-size: 0.72rem; color: {TEXT_MUTED}; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 500; margin-top: 0.4rem;">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_pill(status: str) -> str:
    """Returns an inline pill indicator for execution statuses."""
    color = STATUS_COLORS.get(status, TEXT_MUTED)
    formatted = status.replace("_", " ").title()
    return f'<span style="background:{color}18; color:{color}; border:1px solid {color}30; padding:3px 10px; border-radius:4px; font-size:0.75rem; font-weight:500; letter-spacing:0.03em;">● {formatted}</span>'