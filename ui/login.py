import streamlit as st
from utils.validators import validate_mobile, validate_name, validate_password
from ui.navigation import section_nav, goto_section

def show_login(auth_service):
    st.title("🍔 Food Online Cafe")
    st.subheader("Welcome! Please login to continue.")
    section = section_nav(
        "auth",
        ["login", "register"],
        {"login": "🔑 Login", "register": "📝 Customer Registration"}
    )
    # LOGIN SECTION
    if section == "login":
        st.subheader("User Login")
        done_message = st.session_state.pop("register_done", None)
        if done_message:
            st.success(done_message)
            st.info("You can now login.")
        email = st.text_input("Email Address", key="login_email", placeholder="example@gmail.com")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", type="primary", use_container_width=True):
            email = email.strip().lower()
            if not email or not password:
                st.error("Please enter email and password.")
            else:
                valid, result = auth_service.validate_gmail(email)
                if not valid:
                    st.error(result)
                else:
                    user = auth_service.login(result, password)
                    if user is None:
                        wait = auth_service.lockout_seconds(result)
                        st.error(f"Too many wrong attempts. Try again after {-(-wait // 60)} minute(s)."
                                 if wait else "Invalid email or password.")
                    else:
                        st.session_state.logged_in = True
                        st.session_state.user = user
                        st.success("Login successful!")
                        # app.py creates and saves the session
                        st.rerun()
    # CUSTOMER REGISTRATION SECTION
    if section == "register":
        st.subheader("Create Customer Account")
        name = st.text_input("Full Name", key="register_name")
        email = st.text_input(
            "Email Address",
            key="register_email",
            placeholder="example@gmail.com"
        )
        phone = st.text_input(
            "Mobile Number",
            key="register_phone",
            max_chars=14,
            placeholder="10-digit number starting with 6, 7, 8 or 9"
        )
        password = st.text_input("Create Password", type="password", key="register_password")
        confirm_password = st.text_input(
            "Confirm Password",
            type="password",
            key="register_confirm_password"
        )
        if st.button("Create Customer Account", type="primary", use_container_width=True):
            email = email.strip().lower()
            name_valid, name_result = validate_name(name)
            if not name_valid:
                st.error(name_result)
            elif not email:
                st.error("Please enter your email.")
            else:
                valid, result = auth_service.validate_gmail(email)
                if not valid:
                    st.error(result)
                elif not validate_mobile(phone)[0]:
                    st.error(validate_mobile(phone)[1])
                elif not password:
                    st.error("Please enter a password.")
                elif password != confirm_password:
                    st.error("Passwords do not match.")
                elif len(password) < 6:
                    st.error("Password must contain at least 6 characters.")
                else:
                    success, message = auth_service.register_customer(
                        name_result,
                        result,
                        password,
                        phone
                    )
                    if success:
                        st.session_state["register_done"] = message
                        goto_section("auth", "login")
                        st.rerun()
                    else:
                        st.error(message)

def show_change_password(auth_service, user):
    """Sidebar form for every logged-in user."""
    n = st.session_state.get("cp_n", 0)
    old = st.text_input("Current Password", type="password", key=f"cp_old_{n}")
    new = st.text_input("New Password", type="password", key=f"cp_new_{n}")
    confirm = st.text_input("Confirm New Password", type="password", key=f"cp_confirm_{n}")
    if st.button("Change Password", type="primary", use_container_width=True, key="cp_go"):
        valid, message = validate_password(new)
        if not old:
            st.error("Please enter your current password.")
        elif not valid:
            st.error(message)
        elif new != confirm:
            st.error("Passwords do not match.")
        else:
            ok, message = auth_service.change_password(user.user_id, old, new)
            if ok:
                st.session_state["cp_n"] = n + 1
                st.toast(message, icon="🔑")
                st.rerun()
            else:
                st.error(message)
