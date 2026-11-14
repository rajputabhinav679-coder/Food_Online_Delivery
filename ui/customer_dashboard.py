import streamlit as st
from config.payment_config import UPI_QR_IMAGE, UPI_ID
from config.app_config import (ESTIMATED_DELIVERY_MINUTES, MAX_ITEM_QUANTITY, AUTO_REFRESH_SECONDS)
from utils.validators import validate_mobile, validate_name, validate_city, tel_link, display_name
from utils.time_utils import delivery_eta, format_datetime
from utils.labels import label
from utils.image_utils import prepare_payment_screenshot, ALLOWED_TYPES
from ui.navigation import section_nav, goto_section, run_auto_refresh

# SMALL HELPERS
def _show_eta(order):
    """Show the fixed delivery time / countdown of an order."""
    kind, message = delivery_eta(order["created_at"], order["status"], order["delivery_time"])
    if kind == "success":
        st.success(message)
    elif kind == "warning":
        st.warning(message)
    elif kind == "info":
        st.info(message)

def _items_summary(items):
    return ", ".join(
        f"{item['name']} ×{item['quantity']}"
        for item in items
    ) or "Items not available"

# CALLBACKS (run before the page reruns)
def _add_from_menu(cart_service, customer_id, item, qty_key):
    quantity = st.session_state.get(qty_key, 1)
    success, message = cart_service.add_item(customer_id, item, quantity)
    # reset the quantity box back to 1
    st.session_state[qty_key] = 1
    st.toast(message, icon="🛒" if success else "⚠️")

def _on_cart_quantity_change(cart_service, customer_id, item_id, key):
    cart_service.update_quantity(customer_id, item_id, st.session_state.get(key, 1))

def _remove_from_cart(cart_service, customer_id, item_id):
    cart_service.remove_item(customer_id, item_id)

# MAIN DASHBOARD
def show_customer_dashboard(
    menu_service,
    cart_service,
    order_service,
    payment_service,
    feedback_service
):
    user = st.session_state.user
    customer_id = user.user_id
    st.title("🍔 Customer Dashboard")
    st.write(f"Welcome, **{display_name(user.name)}**")
    # Message after a successful order (shown once)
    placed = st.session_state.pop("order_success", None)
    if placed:
        st.success(
            f"🎉 Order #{placed['order_no']} placed successfully! "
            f"Your food will be delivered within "
            f"**{ESTIMATED_DELIVERY_MINUTES} minutes**."
        )
        st.info(
            f"Payment Status: {label(placed['payment_status'])}  |  "
            "Order Status: Placed. The Cafe Owner has been notified and "
            "will confirm your order. Track it in the **My Orders** tab."
        )
    # CART SUMMARY
    item_count = cart_service.get_item_count(customer_id)
    total = cart_service.get_total(customer_id)
    col1, col2 = st.columns(2)
    with col1:
        st.metric("🛒 Cart Items", item_count)
    with col2:
        st.metric("💰 Cart Total", f"₹{total:.2f}")
    st.divider()
    # status watcher: shows a pop-up when an order status changes
    run_auto_refresh(_status_watcher, order_service, customer_id)
    section = section_nav(
        "customer",
        ["menu", "cart", "orders", "feedback"],
        {
            "menu": "🍽️ Menu",
            "cart": f"🛒 Cart ({item_count})",
            "orders": "📦 My Orders",
            "feedback": "⭐ Feedback"
        }
    )
    # MENU SECTION
    if section == "menu":
        st.subheader("🍽️ Available Menu")
        st.caption(
            f"⏱️ Delivery time: {ESTIMATED_DELIVERY_MINUTES} minutes "
            "after you place the order."
        )
        st.info(
            f"ℹ️ You can order a maximum of **{MAX_ITEM_QUANTITY}** "
            "of one item in a single order. Type a number or use + / −."
        )
        menu_items = menu_service.get_available_items()
        if not menu_items:
            st.info("No food items are currently available.")
        else:
            categories = sorted(set(item.category for item in menu_items))
            selected_category = st.selectbox("Filter by Category", ["All"] + categories)
            if selected_category != "All":
                menu_items = [item for item in menu_items if item.category == selected_category]
            columns = st.columns(3)
            for index, item in enumerate(menu_items):
                with columns[index % 3]:
                    with st.container(border=True):
                        if item.image:
                            st.image(item.image, use_container_width=True)
                        st.subheader(f"🍽️ {item.name}")
                        st.caption(item.category)
                        if item.description:
                            st.write(item.description)
                        st.markdown(f"### ₹{item.price:.2f}")
                        in_cart = cart_service.get_quantity(customer_id, item.item_id)
                        if in_cart:
                            st.success(f"🛒 Already in cart: {in_cart}")
                        # Quantity box: use the + / - buttons
                        # OR type the number directly.
                        qty_key = f"menu_qty_{item.item_id}"
                        if qty_key not in st.session_state:
                            st.session_state[qty_key] = 1
                        st.number_input(
                            f"Quantity (max {MAX_ITEM_QUANTITY})",
                            min_value=1,
                            max_value=MAX_ITEM_QUANTITY,
                            step=1,
                            key=qty_key,
                            help=(
                                f"Maximum {MAX_ITEM_QUANTITY} of one item "
                                "per order."
                            )
                        )
                        st.button(
                            "🛒 Add to Cart",
                            key=f"add_{item.item_id}",
                            use_container_width=True,
                            on_click=_add_from_menu,
                            args=(
                                cart_service,
                                customer_id,
                                item,
                                qty_key
                            )
                        )
    # CART SECTION
    if section == "cart":
        st.subheader("🛒 Your Cart")
        cart = cart_service.get_cart(customer_id)
        if not cart.items:
            st.info("Your cart is empty.")
        else:
            st.info(
                f"ℹ️ Maximum **{MAX_ITEM_QUANTITY}** of one item is "
                "allowed in a single order."
            )
            for item in cart.items:
                with st.container(border=True):
                    col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                    with col1:
                        st.write(f"**{item.name}**")
                        st.caption(f"₹{item.price:.2f} each")
                    with col2:
                        qty_key = f"cart_qty_{item.item_id}"
                        # always show the real quantity of the cart
                        st.session_state[qty_key] = min(item.quantity, MAX_ITEM_QUANTITY)
                        st.number_input(
                            "Quantity",
                            min_value=1,
                            max_value=MAX_ITEM_QUANTITY,
                            step=1,
                            key=qty_key,
                            on_change=_on_cart_quantity_change,
                            args=(
                                cart_service,
                                customer_id,
                                item.item_id,
                                qty_key
                            )
                        )
                    with col3:
                        st.write(f"₹{item.get_total():.2f}")
                    with col4:
                        st.button(
                            "🗑️",
                            key=f"remove_{item.item_id}",
                            on_click=_remove_from_cart,
                            args=(
                                cart_service,
                                customer_id,
                                item.item_id
                            )
                        )
            st.divider()
            subtotal = cart_service.get_subtotal(customer_id)
            delivery = cart_service.get_delivery_charge(customer_id)
            total = cart_service.get_total(customer_id)
            st.write(f"Subtotal: **₹{subtotal:.2f}**")
            st.write(f"Delivery: **₹{delivery:.2f}**")
            st.subheader(f"Total: ₹{total:.2f}")
            st.info(
                f"⏱️ Estimated delivery time: "
                f"**{ESTIMATED_DELIVERY_MINUTES} minutes** "
                "after the order is placed."
            )
            if st.button("💳 Proceed to Checkout", type="primary", use_container_width=True):
                st.session_state.checkout_open = True
                st.rerun()
            # CHECKOUT SECTION
            if st.session_state.get("checkout_open", False):
                st.divider()
                st.subheader("💳 Checkout")
                st.write(f"Amount to Pay: **₹{total:.2f}**")
                # DELIVERY ADDRESS
                st.subheader("📍 Delivery Address")
                if "delivery_name" not in st.session_state:
                    st.session_state.delivery_name = display_name(user.name)
                if "delivery_phone" not in st.session_state:
                    st.session_state.delivery_phone = (getattr(user, "phone", "") or "")
                delivery_name = st.text_input("Full Name", key="delivery_name")
                delivery_phone = st.text_input(
                    "Mobile Number",
                    placeholder="10-digit number starting with 6, 7, 8 or 9",
                    max_chars=14,
                    key="delivery_phone"
                )
                if delivery_phone.strip():
                    phone_ok, phone_message = validate_mobile(delivery_phone)
                    if not phone_ok:
                        st.error(phone_message)
                house_details = st.text_input(
                    "House / Flat / Building",
                    placeholder="Enter house or flat number",
                    key="house_details"
                )
                area_details = st.text_input(
                    "Area / Street / Landmark",
                    placeholder="Enter area and landmark",
                    key="area_details"
                )
                city = st.text_input("City", placeholder="Enter city (letters only)", key="delivery_city")
                if city.strip():
                    city_ok, city_message = validate_city(city)
                    if not city_ok:
                        st.error(city_message)
                pincode = st.text_input(
                    "PIN Code",
                    placeholder="Enter 6-digit PIN code",
                    key="delivery_pincode"
                )
                # PAYMENT METHOD
                shot_bytes = None
                shot_hash = None
                st.subheader("💰 Payment Method")
                payment_method = st.radio(
                    "Select Payment Method",
                    ["UPI", "CASH_ON_DELIVERY"],
                    format_func=lambda method: (
                        "UPI Payment" if method == "UPI"
                        else "Cash on Delivery (COD)"
                    ),
                    key="payment_method_choice"
                )
                # UPI PAYMENT
                if payment_method == "UPI":
                    st.info("Scan the QR code to make your UPI payment.")
                    if UPI_QR_IMAGE.exists():
                        st.image(
                            str(UPI_QR_IMAGE),
                            caption="Scan using PhonePe or another UPI app",
                            width=280
                        )
                    else:
                        st.error("UPI QR image not found. " "Please check assets/upi_qr.jpeg")
                    st.write(f"**UPI ID:** {UPI_ID}")
                    st.subheader("📸 Upload Payment Screenshot")
                    st.caption(
                        "After paying, upload the screenshot of your "
                        "payment. The Cafe Owner checks it and confirms "
                        "your order. Until then the payment shows Pending."
                    )
                    upload_counter = st.session_state.get("upi_upload_counter", 0)
                    payment_file = st.file_uploader(
                        "Payment screenshot (JPG / PNG / WEBP)",
                        type=ALLOWED_TYPES,
                        key=f"upi_upload_{upload_counter}"
                    )
                    if payment_file is not None:
                        shot_bytes, shot_hash, shot_error = (
                            prepare_payment_screenshot(payment_file)
                        )
                        if shot_error:
                            st.error(shot_error)
                        else:
                            st.success(
                                "✅ Screenshot uploaded. Payment status: "
                                "Pending until the Cafe Owner verifies it."
                            )
                            st.image(shot_bytes, width=200)
                    else:
                        st.warning("Upload your payment screenshot to place " "the UPI order.")
                # CASH ON DELIVERY
                else:
                    st.info("Cash on Delivery selected. " "Pay when your order is delivered.")
                    st.caption("COD payment will remain PENDING until delivery.")
                st.info(
                    f"⏱️ Your food will be delivered within "
                    f"**{ESTIMATED_DELIVERY_MINUTES} minutes**."
                )
                # PLACE ORDER
                if st.button("✅ Place Order", type="primary", use_container_width=True):
                    pin_digits = "".join(ch for ch in pincode if ch.isdigit())
                    # ADDRESS VALIDATION
                    phone_ok, phone_result = validate_mobile(delivery_phone)
                    name_ok, name_result = validate_name(delivery_name)
                    if not name_ok:
                        st.error(name_result)
                        st.stop()
                    if not phone_ok:
                        st.error(phone_result)
                        st.stop()
                    phone_digits = phone_result
                    if not house_details.strip():
                        st.error("Please enter house or flat details.")
                        st.stop()
                    if not area_details.strip():
                        st.error("Please enter area or landmark.")
                        st.stop()
                    city_ok, city_result = validate_city(city)
                    if not city_ok:
                        st.error(city_result)
                        st.stop()
                    if len(pin_digits) != 6:
                        st.error("PIN code must contain 6 digits.")
                        st.stop()
                    # COMPLETE DELIVERY ADDRESS
                    delivery_address = (
                        f"{name_result}, "
                        f"Mobile: {phone_digits}, "
                        f"{house_details.strip()}, "
                        f"{area_details.strip()}, "
                        f"{city_result} - {pin_digits}"
                    )
                    # UPI NEEDS A PAYMENT SCREENSHOT
                    if payment_method == "UPI" and not shot_bytes:
                        st.error(
                            "Please upload a valid payment screenshot "
                            "to confirm your UPI payment."
                        )
                        st.stop()
                    # PAYMENT VALIDATION
                    payment_success, payment_message = (
                        payment_service.simulate_payment(
                            payment_method,
                            total
                        )
                    )
                    if not payment_success:
                        st.error(payment_message)
                        st.stop()
                    # INITIAL PAYMENT STATUS
                    payment_status = (
                        payment_service.get_initial_status(
                            payment_method,
                            has_screenshot=bool(shot_bytes)
                        )
                    )
                    # CREATE ORDER
                    order_success, order_message, order_id = (
                        order_service.create_order(
                            customer_id=customer_id,
                            cart=cart,
                            payment_method=payment_method,
                            payment_status=payment_status,
                            delivery_address=delivery_address,
                            customer_phone=phone_digits,
                            payment_screenshot=(
                                shot_bytes
                                if payment_method == "UPI" else None
                            ),
                            screenshot_hash=(
                                shot_hash
                                if payment_method == "UPI" else None
                            )
                        )
                    )
                    if order_success:
                        cart_service.clear_cart(customer_id)
                        st.session_state.checkout_open = False
                        st.session_state.order_success = {
                            "order_id": order_id,
                            "order_no": (
                                order_service.get_customer_order_number(
                                    order_id
                                )
                            ),
                            "payment_status": payment_status
                        }
                        # fresh upload box for the next order
                        st.session_state["upi_upload_counter"] = (
                            st.session_state.get("upi_upload_counter", 0)
                            + 1
                        )
                        goto_section("customer", "orders")
                        st.rerun()
                    else:
                        st.error(order_message)
    # MY ORDERS SECTION (auto refresh)
    if section == "orders":
        run_auto_refresh(_orders_section, order_service, customer_id)
    # FEEDBACK SECTION
    if section == "feedback":
        _feedback_section(order_service, feedback_service, customer_id)

# MY ORDERS (refreshes itself automatically)
def _status_watcher(order_service, customer_id):
    """Pop-up when the status of one of my orders changes."""
    orders = order_service.get_customer_orders(customer_id)
    snapshot = {order["order_id"]: order["status"] for order in orders}
    previous = st.session_state.get("orders_status_snapshot")
    st.session_state["orders_status_snapshot"] = snapshot
    if previous is None:
        return
    for order in orders:
        old_status = previous.get(order["order_id"])
        if old_status and old_status != order["status"]:
            st.toast(f"Order #{order['customer_order_no']} is now " f"{label(order['status'])}", icon="📦")

def _orders_section(order_service, customer_id):
    st.subheader("📦 My Orders")
    if st.session_state.get("auto_refresh_on", True):
        st.caption(f"🔄 Updates automatically every " f"{AUTO_REFRESH_SECONDS} seconds.")
    else:
        st.caption("Auto refresh is OFF. Use the Refresh button on top.")
    orders = order_service.get_customer_orders(customer_id)
    if not orders:
        st.info("You have not placed any orders yet.")
        return
    items_by_order = order_service.get_items_for_orders([order["order_id"] for order in orders])
    for order in orders:
        order_id = order["order_id"]
        status = order["status"]
        with st.container(border=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**Order #{order['customer_order_no']}**")
                st.caption(format_datetime(order["created_at"]))
            with col2:
                st.write(f"Amount: ₹{order['total_amount']:.2f}")
            with col3:
                if status == "DELIVERED":
                    st.success(label(status))
                elif status == "CANCELLED":
                    st.error(label(status))
                else:
                    st.info(label(status))
            # FOOD ITEMS
            st.write("🍽️ **Food ordered**")
            for item in items_by_order.get(order_id, []):
                line_total = item["price"] * item["quantity"]
                st.write(f"• {item['name']} × {item['quantity']} " f"— ₹{line_total:.2f}")
            st.divider()
            # FIXED DELIVERY TIME
            _show_eta(order)
            if status == "PLACED":
                st.caption("⏳ Waiting for the Cafe Owner to confirm your order.")
            # DELIVERY BOY NAME AND NUMBER
            if status not in ("CANCELLED", "DELIVERED"):
                if order["delivery_boy_id"]:
                    st.write(f"🚴 **Delivery Boy:** " f"{display_name(order['delivery_boy_name'])}")
                    if order["delivery_boy_phone"]:
                        st.markdown(tel_link(order["delivery_boy_phone"]) + "  (tap to call)")
                    else:
                        st.caption(
                            "Delivery Boy's number is not available. "
                            "Please contact the cafe."
                        )
                else:
                    st.caption(
                        "🚴 A Delivery Boy will be assigned when "
                        "your food is ready. Their name and number "
                        "will appear here."
                    )
            # PAYMENT METHOD AND STATUS
            st.write(f"Payment Method: {label(order['payment_method']) if order['payment_method'] else 'N/A'}")
            st.write(f"Payment Status: {label(order['payment_status']) if order['payment_status'] else 'N/A'}")
            # CANCELLED ORDER
            if status == "CANCELLED":
                st.error("❌ This order has been cancelled.")
                if order["payment_status"] == "SUCCESS":
                    st.info(
                        "💸 Your payment will be refunded by the cafe. "
                        "This order disappears after the refund is done."
                    )
            # CANCEL ORDER
            elif status in ["PLACED", "CONFIRMED"]:
                st.warning("You can cancel this order before " "food preparation starts.")
                if st.button(
                    "❌ Cancel Order",
                    key=f"cancel_order_{order_id}",
                    use_container_width=True
                ):
                    success, message = (
                        order_service.cancel_order(
                            order_id=order_id,
                            customer_id=customer_id
                        )
                    )
                    if success:
                        st.toast(message, icon="✅")
                        st.rerun()
                    else:
                        st.error(message)
            elif status == "PREPARING":
                st.info("Cancellation is no longer available " "because preparation has started.")
            elif status == "OUT_FOR_DELIVERY":
                st.info("Your order is out for delivery " "and cannot be cancelled.")
            elif status == "DELIVERED":
                st.caption("⭐ Please rate this order in the Feedback tab.")

# FEEDBACK
def _feedback_section(order_service, feedback_service, customer_id):
    st.subheader("⭐ Give Feedback")
    orders = order_service.get_customer_orders(customer_id)
    delivered = [order for order in orders if order["status"] == "DELIVERED"]
    given = feedback_service.get_customer_feedback(customer_id)
    pending = [order for order in delivered if order["order_id"] not in given]
    items_by_order = order_service.get_items_for_orders([order["order_id"] for order in delivered])
    if not delivered:
        st.info("You can give feedback after your order is delivered.")
    elif not pending:
        st.success("You have given feedback for all delivered orders. Thank you!")
    else:
        order_numbers = {order["order_id"]: order["customer_order_no"] for order in orders}
        def order_label(order_id):
            return (
                f"Order #{order_numbers[order_id]} — "
                f"{_items_summary(items_by_order.get(order_id, []))}"
            )
        selected_order_id = st.selectbox(
            "Select delivered order",
            [order["order_id"] for order in pending],
            format_func=order_label,
            key="feedback_order_choice"
        )
        with st.form("feedback_form", clear_on_submit=True):
            rating = st.radio(
                "How was your food and delivery?",
                [1, 2, 3, 4, 5],
                format_func=lambda stars: "⭐" * stars,
                index=None,
                horizontal=True
            )
            comment = st.text_area(
                "Your feedback (optional)",
                max_chars=500,
                placeholder="Tell us about the taste, packing, delivery..."
            )
            submitted = st.form_submit_button(
                "Submit Feedback",
                type="primary",
                use_container_width=True
            )
        if submitted:
            if rating is None:
                st.error("Please select a star rating.")
            else:
                success, message = feedback_service.submit_feedback(
                    selected_order_id,
                    customer_id,
                    rating,
                    comment
                )
                if success:
                    st.toast(message, icon="⭐")
                    st.rerun()
                else:
                    st.error(message)
    # PREVIOUS FEEDBACK
    if given:
        st.divider()
        st.subheader("📝 Your Previous Feedback")
        order_numbers = {order["order_id"]: order["customer_order_no"] for order in orders}
        for order_id, feedback in given.items():
            with st.container(border=True):
                st.write(
                    f"**Order #{order_numbers.get(order_id, order_id)}** — "
                    f"{'⭐' * feedback['rating']}"
                )
                if feedback["comment"]:
                    st.write(feedback["comment"])
                st.caption(format_datetime(feedback["created_at"]))