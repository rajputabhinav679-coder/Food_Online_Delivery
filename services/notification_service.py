"""Email notifications for cafe orders.

Notification flow:
    1. Customer places an order -> configured Cafe Owner email.
    2. Cafe Owner confirms the order -> every active Delivery Boy account
       with a registered email address.

Delivery Boys can then accept the available order in their dashboard; the
first one to accept it becomes assigned to that order. This module sends
EMAIL only. A phone number is included in the delivery email for calling,
but SMS requires a separate SMS gateway and credentials.
"""
import smtplib
import ssl
import threading
from email.message import EmailMessage
from config.email_config import load_email_settings, is_configured
from utils.validators import area_of
from utils.time_utils import now_iso

class NotificationService:
    def __init__(self, database, settings_loader=None, background=True):
        self.database = database
        self.settings_loader = settings_loader or load_email_settings
        self.background = background

    # Configuration and recipient information (also used by Cafe UI)
    def is_configured(self):
        return is_configured(self.settings_loader())

    # Notifications
    def notify_new_order(self, order_id):
        """Send a new-order notification to the configured Cafe Owner."""
        try:
            settings = self.settings_loader()
            order = self._load_order(order_id)
            if order is None:
                self._log("new_order", "", "New order", "FAILED", "Order not found.")
                return
            recipients = self._cafe_recipients(settings)
            number = order["order_no"]
            lines = [
                f"New order #{number} received - Food Online Cafe",
                "",
                f"Customer: {order['customer_name']}",
                f"Customer email: {order.get('customer_email') or 'N/A'}",
                f"Customer mobile: {order.get('customer_phone') or 'N/A'}",
                "",
                "Food ordered:",
            ]
            lines.extend(self._item_lines(order["items"]))
            lines.extend([
                "",
                f"Total: ₹{order['total_amount']:.2f} (including delivery charge)",
                f"Delivery address: {order.get('delivery_address') or 'N/A'}",
                "",
            ])
            attachments = []
            method = (order.get("method") or "").upper()
            payment_status = (order.get("payment_status") or "PENDING").upper()
            if method == "UPI":
                lines.append(f"Payment: UPI ({payment_status})")
                if order.get("screenshot"):
                    lines.append("The customer's payment screenshot is attached for verification.")
                    attachments.append((f"payment_order_{number}.jpg", order["screenshot"]))
                lines.append("Please verify the actual UPI transaction before confirming the order.")
            else:
                lines.append("Payment: Cash on Delivery")
            lines.extend([
                "",
                "Next step: open Cafe Owner Dashboard -> Order Management and confirm the order.",
                "Active Delivery Boys are notified by email only after confirmation.",
            ])
            if settings.get("app_url"):
                lines.extend(["", f"Open the app: {settings['app_url']}"])
            self._send(
                settings,
                "new_order",
                recipients,
                f"New order #{number} - please confirm",
                "\n".join(lines),
                attachments,
            )
            # Send a separate receipt to the customer, if the customer has
            # supplied an email address. Never attach the payment screenshot.
            customer_email = (order.get("customer_email") or "").strip()
            if customer_email:
                customer_lines = [
                    f"Thank you, {order['customer_name']}!",
                    f"Your order #{order['customer_order_no']} has been received.",
                    "",
                    "Order items:",
                ]
                customer_lines.extend(self._item_lines(order["items"]))
                customer_lines.extend([
                    "",
                    f"Total: ₹{order['total_amount']:.2f}",
                    f"Delivery address: {order.get('delivery_address') or 'N/A'}",
                    "The cafe will confirm your order shortly.",
                ])
                self._send(
                    settings,
                    "customer_order_receipt",
                    [customer_email],
                    f"Order #{order['customer_order_no']} received - Food Online Cafe",
                    "\n".join(customer_lines),
                    [],
                )
        except Exception as error:
            self._log("new_order", "", "New order notification", "FAILED", str(error))

    def notify_order_confirmed(self, order_id):
        """Notify all active Delivery Boys after the cafe confirms an order."""
        try:
            settings = self.settings_loader()
            order = self._load_order(order_id)
            if order is None:
                self._log("order_confirmed", "", "Order confirmed", "FAILED", "Order not found.")
                return
            recipients = self._delivery_recipients()
            number = order["order_no"]
            method = (order.get("method") or "").upper()
            payment_status = (order.get("payment_status") or "PENDING").upper()
            lines = [
                f"Order #{number} has been confirmed by the cafe.",
                "",
                f"Delivery area: {area_of(order.get('delivery_address'))}",
                "",
                "Food to deliver:",
            ]
            lines.extend(self._item_lines(order["items"]))
            lines.extend([
                "",
                f"Amount: ₹{order['total_amount']:.2f}",
                f"Payment: {method or 'N/A'} ({payment_status})",
                "",
                "Open the Delivery Boy Dashboard -> Available Orders and accept this order.",
                "The customer's name, mobile number and full address are shown in the app after you accept.",
                "The first active Delivery Boy who accepts it will be assigned to the order.",
            ])
            if method == "CASH_ON_DELIVERY" and payment_status != "SUCCESS":
                lines.append(f"Cash to collect from customer: ₹{order['total_amount']:.2f}")
            if settings.get("app_url"):
                lines.extend(["", f"Open the app: {settings['app_url']}"])
            self._send(
                settings,
                "order_confirmed",
                recipients,
                f"Order #{number} confirmed - available for delivery",
                "\n".join(lines),
                [],
            )
        except Exception as error:
            self._log("order_confirmed", "", "Order confirmation notification", "FAILED", str(error))

    def notify_password_changed(self, recipient, name):
        """Security mail: the password of this account was changed."""
        self._send(self.settings_loader(), "password_changed", [recipient],
                   "Your password was changed - Food Online Cafe",
                   f"Hello {name},\n\nThe password of your Food Online Cafe account was just changed.\n"
                   "If this was not you, please contact the cafe immediately.", [])

    # Recipient helpers
    def _cafe_recipients(self, settings):
        # An explicit [email].cafe_email is the notification override.
        # Otherwise config/email_config.py uses [auth].cafe_email; if that
        # is also absent, fall back to the Cafe Owner account in the DB.
        configured_email = (settings.get("cafe_email") or "").strip()
        if configured_email:
            return [configured_email]
        return self._emails_of_role("cafe")

    def _delivery_recipients(self):
        return self._emails_of_role("delivery_boy")

    def _emails_of_role(self, role):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT DISTINCT TRIM(email) AS email
                    FROM users
                    WHERE role = ? AND is_active = 1 AND email IS NOT NULL AND TRIM(email) != ''
                        AND INSTR(email, '@') > 1
                    ORDER BY email""",
                (role,),
            )
            return [row["email"] for row in cursor.fetchall()]
        finally:
            connection.close()

    # Order details
    def _load_order(self, order_id):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT o.order_id, (SELECT COUNT(*) FROM orders ox WHERE ox.order_id <=
                        o.order_id) AS order_no, (SELECT COUNT(*) FROM orders cx WHERE cx.customer_id
                        = o.customer_id AND cx.order_id <= o.order_id) AS customer_order_no,
                        o.total_amount, o.delivery_address, o.customer_phone, u.name AS
                        customer_name, u.email AS customer_email, p.method, p.status AS
                        payment_status, p.screenshot
                    FROM orders o
                    JOIN users u ON o.customer_id = u.user_id
                    LEFT JOIN payments p ON o.order_id = p.order_id
                    WHERE o.order_id = ?""",
                (order_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            order = dict(row)
            cursor.execute(
                """SELECT COALESCE(oi.item_name, m.name, 'Food item #' || oi.item_id) AS name,
                        oi.quantity, oi.price
                    FROM order_items oi
                    LEFT JOIN menu_items m ON oi.item_id = m.item_id
                    WHERE oi.order_id = ?
                    ORDER BY oi.order_item_id""",
                (order_id,),
            )
            order["items"] = [dict(item) for item in cursor.fetchall()]
            return order
        finally:
            connection.close()

    @staticmethod
    def _item_lines(items):
        return [
            f"  - {item['name']} x {item['quantity']} "
            f"(₹{item['price'] * item['quantity']:.2f})"
            for item in items
        ]

    # SMTP sending and delivery log
    def _send(self, settings, kind, recipients, subject, body, attachments):
        recipients = list(dict.fromkeys(
            str(address).strip() for address in (recipients or [])
            if str(address or "").strip()
        ))
        joined = ", ".join(recipients)
        if not recipients:
            self._log(
                kind, "", subject, "SKIPPED",
                "No valid recipient email found. Check Cafe Owner / Delivery Boy account emails.",
            )
            return
        if not is_configured(settings):
            self._log(
                kind, joined, subject, "SKIPPED",
                "SMTP is not configured. Set [email].sender and [email].app_password.",
            )
            return
        def work():
            try:
                self._smtp_send(settings, recipients, subject, body, attachments)
                self._log(kind, joined, subject, "SENT", "")
            except Exception as error:
                self._log(kind, joined, subject, "FAILED", str(error))
        if self.background:
            threading.Thread(target=work, daemon=True, name=f"email-{kind}").start()
        else:
            work()

    @staticmethod
    def _smtp_send(settings, recipients, subject, body, attachments):
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings["sender"]
        message["To"] = ", ".join(recipients)
        message.set_content(body)
        for filename, data in attachments:
            message.add_attachment(data, maintype="image", subtype="jpeg", filename=filename)
        host = settings.get("smtp_host", "smtp.gmail.com")
        port = int(settings.get("smtp_port", 587))
        context = ssl.create_default_context()
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            server.starttls(context=context)
        try:
            server.login(settings["sender"], settings["app_password"])
            server.send_message(message)
        finally:
            server.quit()

    def _log(self, kind, recipient, subject, status, error):
        try:
            connection = self.database.get_connection()
            try:
                connection.execute(
                    """INSERT INTO notification_log (kind, recipient, subject, status, error,
                            created_at)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                    (kind, recipient, subject, status, error, now_iso()),
                )
                connection.commit()
            finally:
                connection.close()
        except Exception:
            # Notification logging must never break placing/confirming orders.
            pass
