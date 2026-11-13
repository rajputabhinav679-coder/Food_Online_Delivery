import streamlit as st
from config.app_config import AUTO_REFRESH_SECONDS
from utils.labels import label
from utils.validators import tel_link, display_name, area_of
from utils.time_utils import delivery_eta, format_datetime
from ui.navigation import section_nav, run_auto_refresh

def _customer_phone(order):
    return order["customer_phone"] or order["customer_account_phone"] or ""

def _show_order_details(order, items, accepted):
    """Details of an order. Name, mobile and full address are shown only AFTER the Delivery Boy accepts."""
    if accepted:
        st.write(f"Customer: **{display_name(order['customer_name'])}**")
        phone = _customer_phone(order)
        if phone:
            st.markdown(tel_link(phone) + "  (tap to call customer)")
        else:
            st.caption("Customer mobile number not available.")
    else:
        st.write(f"📍 Delivery area: **{area_of(order['delivery_address'])}**")
        st.caption("Customer name, mobile and full address are shown after you accept the order.")
    st.write("🍽️ **Food to deliver**")
    for item in items:
        st.write(f"• {item['name']} × {item['quantity']}")
    st.write(f"Amount: **₹{order['total_amount']:.2f}**")
    method = order["payment_method"] or "N/A"
    payment_status = order["payment_status"] or "PENDING"
    if method == "CASH_ON_DELIVERY" and payment_status != "SUCCESS":
        st.warning(
            f"💵 Cash on Delivery — collect ₹{order['total_amount']:.2f} "
            "from the customer."
        )
    else:
        st.caption(f"Payment: {label(method)} ({label(payment_status)})")
    if accepted:
        st.write("📍 **Delivery Address**")
        st.write(order["delivery_address"] or "Address not available")

def _new_order_watcher(delivery_service):
    """Pop-up when a new order becomes available (auto refresh)."""
    available_ids = {order["order_id"] for order in delivery_service.get_available_orders()}
    seen = st.session_state.get("delivery_seen_available")
    if seen is not None:
        for order in delivery_service.get_available_orders():
            if order["order_id"] not in seen:
                st.toast(f"🔔 New order #{order['order_no']} is available!", icon="📦")
    st.session_state["delivery_seen_available"] = available_ids

def _delivery_section(delivery_service, order_service, delivery_boy_id, section):
    if st.session_state.get("auto_refresh_on", True):
        st.caption(f"🔄 Updates automatically every " f"{AUTO_REFRESH_SECONDS} seconds.")
    else:
        st.caption("Auto refresh is OFF. Use the Refresh button on top.")
    available_orders = delivery_service.get_available_orders()
    my_orders = delivery_service.get_my_orders(delivery_boy_id)
    items_by_order = order_service.get_items_for_orders(
        [order["order_id"] for order in available_orders + my_orders]
    )
    # AVAILABLE ORDERS
    if section == "available":
        st.subheader("📦 Available Orders")
        if not available_orders:
            st.info("No available orders right now.")
        else:
            st.write(f"Available Orders: **{len(available_orders)}**")
            for order in available_orders:
                with st.container(border=True):
                    st.subheader(f"Order #{order['order_no']}")
                    _show_order_details(order, items_by_order.get(order["order_id"], []), False)
                    st.write(f"Order Status: **{label(order['order_status'])}**")
                    kind, message = delivery_eta(order["created_at"], order["order_status"])
                    if message:
                        st.caption(message.replace("**", ""))
                    if st.button(
                        "✅ Accept Order",
                        key=f"accept_{order['order_id']}",
                        type="primary",
                        use_container_width=True
                    ):
                        accepted = delivery_service.accept_order(order["order_id"], delivery_boy_id)
                        if accepted:
                            st.toast("Order accepted successfully!", icon="✅")
                        else:
                            st.toast("This order is no longer available.", icon="⚠️")
                        st.rerun()
    # MY DELIVERIES
    if section == "mine":
        st.subheader("🚴 My Deliveries")
        if not my_orders:
            st.info("You have not accepted any orders.")
        else:
            st.write(f"Total Assigned Orders: **{len(my_orders)}**")
            for order in my_orders:
                with st.container(border=True):
                    st.subheader(f"Order #{order['order_no']}")
                    _show_order_details(order, items_by_order.get(order["order_id"], []), True)
                    status = order["order_status"]
                    st.write(f"Order Status: **{label(status)}**")
                    if status == "DELIVERED":
                        st.success("✅ Delivery completed.")
                        if order["delivery_time"]:
                            st.caption(f"Delivered at: {format_datetime(order['delivery_time'])}")
                    elif status == "CANCELLED":
                        st.error("This order was cancelled.")
                    elif status == "OUT_FOR_DELIVERY":
                        kind, message = delivery_eta(order["created_at"], status)
                        if message:
                            st.caption(message.replace("**", ""))
                        if st.button(
                            "✅ Mark as Delivered",
                            key=f"delivered_{order['order_id']}",
                            type="primary",
                            use_container_width=True
                        ):
                            updated = delivery_service.mark_delivered(
                                order["order_id"],
                                delivery_boy_id
                            )
                            if updated:
                                st.toast("Order marked as delivered!", icon="✅")
                            else:
                                st.toast("Unable to update this order.", icon="⚠️")
                            st.rerun()
                    else:
                        st.info("Waiting for order processing.")

def show_delivery_dashboard(delivery_service, user, order_service):
    # ACCESS CHECK
    if user is None or user.role.lower() != "delivery_boy":
        st.error("Access Denied! Delivery Boy access only.")
        return
    st.title("🚴 Delivery Boy Dashboard")
    st.write(f"Welcome, **{display_name(user.name)}**")
    run_auto_refresh(_new_order_watcher, delivery_service)
    section = section_nav(
        "delivery",
        ["available", "mine"],
        {
            "available": "📦 Available Orders",
            "mine": "🚴 My Deliveries"
        }
    )
    run_auto_refresh(_delivery_section, delivery_service, order_service, user.user_id, section)
