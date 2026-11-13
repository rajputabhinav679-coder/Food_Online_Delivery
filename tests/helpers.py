"""Shared set-up for the tests: a fresh database with a few users and food items."""
import os
import shutil
import tempfile
import unittest

from database.database import Database
from services.auth_service import AuthService
from services.cart_service import CartService  # noqa: F401  (needs Streamlit only when used)
from services.delivery_service import DeliveryService
from services.feedback_service import FeedbackService
from services.menu_service import MenuService
from services.notification_service import NotificationService
from services.order_service import OrderService
from models.cart import Cart

class SentMail:
    """Collects the mails instead of sending them."""
    def __init__(self):
        self.mails = []

    def install(self, notifier):
        def fake_send(settings, kind, recipients, subject, body, attachments):
            self.mails.append({"kind": kind, "to": list(recipients), "subject": subject, "body": body})
        notifier._send = fake_send
        return self

class ShopTestCase(unittest.TestCase):
    """Every test gets its own empty database in a temporary folder."""

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.db = Database(os.path.join(self.folder, "test.db"))
        self.mail = SentMail()
        settings = lambda: {"sender": "", "app_password": "", "cafe_email": "owner@example.com",
                            "app_url": "", "smtp_host": "x", "smtp_port": 587}
        self.notifier = NotificationService(self.db, settings_loader=settings, background=False)
        self.mail.install(self.notifier)
        self.auth = AuthService(self.db, self.notifier)
        self.menu = MenuService(self.db)
        self.orders = OrderService(self.db, self.notifier)
        self.delivery = DeliveryService(self.db)
        self.feedback = FeedbackService(self.db)
        self.customer_id = self.add_user("Asha Rao", "asha@example.com", "customer")
        self.boy_id = self.add_user("Ravi Kumar", "ravi@example.com", "delivery_boy", "9876501234")
        self.pizza = self.add_food("Pizza", 100.0)
        self.burger = self.add_food("Burger", 60.0)

    # --- builders --------------------------------------------------------
    def add_user(self, name, email, role, phone="9123456780"):
        conn = self.db.get_connection()
        try:
            cur = conn.execute(
                "INSERT INTO users (name, email, password, role, phone) VALUES (?, ?, ?, ?, ?)",
                (name, email, "x", role, phone))
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def add_food(self, name, price, category="Other"):
        self.menu.add_item(name, category, price, "")
        return [i for i in self.menu.get_all_items() if i.name == name][0].item_id

    def menu_item(self, item_id):
        return [i for i in self.menu.get_all_items() if i.item_id == item_id][0]

    def cart_with(self, *item_ids):
        cart = Cart(self.customer_id)
        for item_id in item_ids:
            cart.add_item(self.menu_item(item_id), 1)
        return cart

    def place(self, cart=None, method="CASH_ON_DELIVERY"):
        cart = cart or self.cart_with(self.pizza)
        ok, message, order_id = self.orders.create_order(
            self.customer_id, cart, method, "PENDING", "1 Main Road, Rourkela - 769001", "9123456780")
        self.assertTrue(ok, message)
        return order_id

    def row(self, sql, *params):
        conn = self.db.get_connection()
        try:
            return conn.execute(sql, params).fetchone()
        finally:
            conn.close()

    def order_status(self, order_id):
        return self.row("SELECT status FROM orders WHERE order_id = ?", order_id)["status"]

    def count(self, table):
        return self.row(f"SELECT COUNT(*) AS n FROM {table}")["n"]

    def delivered_by_boy(self):
        """A full normal order: confirmed, accepted by the Delivery Boy, delivered."""
        order_id = self.place()
        self.assertTrue(self.orders.confirm_order(order_id)[0])
        self.assertTrue(self.delivery.accept_order(order_id, self.boy_id))
        self.assertTrue(self.delivery.mark_delivered(order_id, self.boy_id))
        return order_id
