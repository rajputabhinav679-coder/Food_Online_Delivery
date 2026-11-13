import streamlit as st
from streamlit_cookies_manager import EncryptedCookieManager

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        cookies = EncryptedCookieManager(
            prefix="food_cafe/",
            password=st.secrets["COOKIES_PASSWORD"]
        )
        if not cookies.ready():
            st.stop()
        st.session_state.cookie_manager = cookies
    return st.session_state.cookie_manager
