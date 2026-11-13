"""SMS settings. [sms] api_key in .streamlit/secrets.toml (or SMS_API_KEY) = Fast2SMS API key."""
import os

def load_sms_settings():
    settings = {"api_key": "", "route": "otp"}
    try:
        import streamlit as st
        section = st.secrets.get("sms", {})
        for key in settings:
            if section.get(key):
                settings[key] = str(section[key]).strip()
    except Exception:
        pass
    if os.environ.get("SMS_API_KEY"):
        settings["api_key"] = os.environ["SMS_API_KEY"].strip()
    return settings
