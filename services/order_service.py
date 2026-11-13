from config.app_config import DELIVERY_CHARGE
from utils.time_utils import now_iso

class OrderService:
    VALID_STATUSES = [
        "PLACED",
        "CONFIRMED",
        "PREPARING",
        "OUT_FOR_DELIVERY",
        "DELIVERED",
        "CANCELLED"
    ]
    STATUS_ORDER = ["PLACED", "CONFIRMED", "PREPARING", "OUT_FOR_DELIVERY", "DELIVERED"]
    ALLOWED_PAYMENT_METHODS = ["UPI", "CASH_ON_DELIVERY"]

    def selectable_statuses(self, current, has_delivery_boy):
        """Statuses the Cafe Owner may choose: only forward, and OUT_FOR_DELIVERY / DELIVERED only
        after a Delivery Boy has accepted the order."""
        forward = self.STATUS_ORDER[self.STATUS_ORDER.index(current):] if current in self.STATUS_ORDER else [current]
        if not has_delivery_boy:
            forward = [s for s in forward if s == current or s not in ("OUT_FOR_DELIVERY", "DELIVERED")]
        return forward + ["CANCELLED"]

    def __init__(self, database, notifier=None):
        self.database = database
        self.notifier = notifier
        self.purge_cancelled_orders()

    def _notify(self, method_name, order_id):
        """Email notification. Never breaks the order flow."""
        if self.notifier is None:
            return
        try:
            getattr(self.notifier, method_name)(order_id)
        except Exception:
            pass

    # CANCELLED ORDERS - REMOVE FROM DATABASE
    #
    # A cancelled order has no value for reports or history, so it is
    # deleted completely (order, items, payment, delivery, feedback).
    #
    # Only exception: if the customer already PAID (payment SUCCESS),
    # the order is kept as CANCELLED until the Cafe Owner refunds the
    # money and presses "Refund done". This protects the customer's money.
    @staticmethod
    def _delete_order_rows(cursor, order_id):
        cursor.execute("DELETE FROM feedback WHERE order_id = ?", (order_id,))
        cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        cursor.execute("DELETE FROM payments WHERE order_id = ?", (order_id,))
        cursor.execute("DELETE FROM deliveries WHERE order_id = ?", (order_id,))
        cursor.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))

    def _cancel_with_cursor(self, cursor, order_id):
        """Cancel one order. Returns (deleted, message)."""
        cursor.execute("""SELECT status
            FROM payments
            WHERE order_id = ?""", (order_id,))
        payment = cursor.fetchone()
        already_paid = (payment is not None and payment["status"] == "SUCCESS")
        if already_paid:
            cursor.execute("""UPDATE orders
                SET status = 'CANCELLED'
                WHERE order_id = ?""", (order_id,))
            cursor.execute("""UPDATE deliveries
                SET status = 'CANCELLED', delivery_time = NULL, delivery_boy_id = NULL
                WHERE order_id = ?""", (order_id,))
            return False, ("Order cancelled. Your payment will be refunded " "by the cafe.")
        self._delete_order_rows(cursor, order_id)
        return True, "Order cancelled and removed successfully."

    def purge_cancelled_orders(self):
        """Delete old cancelled orders that need no refund."""
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT o.order_id
                FROM orders o
                LEFT JOIN payments p ON o.order_id = p.order_id
                WHERE o.status = 'CANCELLED' AND COALESCE(p.status, '') != 'SUCCESS'""")
            for row in cursor.fetchall():
                self._delete_order_rows(cursor, row["order_id"])
            connection.commit()
        except Exception:
            connection.rollback()
        finally:
            connection.close()

    def mark_refunded(self, order_id):
        """Cafe Owner pressed 'Refund done' - remove the cancelled order."""
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT status
                FROM orders
                WHERE order_id = ?""", (order_id,))
            order = cursor.fetchone()
            if order is None:
                return False, "Order not found."
            if order["status"] != "CANCELLED":
                return False, "Only cancelled orders can be marked refunded."
            self._delete_order_rows(cursor, order_id)
            connection.commit()
            return True, "Refund recorded and order removed."
        except Exception as error:
            connection.rollback()
            return False, f"Could not update order: {error}"
        finally:
            connection.close()

    # CREATE ORDER
    def create_order(
        self,
        customer_id,
        cart,
        payment_method,
        payment_status,
        delivery_address,
        customer_phone="",
        payment_screenshot=None,
        screenshot_hash=None
    ):
        if not cart.items:
            return False, "Cart is empty.", None
        if not delivery_address or not delivery_address.strip():
            return False, "Delivery address is required.", None
        payment_method = payment_method.strip().upper()
        if payment_method not in self.ALLOWED_PAYMENT_METHODS:
            return False, "Only UPI and Cash on Delivery are allowed.", None
        # Payment is always PENDING when the order is placed. For UPI the
        # Cafe Owner checks the screenshot and then confirms the order.
        if payment_method == "UPI":
            payment_status = "PENDING"
        elif payment_method == "CASH_ON_DELIVERY":
            payment_status = "PENDING"
            payment_screenshot = None
            screenshot_hash = None
        subtotal = cart.get_subtotal()
        delivery_charge = DELIVERY_CHARGE
        total_amount = subtotal + delivery_charge
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            # prices and availability are read again from the menu (the owner may have changed them)
            gone, changed = [], []
            for item in cart.items:
                row = cursor.execute("SELECT price, available FROM menu_items WHERE item_id = ?", (item.item_id,)).fetchone()
                if row is None or not row["available"]:
                    gone.append(item.name)
                elif abs(row["price"] - item.price) > 0.001:
                    changed.append(f"{item.name} (₹{item.price:.2f} -> ₹{row['price']:.2f})")
                    item.price = row["price"]                      # the cart now shows the new price
            if gone:
                return False, f"Not available now: {', '.join(gone)}. Please remove it from your cart.", None
            if changed:
                return False, ("The price changed for " + ", ".join(changed) +
                               ". Your cart is updated. Please check it and place the order again."), None
            # the same screenshot cannot be used for two orders
            if screenshot_hash:
                cursor.execute("""SELECT 1
                    FROM payments
                    WHERE screenshot_hash = ?""", (screenshot_hash,))
                if cursor.fetchone():
                    return False, (
                        "This screenshot was already used for another "
                        "order. Please upload your own payment screenshot."
                    ), None
            created_at = now_iso()
            # INSERT ORDER
            cursor.execute("""INSERT INTO orders ( customer_id, total_amount, status,
                    created_at, delivery_address, customer_phone )
                VALUES (?, ?, ?, ?, ?, ?)""", (
                customer_id,
                total_amount,
                "PLACED",
                created_at,
                delivery_address.strip(),
                (customer_phone or "").strip()
            ))
            order_id = cursor.lastrowid
            # INSERT ORDER ITEMS
            for item in cart.items:
                cursor.execute("""INSERT INTO order_items ( order_id, item_id, quantity, price,
                        item_name )
                    VALUES (?, ?, ?, ?, ?)""", (
                    order_id,
                    item.item_id,
                    item.quantity,
                    item.price,
                    item.name
                ))
            # INSERT PAYMENT
            cursor.execute("""INSERT INTO payments ( order_id, amount, method, status,
                    screenshot, screenshot_hash )
                VALUES (?, ?, ?, ?, ?, ?)""", (
                order_id,
                total_amount,
                payment_method,
                payment_status,
                payment_screenshot,
                screenshot_hash
            ))
            # INSERT DELIVERY
            cursor.execute("""INSERT INTO deliveries ( order_id, status )
                VALUES (?, ?)""", (
                order_id,
                "PENDING"
            ))
            connection.commit()
            # email the Cafe Owner: new order, please confirm
            self._notify("notify_new_order", order_id)
            return True, "Order placed successfully.", order_id
        except Exception as error:
            connection.rollback()
            return False, f"Order creation failed: {error}", None
        finally:
            connection.close()

    # CUSTOMER - MY ORDERS
    def get_customer_orders(self, customer_id):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT o.order_id, (SELECT COUNT(*) FROM orders ox WHERE
                    ox.order_id <= o.order_id) AS order_no, (SELECT COUNT(*) FROM
                    orders cx WHERE cx.customer_id = o.customer_id AND cx.order_id <=
                    o.order_id) AS customer_order_no, o.customer_id, o.total_amount,
                    o.status, o.created_at, o.delivery_address, d.status AS
                    delivery_status, d.delivery_time, d.delivery_boy_id,
                    delivery_boy.name AS delivery_boy_name, delivery_boy.phone AS
                    delivery_boy_phone, p.method AS payment_method, p.status AS
                    payment_status
                FROM orders o
                LEFT JOIN deliveries d ON o.order_id = d.order_id
                LEFT JOIN users delivery_boy ON d.delivery_boy_id = delivery_boy.user_id
                LEFT JOIN payments p ON o.order_id = p.order_id
                WHERE o.customer_id = ?
                ORDER BY o.order_id DESC""", (customer_id,))
            return cursor.fetchall()
        finally:
            connection.close()

    # DISPLAY NUMBER OF AN ORDER
    #
    # The order number shown to users is the position of the order among
    # the existing orders (1, 2, 3 ...). When an earlier order is deleted,
    # the later orders move up automatically (#3 becomes #1).
    # The internal order_id never changes, so buttons always act on the
    # correct order.
    def get_order_number(self, order_id):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT COUNT(*) AS number
                FROM orders
                WHERE order_id <= ?""", (order_id,))
            return cursor.fetchone()["number"]
        finally:
            connection.close()

    def get_customer_order_number(self, order_id):
        """Number of the order among the orders of the SAME customer.

        The first order of a customer is #1, the second #2 ... This is
        the number the customer sees. Cafe Owner and Delivery Boys see
        get_order_number() (position among all orders).
        """
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT COUNT(*) AS number
                FROM orders
                WHERE customer_id = ( SELECT customer_id FROM orders WHERE order_id = ? ) AND
                    order_id <= ?""", (order_id, order_id))
            return cursor.fetchone()["number"]
        finally:
            connection.close()

    def get_payment_screenshot(self, order_id):
        """Payment screenshot (JPEG bytes) of an order, or None."""
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT screenshot
                FROM payments
                WHERE order_id = ?""", (order_id,))
            row = cursor.fetchone()
            return row["screenshot"] if row else None
        finally:
            connection.close()

    # FOOD ITEMS OF ORDERS (NAME + QUANTITY)
    def get_items_for_orders(self, order_ids):
        """Return {order_id: [ {name, quantity, price}, ... ]}."""
        order_ids = list(order_ids)
        if not order_ids:
            return {}
        placeholders = ",".join("?" for _ in order_ids)
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(f"""
                SELECT
                    oi.order_id,
                    COALESCE(
                        oi.item_name,
                        m.name,
                        'Food item #' || oi.item_id
                    ) AS name,
                    oi.quantity,
                    oi.price

                FROM order_items oi

                LEFT JOIN menu_items m
                    ON oi.item_id = m.item_id

                WHERE oi.order_id IN ({placeholders})

                ORDER BY oi.order_item_id
            """, order_ids)
            items = {}
            for row in cursor.fetchall():
                items.setdefault(row["order_id"], []).append({
                    "name": row["name"],
                    "quantity": row["quantity"],
                    "price": row["price"]
                })
            return items
        finally:
            connection.close()

    # CUSTOMER - CANCEL ORDER
    def cancel_order(self, order_id, customer_id):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            # Only the owner can cancel their order.
            # Cancellation allowed before preparation.
            cursor.execute("""SELECT status
                FROM orders
                WHERE order_id = ? AND customer_id = ?""", (order_id, customer_id))
            order = cursor.fetchone()
            if order is None or order["status"] not in ("PLACED", "CONFIRMED"):
                return False, (
                    "Order cannot be cancelled. "
                    "It may already be preparing, delivered, "
                    "cancelled, or may not belong to you."
                )
            deleted, message = self._cancel_with_cursor(cursor, order_id)
            connection.commit()
            return True, message
        except Exception as error:
            connection.rollback()
            return False, f"Order cancellation failed: {error}"
        finally:
            connection.close()

    # GET SINGLE ORDER
    def get_order(self, order_id):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT o.order_id, (SELECT COUNT(*) FROM orders ox WHERE
                    ox.order_id <= o.order_id) AS order_no, (SELECT COUNT(*) FROM
                    orders cx WHERE cx.customer_id = o.customer_id AND cx.order_id <=
                    o.order_id) AS customer_order_no, o.customer_id, o.total_amount,
                    o.status, o.created_at, o.delivery_address, d.status AS
                    delivery_status, d.delivery_time, d.delivery_boy_id,
                    delivery_boy.name AS delivery_boy_name, delivery_boy.email AS
                    delivery_boy_email, delivery_boy.phone AS delivery_boy_phone,
                    p.method AS payment_method, p.status AS payment_status
                FROM orders o
                LEFT JOIN deliveries d ON o.order_id = d.order_id
                LEFT JOIN users delivery_boy ON d.delivery_boy_id = delivery_boy.user_id
                LEFT JOIN payments p ON o.order_id = p.order_id
                WHERE o.order_id = ?""", (order_id,))
            return cursor.fetchone()
        finally:
            connection.close()

    # CAFE - GET ALL ORDERS
    def get_all_orders(self):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT o.order_id, (SELECT COUNT(*) FROM orders ox WHERE
                    ox.order_id <= o.order_id) AS order_no, (SELECT COUNT(*) FROM
                    orders cx WHERE cx.customer_id = o.customer_id AND cx.order_id <=
                    o.order_id) AS customer_order_no, o.customer_id, u.name AS
                    customer_name, u.email AS customer_email, o.customer_phone,
                    u.phone AS customer_account_phone, o.total_amount, o.status AS
                    order_status, o.created_at, o.delivery_address, p.method AS
                    payment_method, p.status AS payment_status, d.status AS
                    delivery_status, d.delivery_time, d.delivery_boy_id,
                    delivery_boy.name AS delivery_boy_name, delivery_boy.email AS
                    delivery_boy_email, delivery_boy.phone AS delivery_boy_phone
                FROM orders o
                JOIN users u ON o.customer_id = u.user_id
                LEFT JOIN payments p ON o.order_id = p.order_id
                LEFT JOIN deliveries d ON o.order_id = d.order_id
                LEFT JOIN users delivery_boy ON d.delivery_boy_id = delivery_boy.user_id
                ORDER BY o.order_id DESC""")
            return cursor.fetchall()
        finally:
            connection.close()

    # CAFE - UPDATE ORDER STATUS
    def update_status(self, order_id, new_status):
        new_status = new_status.strip().upper()
        if new_status not in self.VALID_STATUSES:
            return False, "Invalid order status."
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT o.status, p.method AS payment_method, p.status AS
                    payment_status, d.delivery_boy_id
                FROM orders o
                LEFT JOIN payments p ON o.order_id = p.order_id
                LEFT JOIN deliveries d ON o.order_id = d.order_id
                WHERE o.order_id = ?""", (order_id,))
            existing_order = cursor.fetchone()
            if existing_order is None:
                return False, "Order not found."
            current_status = existing_order["status"]
            # Do not reopen a cancelled or delivered order.
            if current_status in ["CANCELLED", "DELIVERED"]:
                return False, f"Cannot change an order that is {current_status.lower()}."
            # CANCELLED: remove from database (refund case is kept)
            if new_status == "CANCELLED":
                deleted, message = self._cancel_with_cursor(cursor, order_id)
                connection.commit()
                return True, message
            # Only forward; OUT_FOR_DELIVERY / DELIVERED need a Delivery Boy who accepted the order.
            if self.STATUS_ORDER.index(new_status) < self.STATUS_ORDER.index(current_status):
                return False, "An order cannot go back to an earlier status."
            if new_status in ("OUT_FOR_DELIVERY", "DELIVERED") and not existing_order["delivery_boy_id"]:
                return False, "A Delivery Boy must accept the order first."
            # An order with a UPI payment can go forward (and reach the
            # Delivery Boys) only after the Cafe Owner verified the payment.
            if (
                new_status != "PLACED"
                and existing_order["payment_method"] == "UPI"
                and existing_order["payment_status"] != "SUCCESS"
            ):
                return False, (
                    "UPI payment is not verified yet. Check the payment "
                    "screenshot and press 'Verify Payment & Confirm "
                    "Order' first."
                )
            # UPDATE ORDER
            cursor.execute("""UPDATE orders
                SET status = ?
                WHERE order_id = ?""", (
                new_status,
                order_id
            ))
            # UPDATE DELIVERY STATUS
            if new_status == "DELIVERED":
                delivery_status = "DELIVERED"
                delivery_time = now_iso()
            elif new_status == "CANCELLED":
                delivery_status = "CANCELLED"
                delivery_time = None
            elif new_status == "OUT_FOR_DELIVERY":
                delivery_status = "OUT_FOR_DELIVERY"
                delivery_time = None
            else:
                delivery_status = "PENDING"
                delivery_time = None
            cursor.execute("""UPDATE deliveries
                SET status = ?, delivery_time = ?
                WHERE order_id = ?""", (
                delivery_status,
                delivery_time,
                order_id
            ))
            connection.commit()
            # Delivery Boys are informed when the order gets confirmed
            if current_status == "PLACED" and new_status in ("CONFIRMED", "PREPARING"):
                self._notify("notify_order_confirmed", order_id)
            return True, "Order status updated successfully."
        except Exception as error:
            connection.rollback()
            return False, f"Status update failed: {error}"
        finally:
            connection.close()

    # CAFE OWNER: CONFIRM ORDER (VERIFIES UPI PAYMENT)
    def confirm_order(self, order_id):
        """Confirm a PLACED order.

        For UPI orders this also marks the payment as verified (SUCCESS).
        After this the order is visible to the Delivery Boys and they get
        an email.
        """
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT o.status, p.method AS payment_method, p.status AS
                    payment_status
                FROM orders o
                LEFT JOIN payments p ON o.order_id = p.order_id
                WHERE o.order_id = ?""", (order_id,))
            order = cursor.fetchone()
            if order is None:
                return False, "Order not found."
            if order["status"] != "PLACED":
                return False, "This order is already confirmed or closed."
            if order["payment_method"] == "UPI":
                if order["payment_status"] == "FAILED":
                    return False, (
                        "This UPI payment was marked as failed. "
                        "Cancel the order instead."
                    )
                cursor.execute("""UPDATE payments
                    SET status = 'SUCCESS'
                    WHERE order_id = ?""", (order_id,))
                connection.commit()
        except Exception as error:
            connection.rollback()
            return False, f"Could not confirm the order: {error}"
        finally:
            connection.close()
        return self.update_status(order_id, "CONFIRMED")

    # TOTAL ORDER COUNT
    def get_order_count(self):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT COUNT(*) AS total
                FROM orders""")
            row = cursor.fetchone()
            return row["total"]
        finally:
            connection.close()

    # ORDER STATUS COUNT
    def get_status_count(self, status):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT COUNT(*) AS total
                FROM orders
                WHERE status = ?""", (status,))
            row = cursor.fetchone()
            return row["total"]
        finally:
            connection.close()
