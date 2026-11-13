from datetime import timedelta
import streamlit as st
import pandas as pd
from config.app_config import AUTO_REFRESH_SECONDS
from utils.validators import validate_mobile, validate_name, tel_link, display_name
from ui.navigation import section_nav, run_auto_refresh
from utils.time_utils import delivery_eta, format_datetime, now_ist
from utils.labels import label
from utils.excel_utils import to_excel_bytes, EXCEL_MIME
from utils.image_utils import prepare_food_image, ALLOWED_TYPES, MAX_UPLOAD_MB

def update_payment_status(database, order_id, new_status):
    """Update payment status in the database."""
    connection = database.get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("""UPDATE payments
            SET status = ?
            WHERE order_id = ?""", (new_status, order_id))
        if cursor.rowcount == 0:
            connection.rollback()
            return False, "Payment record not found."
        connection.commit()
        return True, "Payment status updated successfully."
    except Exception as error:
        connection.rollback()
        return False, f"Payment update failed: {error}"
    finally:
        connection.close()

# AUTO-REFRESHING SECTIONS
def _stats_section(order_service):
    """Order counters + pop-up for new orders (auto refresh)."""
    # pop-up when a new order arrives (works on every section)
    latest = order_service.get_all_orders()
    latest_order_id = max((order["order_id"] for order in latest), default=0)
    last_seen = st.session_state.get("cafe_last_order_id")
    if last_seen is not None and latest_order_id > last_seen:
        newest = [order for order in latest if order["order_id"] == latest_order_id][0]
        st.toast(f"🔔 New order #{newest['order_no']} received!", icon="🛎️")
    st.session_state["cafe_last_order_id"] = latest_order_id
    total_orders = order_service.get_order_count()
    placed_orders = order_service.get_status_count("PLACED")
    preparing_orders = order_service.get_status_count("PREPARING")
    delivered_orders = order_service.get_status_count("DELIVERED")
    refund_pending = order_service.get_status_count("CANCELLED")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("📦 Total Orders", total_orders)
    with col2:
        st.metric("🟡 Placed", placed_orders)
    with col3:
        st.metric("👨‍🍳 Preparing", preparing_orders)
    with col4:
        st.metric("🟢 Delivered", delivered_orders)
    with col5:
        st.metric("💸 Refund Pending", refund_pending)

def _orders_section(order_service, auth_service):
    """Order management - refreshes itself automatically."""
    st.subheader("📦 Order Management")
    if st.session_state.get("auto_refresh_on", True):
        st.caption(f"🔄 Updates automatically every " f"{AUTO_REFRESH_SECONDS} seconds.")
    else:
        st.caption("Auto refresh is OFF. Use the Refresh button on top.")
    orders = order_service.get_all_orders()
    if not orders:
        st.info("No orders have been placed yet.")
        return
    filter_status = st.selectbox(
        "Filter Orders",
        [
            "ALL",
            "PLACED",
            "CONFIRMED",
            "PREPARING",
            "OUT_FOR_DELIVERY",
            "DELIVERED",
            "CANCELLED"
        ],
        format_func=lambda code: "All" if code == "ALL" else label(code),
        key="cafe_order_filter"
    )
    if filter_status != "ALL":
        orders = [order for order in orders if order["order_status"] == filter_status]
    st.write(f"Showing **{len(orders)}** order(s)")
    st.divider()
    items_by_order = order_service.get_items_for_orders([order["order_id"] for order in orders])
    for order in orders:
        order_id = order["order_id"]
        status = order["order_status"]
        payment_method = order["payment_method"] or "N/A"
        payment_status = order["payment_status"] or "PENDING"
        with st.container(border=True):
            col1, col2, col3 = st.columns([2, 3, 2])
            with col1:
                st.subheader(f"📦 Order #{order['order_no']}")
                st.caption(format_datetime(order["created_at"]))
                st.write(f"Customer: **{display_name(order['customer_name'])}**")
                st.caption(order["customer_email"])
                customer_phone = (order["customer_phone"] or order["customer_account_phone"])
                if customer_phone:
                    st.markdown(tel_link(customer_phone))
                st.write("🍽️ **Food Ordered**")
                for item in items_by_order.get(order_id, []):
                    st.write(f"• {item['name']} × {item['quantity']}")
                st.write("📍 **Delivery Address**")
                st.caption(order["delivery_address"] or "Address not available")
            with col2:
                st.write(f"💰 **₹{order['total_amount']:.2f}**")
                st.write(f"Payment: **{label(payment_method)}**")
                if payment_status == "SUCCESS":
                    st.success("Payment: Success")
                elif payment_status == "FAILED":
                    st.error("Payment: Failed")
                else:
                    st.warning("Payment: Pending")
                st.write(f"🚚 Delivery: **{label(order['delivery_status'])}**")
                kind, eta_message = delivery_eta(
                    order["created_at"],
                    status,
                    order["delivery_time"]
                )
                if eta_message:
                    st.caption(eta_message.replace("**", ""))
                st.write("🚴 **Delivery Boy**")
                delivery_boy_name = order["delivery_boy_name"]
                if delivery_boy_name:
                    st.success(display_name(delivery_boy_name))
                    if order["delivery_boy_phone"]:
                        st.markdown(tel_link(order["delivery_boy_phone"]))
                    elif order["delivery_boy_email"]:
                        st.caption(order["delivery_boy_email"])
                else:
                    st.warning("Delivery Boy Not Assigned")
            with col3:
                st.write(f"Order Status: **{label(status)}**")
                if status == "PLACED":
                    confirm_label = (
                        "✅ Verify Payment & Confirm Order"
                        if payment_method == "UPI"
                        else "✅ Confirm Order"
                    )
                    if st.button(
                        confirm_label,
                        key=f"confirm_{order_id}",
                        type="primary",
                        use_container_width=True
                    ):
                        success, message = order_service.confirm_order(order_id)
                        if success:
                            st.toast(
                                "Order confirmed. Delivery Boys are "
                                "being informed.",
                                icon="✅"
                            )
                            st.rerun()
                        else:
                            st.error(message)
                    if payment_method == "UPI":
                        st.caption("Check the payment screenshot below " "before confirming.")
                    else:
                        st.caption("Delivery Boys get this order only after " "you confirm it.")
                if status not in ["DELIVERED", "CANCELLED"]:
                    options = order_service.selectable_statuses(status, bool(order["delivery_boy_id"]))
                    new_status = st.selectbox(
                        "Change Order Status",
                        options,
                        index=options.index(status),
                        format_func=label,
                        key=f"status_{order_id}"
                    )
                    if st.button(
                        "🔄 Update Status",
                        key=f"update_{order_id}",
                        type="primary",
                        use_container_width=True
                    ):
                        success, message = (order_service.update_status(order_id, new_status))
                        if success:
                            st.rerun()
                        else:
                            st.error(message)
            # CANCELLED AFTER PAYMENT -> REFUND
            if status == "CANCELLED":
                st.divider()
                st.warning(
                    f"💸 This order was cancelled after payment. "
                    f"Refund ₹{order['total_amount']:.2f} to the customer."
                )
                if customer_phone:
                    st.markdown(tel_link(customer_phone))
                if st.button(
                    "✅ Refund done — remove this order",
                    key=f"refunded_{order_id}",
                    type="primary"
                ):
                    success, message = order_service.mark_refunded(order_id)
                    if success:
                        st.rerun()
                    else:
                        st.error(message)
                continue
            # PAYMENT VERIFICATION
            st.divider()
            st.write("### 💳 Payment Verification")
            if payment_status == "PENDING":
                if payment_method == "UPI":
                    st.warning(
                        "UPI payment is pending. Check the customer's "
                        "screenshot and your actual UPI transaction, then "
                        "press 'Verify Payment & Confirm Order'. The order "
                        "reaches the Delivery Boys only after that."
                    )
                    if st.checkbox(
                        "🧾 View payment screenshot",
                        value=True,
                        key=f"view_shot_{order_id}"
                    ):
                        screenshot = order_service.get_payment_screenshot(order_id)
                        if screenshot:
                            st.image(screenshot, width=320)
                        else:
                            st.caption("No screenshot saved for this order.")
                    if status == "PLACED" and st.button(
                        "❌ Reject Payment (wrong / fake screenshot)",
                        key=f"failed_upi_{order_id}"
                    ):
                        success, message = update_payment_status(
                            auth_service.database,
                            order_id,
                            "FAILED"
                        )
                        if success:
                            st.rerun()
                        else:
                            st.error(message)
                elif payment_method == "CASH_ON_DELIVERY":
                    if status == "DELIVERED":
                        st.info("Confirm that the customer has paid cash.")
                        if st.button(
                            "✅ Confirm COD Payment Received",
                            key=f"verify_cod_{order_id}",
                            type="primary"
                        ):
                            success, message = update_payment_status(
                                auth_service.database,
                                order_id,
                                "SUCCESS"
                            )
                            if success:
                                st.rerun()
                            else:
                                st.error(message)
                    else:
                        st.warning("COD payment can only be confirmed " "after delivery.")
            elif payment_status == "SUCCESS":
                if payment_method == "UPI":
                    st.success("Payment verified by the Cafe Owner.")
                    if st.checkbox("🧾 View payment screenshot", key=f"view_shot_{order_id}"):
                        screenshot = order_service.get_payment_screenshot(order_id)
                        if screenshot:
                            st.image(screenshot, width=320)
                        else:
                            st.caption("No screenshot saved for this order.")
                else:
                    st.success("Payment has been verified.")
            elif payment_status == "FAILED":
                st.error("Payment marked as failed.")
            # DELIVERY TIME
            if order["delivery_time"]:
                st.caption(f"Delivered at: {format_datetime(order['delivery_time'])}")

def _feedback_section(feedback_service):
    st.subheader("⭐ Customer Feedback")
    count, average = feedback_service.get_summary()
    col1, col2 = st.columns(2)
    with col1:
        st.metric("📝 Total Feedback", count)
    with col2:
        st.metric("⭐ Average Rating", f"{average:.1f} / 5" if count else "No ratings yet")
    st.divider()
    feedbacks = feedback_service.get_all_feedback()
    if not feedbacks:
        st.info("No customer feedback yet.")
        return
    for feedback in feedbacks:
        with st.container(border=True):
            st.write(
                f"**{display_name(feedback['customer_name'])}** — "
                f"Order #{feedback['order_no']} — "
                f"{'⭐' * feedback['rating']}"
            )
            if feedback["comment"]:
                st.write(feedback["comment"])
            else:
                st.caption("(No written comment)")
            st.caption(format_datetime(feedback["created_at"]))

# CAFE DASHBOARD
def show_cafe_dashboard(
    menu_service,
    order_service,
    report_service,
    auth_service,
    feedback_service
):
    user = st.session_state.get("user")
    # ACCESS CONTROL
    if user is None or user.role.lower() != "cafe":
        st.error("Access Denied! Only Cafe Owner can access this dashboard.")
        return
    st.title("☕ Cafe Owner Dashboard")
    st.write(f"Welcome, **{display_name(user.name)}**")
    st.divider()
    # ORDER STATISTICS (auto refresh)
    run_auto_refresh(_stats_section, order_service)
    st.divider()
    # MAIN TABS
    section = section_nav(
        "cafe",
        ["menu", "orders", "reports", "delivery", "feedback"],
        {
            "menu": "🍽️ Menu Management",
            "orders": "📦 Order Management",
            "reports": "📊 Growth Reports",
            "delivery": "🚴 Delivery Boys",
            "feedback": "⭐ Customer Feedback"
        }
    )
    # MENU MANAGEMENT
    if section == "menu":
        st.subheader("🍽️ Food Menu Management")
        menu_items = menu_service.get_all_items()
        total_items = len(menu_items)
        available_items = sum(1 for item in menu_items if item.available)
        unavailable_items = total_items - available_items
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Food Items", total_items)
        with col2:
            st.metric("Available", available_items)
        with col3:
            st.metric("Unavailable", unavailable_items)
        st.divider()
        add_tab, manage_tab = st.tabs(["➕ Add Food", "📋 Manage Menu"])
        # ADD FOOD
        with add_tab:
            with st.form("add_food_form"):
                name = st.text_input("Food Name")
                category = st.selectbox(
                    "Category",
                    [
                        "Pizza",
                        "Burger",
                        "Biryani",
                        "Indian",
                        "Chinese",
                        "South Indian",
                        "Dessert",
                        "Beverage",
                        "Other"
                    ]
                )
                price = st.number_input("Price (₹)", min_value=1.0, value=100.0, step=10.0)
                description = st.text_area("Description")
                food_photo = st.file_uploader(
                    f"Food Photo (JPG / PNG / WEBP, max {MAX_UPLOAD_MB} MB)",
                    type=ALLOWED_TYPES,
                    key="add_food_photo"
                )
                available = st.checkbox("Available", value=True)
                submitted = st.form_submit_button(
                    "Add Food Item",
                    type="primary",
                    use_container_width=True
                )
            if submitted:
                image_bytes, image_error = prepare_food_image(food_photo)
                if not name.strip():
                    st.error("Please enter food name.")
                elif image_error:
                    st.error(image_error)
                else:
                    success, message = menu_service.add_item(
                        image_bytes=image_bytes,
                        name=name.strip(),
                        category=category,
                        price=price,
                        description=description.strip(),
                        available=available
                    )
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
        # MANAGE MENU
        with manage_tab:
            if not menu_items:
                st.info("No food items found.")
            else:
                for item in menu_items:
                    with st.container(border=True):
                        col1, col2, col3 = st.columns([3, 2, 1])
                        with col1:
                            if item.image:
                                st.image(item.image, width=160)
                            st.subheader(f"🍽️ {item.name}")
                            st.caption(item.category)
                            if item.description:
                                st.write(item.description)
                        with col2:
                            st.write(f"**Price: ₹{item.price:.2f}**")
                            if item.available:
                                st.success("Available")
                            else:
                                st.error("Unavailable")
                        with col3:
                            if st.button(
                                "🗑️ Delete",
                                key=f"delete_{item.item_id}",
                                use_container_width=True
                            ):
                                success, message = (menu_service.delete_item(item.item_id))
                                if success:
                                    st.success(message)
                                    st.rerun()
                                else:
                                    st.error(message)
                        edit_col, availability_col = st.columns(2)
                        with edit_col:
                            with st.expander("✏️ Edit Food"):
                                with st.form(f"edit_{item.item_id}"):
                                    edit_name = st.text_input("Food Name", value=item.name)
                                    edit_category = st.selectbox(
                                        "Category",
                                        [
                                            "Pizza",
                                            "Burger",
                                            "Biryani",
                                            "Indian",
                                            "Chinese",
                                            "South Indian",
                                            "Dessert",
                                            "Beverage",
                                            "Other"
                                        ],
                                        index=(
                                            [
                                                "Pizza",
                                                "Burger",
                                                "Biryani",
                                                "Indian",
                                                "Chinese",
                                                "South Indian",
                                                "Dessert",
                                                "Beverage",
                                                "Other"
                                            ].index(item.category)
                                            if item.category in [
                                                "Pizza",
                                                "Burger",
                                                "Biryani",
                                                "Indian",
                                                "Chinese",
                                                "South Indian",
                                                "Dessert",
                                                "Beverage",
                                                "Other"
                                            ] else 8
                                        )
                                    )
                                    edit_price = st.number_input(
                                        "Price",
                                        min_value=1.0,
                                        value=float(item.price),
                                        step=10.0
                                    )
                                    edit_description = st.text_area(
                                        "Description",
                                        value=item.description or ""
                                    )
                                    edit_photo = st.file_uploader(
                                        "New Food Photo (leave empty to keep current)",
                                        type=ALLOWED_TYPES,
                                        key=f"edit_photo_{item.item_id}"
                                    )
                                    remove_photo = False
                                    if item.image:
                                        remove_photo = st.checkbox(
                                            "Remove current photo",
                                            key=f"remove_photo_{item.item_id}"
                                        )
                                    edit_available = st.checkbox(
                                        "Available",
                                        value=bool(item.available)
                                    )
                                    save = st.form_submit_button("Save Changes", type="primary")
                                if save:
                                    new_image, edit_image_error = (prepare_food_image(edit_photo))
                                    if not edit_name.strip():
                                        st.error("Food name is required.")
                                    elif edit_image_error:
                                        st.error(edit_image_error)
                                    else:
                                        success, message = (
                                            menu_service.update_item(
                                                item_id=item.item_id,
                                                name=edit_name.strip(),
                                                category=edit_category,
                                                price=edit_price,
                                                description=edit_description.strip(),
                                                available=edit_available,
                                                image_bytes=new_image,
                                                remove_image=remove_photo
                                            )
                                        )
                                        if success:
                                            st.success(message)
                                            st.rerun()
                                        else:
                                            st.error(message)
                        with availability_col:
                            button_text = (
                                "🔴 Make Unavailable"
                                if item.available
                                else "🟢 Make Available"
                            )
                            if st.button(
                                button_text,
                                key=f"availability_{item.item_id}",
                                use_container_width=True
                            ):
                                success, message = (menu_service.toggle_availability(item.item_id))
                                if success:
                                    st.success(message)
                                    st.rerun()
                                else:
                                    st.error(message)
    # ORDER MANAGEMENT
    if section == "orders":
        run_auto_refresh(_orders_section, order_service, auth_service)
    # GROWTH REPORTS
    if section == "reports":
        st.subheader("📊 Growth Reports & Analytics")
        total_orders_report = report_service.get_total_orders()
        total_revenue = report_service.get_total_revenue()
        total_customers = report_service.get_total_customers()
        delivery_data = report_service.get_delivery_performance()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📦 Total Orders", total_orders_report)
        with col2:
            st.metric("💰 Total Revenue", f"₹{total_revenue:,.2f}")
        with col3:
            st.metric("👥 Total Customers", total_customers)
        st.divider()
        # DELIVERY PERFORMANCE
        st.subheader("🚚 Delivery Performance")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("🟢 Delivered", delivery_data["delivered"])
        with col2:
            st.metric("🟡 Pending", delivery_data["pending"])
        with col3:
            st.metric("💸 Cancelled (refund pending)", delivery_data["cancelled"])
        st.divider()
        # MONTHLY REPORT (ORDERS + REVENUE + CUSTOMERS IN ONE TABLE)
        st.subheader("📅 Monthly Growth Report")
        monthly_rows = report_service.get_monthly_report()
        if monthly_rows:
            monthly_df = pd.DataFrame([
                {
                    "Month": row["month"],
                    "Orders": row["orders"],
                    "Revenue (₹)": round(row["revenue"], 2),
                    "Customers": row["customers"],
                    "New Customers": row["new_customers"],
                    "Revenue Growth (%)": (
                        round(row["growth"], 1)
                        if row["growth"] is not None else None
                    )
                }
                for row in monthly_rows
            ])
            monthly_df.index = range(1, len(monthly_df) + 1)
            monthly_df.index.name = "No."
            st.dataframe(monthly_df, use_container_width=True)
            st.download_button(
                "⬇️ Download Monthly Report (Excel)",
                to_excel_bytes(monthly_df, "Monthly Report"),
                file_name="monthly_report.xlsx",
                mime=EXCEL_MIME,
                key="download_monthly_report"
            )
            st.caption(
                "Customers = different customers who ordered. "
                "New Customers = accounts registered in that month. "
                "Cancelled orders are not counted."
            )
        else:
            st.info("No monthly data available yet.")
        st.divider()
        # DAILY REPORT (SAME FORMAT AS MONTHLY)
        st.subheader("🗓️ Daily Report")
        today = now_ist().date()
        date_range = st.date_input(
            "Select date range",
            value=(today - timedelta(days=29), today),
            max_value=today,
            key="daily_report_range"
        )
        if isinstance(date_range, (list, tuple)):
            if len(date_range) == 2:
                start_date, end_date = date_range
            elif len(date_range) == 1:
                start_date = end_date = date_range[0]
            else:
                start_date = end_date = today
        else:
            start_date = end_date = date_range
        if (end_date - start_date).days > 366:
            st.warning("Please select a range of up to 1 year.")
        else:
            daily_rows = report_service.get_daily_report(start_date, end_date)
            daily_df = pd.DataFrame([
                {
                    "Date": row["date"],
                    "Orders": row["orders"],
                    "Revenue (₹)": round(row["revenue"], 2),
                    "Customers": row["customers"],
                    "New Customers": row["new_customers"]
                }
                for row in daily_rows
            ])
            total_orders_range = int(daily_df["Orders"].sum())
            total_revenue_range = float(daily_df["Revenue (₹)"].sum())
            col1, col2 = st.columns(2)
            with col1:
                st.metric("📦 Orders in range", total_orders_range)
            with col2:
                st.metric("💰 Revenue in range", f"₹{total_revenue_range:,.2f}")
            daily_df.index = range(1, len(daily_df) + 1)
            daily_df.index.name = "No."
            st.dataframe(daily_df, use_container_width=True)
            st.download_button(
                "⬇️ Download Daily Report (Excel)",
                to_excel_bytes(daily_df, "Daily Report"),
                file_name="daily_report.xlsx",
                mime=EXCEL_MIME,
                key="download_daily_report"
            )
    # DELIVERY BOY MANAGEMENT
    if section == "delivery":
        st.subheader("🚴 Delivery Boy Management")
        st.write("Create a new Delivery Boy account.")
        with st.form("create_delivery_boy_form"):
            name = st.text_input("Delivery Boy Name")
            email = st.text_input("Email Address")
            phone = st.text_input(
                "Mobile Number",
                placeholder="10-digit number starting with 6, 7, 8 or 9",
                help="Customers will see this number to call the Delivery Boy."
            )
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button(
                "Create Delivery Boy Account",
                type="primary",
                use_container_width=True
            )
        if submitted:
            phone_ok, phone_result = validate_mobile(phone)
            name_ok, name_result = validate_name(name)
            if not name_ok:
                st.error(name_result)
            elif not email.strip():
                st.error("Please enter email address.")
            elif not phone_ok:
                st.error(phone_result)
            elif len(password) < 6:
                st.error("Password must contain at least 6 characters.")
            elif password != confirm_password:
                st.error("Passwords do not match.")
            else:
                success, message = auth_service.register_delivery_boy(
                    name.strip(),
                    email.strip(),
                    password,
                    user,
                    phone
                )
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
        st.divider()
        st.subheader("📋 Delivery Boy Accounts")
        delivery_boys = auth_service.get_delivery_boys()
        if delivery_boys:
            for boy in delivery_boys:
                with st.container(border=True):
                    st.write(f"**🚴 {display_name(boy['name'])}**")
                    st.write(f"Email: {boy['email']}")
                    if boy["phone"]:
                        st.markdown(tel_link(boy["phone"]))
                    else:
                        st.warning(
                            "Mobile number not added. Customers cannot "
                            "call this Delivery Boy. Please add it below."
                        )
                    st.caption(f"Delivery Boy ID: {boy['user_id']}")
                    with st.expander("📞 Add / change mobile number"):
                        with st.form(f"phone_form_{boy['user_id']}"):
                            new_phone = st.text_input(
                                "Mobile Number",
                                value=boy["phone"] or "",
                                key=f"phone_input_{boy['user_id']}"
                            )
                            save_phone = st.form_submit_button("Save Number", type="primary")
                        if save_phone:
                            success, message = (
                                auth_service.update_delivery_boy_phone(
                                    boy["user_id"],
                                    new_phone,
                                    user
                                )
                            )
                            if success:
                                st.rerun()
                            else:
                                st.error(message)
                    with st.expander("🗑️ Remove this Delivery Boy"):
                        st.write(
                            "The account is closed and the Delivery Boy can no longer "
                            "log in or get order emails. Old "
                            "deliveries stay in the records."
                        )
                        sure = st.checkbox(
                            f"Yes, remove {display_name(boy['name'])}",
                            key=f"sure_remove_{boy['user_id']}"
                        )
                        if st.button(
                            "🗑️ Remove Delivery Boy",
                            key=f"remove_boy_{boy['user_id']}",
                            disabled=not sure
                        ):
                            success, message = (
                                auth_service.remove_delivery_boy(
                                    boy["user_id"],
                                    user
                                )
                            )
                            if success:
                                st.toast(message, icon="🗑️")
                                st.rerun()
                            else:
                                st.error(message)
        else:
            st.info("No Delivery Boy accounts created yet.")
    # CUSTOMER FEEDBACK
    if section == "feedback":
        _feedback_section(feedback_service)
