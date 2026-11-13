import streamlit as st
from database.database import Database
from services.auth_service import AuthService
from services.menu_service import MenuService
from services.cart_service import CartService
from services.order_service import OrderService
from services.payment_service import PaymentService
from services.report_service import ReportService
from services.delivery_service import DeliveryService
from services.feedback_service import FeedbackService
from services.notification_service import NotificationService
from ui.login import show_login, show_change_password
from utils.labels import label
from utils.validators import display_name, tel_link
from config.app_config import HELPLINE_NUMBER
from ui.styles import apply_styles
from ui.navigation import render_top_bar, auto_hide_passwords
from ui.cafe_dashboard import show_cafe_dashboard
from ui.customer_dashboard import show_customer_dashboard
from ui.delivery_dashboard import show_delivery_dashboard

# INITIALIZE APPLICATION
def initialize_app():
    if "database" not in st.session_state:
        st.session_state.database = Database()
    if "notification_service" not in st.session_state:
        st.session_state.notification_service = NotificationService(st.session_state.database)
    if "auth_service" not in st.session_state:
        st.session_state.auth_service = AuthService(st.session_state.database, st.session_state.notification_service)
    if "menu_service" not in st.session_state:
        st.session_state.menu_service = MenuService(st.session_state.database)
    if "cart_service" not in st.session_state:
        st.session_state.cart_service = CartService()
    if "order_service" not in st.session_state:
        st.session_state.order_service = OrderService(
            st.session_state.database,
            st.session_state.notification_service
        )
    if "delivery_service" not in st.session_state:
        st.session_state.delivery_service = DeliveryService(st.session_state.database)
    if "payment_service" not in st.session_state:
        st.session_state.payment_service = PaymentService()
    if "feedback_service" not in st.session_state:
        st.session_state.feedback_service = FeedbackService(st.session_state.database)
    if "report_service" not in st.session_state:
        st.session_state.report_service = ReportService(st.session_state.database)
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user" not in st.session_state:
        st.session_state.user = None

# LOGOUT
def logout():
    st.session_state.logged_in = False
    st.session_state.user = None
    # Clear customer cart on logout
    st.session_state.cart_service = CartService()
    st.session_state.pop("customer_carts", None)
    # Clear checkout / quantity / refresh state of the previous user
    stale_prefixes = (
        "delivery_name", "delivery_phone", "delivery_city",
        "delivery_pincode", "house_details", "area_details",
        "checkout_open", "order_success", "orders_snapshot",
        "menu_qty_", "cart_qty_", "cafe_last_order_id",
        "delivery_seen_available", "feedback_order_choice",
        "nav_", "goto_", "upi_upload", "orders_status_snapshot",
        "cp_"
    )
    for key in list(st.session_state.keys()):
        if str(key).startswith(stale_prefixes):
            del st.session_state[key]
    st.rerun()

# MAIN APPLICATION
def main():
    st.set_page_config(page_title="Food Online Cafe", page_icon="🍔", layout="wide")
    apply_styles()
    initialize_app()
    auto_hide_passwords(5)
    # LOGIN PAGE
    if not st.session_state.logged_in:
        render_top_bar("auth")
        show_login(st.session_state.auth_service)
        return
    # LOGGED-IN USER
    user = st.session_state.user
    if user is None:
        st.session_state.logged_in = False
        st.rerun()
        return
    # SIDEBAR
    with st.sidebar:
        st.write(f"👤 **{display_name(user.name)}**")
        st.write(f"Role: **{label(user.role)}**")
        st.divider()
        with st.expander("🔑 Change Password"):
            show_change_password(st.session_state.auth_service, user)
        if st.button("Logout", use_container_width=True):
            logout()
    # BACK / REFRESH / AUTO REFRESH BAR (every page)
    role_scope = {
        "cafe": "cafe",
        "delivery_boy": "delivery",
        "customer": "customer"
    }.get(user.role.lower(), "app")
    render_top_bar(role_scope)
    st.caption("Helpline: " + tel_link(HELPLINE_NUMBER))
    # cafe DASHBOARD
    if user.role.lower() == "cafe":
        show_cafe_dashboard(
            st.session_state.menu_service,
            st.session_state.order_service,
            st.session_state.report_service,
            st.session_state.auth_service,
            st.session_state.feedback_service
        )
    # DELIVERY BOY DASHBOARD
    elif user.role.lower() == "delivery_boy":
        show_delivery_dashboard(
            st.session_state.delivery_service,
            user,
            st.session_state.order_service
        )
    # CUSTOMER DASHBOARD
    elif user.role.lower() == "customer":
        show_customer_dashboard(
            st.session_state.menu_service,
            st.session_state.cart_service,
            st.session_state.order_service,
            st.session_state.payment_service,
            st.session_state.feedback_service
        )
    else:
        st.error("Invalid user role. Please contact cafe.")
# RUN APPLICATION
if __name__ == "__main__":
    main()
