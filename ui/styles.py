import streamlit as st
# Text sizes of the whole app. 1 rem = 16 px. Change these numbers to make the text bigger or smaller.
BASE_FONT_REM = 1.05       # normal text
SMALL_FONT_REM = 0.95      # captions, small notes
LABEL_FONT_REM = 1.0       # field labels, buttons, radio / select text
METRIC_FONT_REM = 2.0      # big numbers (cart total, order counts)

def apply_styles():
    """One place for the text sizes, so every page looks the same."""
    st.markdown(f"""<style>
html, body, .stApp {{ font-size: {BASE_FONT_REM}rem; }}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {{ font-size: {BASE_FONT_REM}rem; line-height: 1.6; }}
[data-testid="stCaptionContainer"] p {{ font-size: {SMALL_FONT_REM}rem !important; }}
[data-testid="stWidgetLabel"] p, label p, .stButton button p, .stDownloadButton button p, [data-testid="stRadio"] label p,
input, textarea, [data-baseweb="select"] {{ font-size: {LABEL_FONT_REM}rem !important; }}
[data-testid="stMetricValue"] {{ font-size: {METRIC_FONT_REM}rem; }}
[data-testid="stMetricLabel"] p {{ font-size: {LABEL_FONT_REM}rem; }}
.stButton button, .stDownloadButton button {{ min-height: 2.6rem; }}
@media (max-width: 640px) {{ html, body, .stApp {{ font-size: 1rem; }} h1 {{ font-size: 1.8rem !important; }}
  h2 {{ font-size: 1.45rem !important; }} h3 {{ font-size: 1.2rem !important; }} }}
</style>""", unsafe_allow_html=True)
