"""Email (SMTP) settings for order notifications.

Settings are read from, in this order of priority:

1. Environment variables:
     EMAIL_SENDER, EMAIL_APP_PASSWORD, EMAIL_SMTP_HOST, EMAIL_SMTP_PORT,
     CAFE_NOTIFY_EMAIL, APP_URL
2. Streamlit secrets  (.streamlit/secrets.toml  or the Secrets box of
   Streamlit Cloud):

     [email]
     sender = "yourcafe@gmail.com"
     app_password = "xxxx xxxx xxxx xxxx"
     # optional:
     smtp_host = "smtp.gmail.com"
     smtp_port = 587
     # cafe_email = "owner@gmail.com"  # optional recipient override

     [auth]
     cafe_email = "owner@gmail.com"    # owner login and default order-alert inbox
     app_url = "https://your-app.streamlit.app"

For Gmail, create an "App password" (Google Account -> Security ->
2-Step Verification -> App passwords). Never use the normal Gmail password.
"""
import os

def load_email_settings():
    settings = {
        "sender": "",
        "app_password": "",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "cafe_email": "",
        "app_url": ""
    }
    # Streamlit secrets (may not exist -> ignore)
    try:
        import streamlit as st
        section = st.secrets.get("email", {})
        auth_section = st.secrets.get("auth", {})
        for key in settings:
            if key in section and section[key] not in (None, ""):
                settings[key] = section[key]
        # If no explicit notification recipient is set, use the configured
        # Cafe Owner login email.
        if not settings["cafe_email"] and auth_section.get("cafe_email"):
            settings["cafe_email"] = str(auth_section["cafe_email"]).strip()
    except Exception:
        pass
    # environment variables win
    env_map = {
        "sender": "EMAIL_SENDER",
        "app_password": "EMAIL_APP_PASSWORD",
        "smtp_host": "EMAIL_SMTP_HOST",
        "smtp_port": "EMAIL_SMTP_PORT",
        "cafe_email": "CAFE_NOTIFY_EMAIL",
        "app_url": "APP_URL"
    }
    for key, env_name in env_map.items():
        value = os.environ.get(env_name)
        if value:
            settings[key] = value
    try:
        settings["smtp_port"] = int(settings["smtp_port"])
    except (TypeError, ValueError):
        settings["smtp_port"] = 587
    # Google shows app passwords with spaces - remove them
    settings["app_password"] = str(settings["app_password"]).replace(" ", "")
    return settings

def is_configured(settings):
    return bool(settings.get("sender") and settings.get("app_password"))
