"""Automatic tests of the project logic. Run in the project folder:   python -m unittest discover -s tests -v"""
import hashlib
import io
import os
import sqlite3
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import streamlit as st
except ImportError:                                   # tests also run without Streamlit installed
    st = sys.modules["streamlit"] = types.SimpleNamespace()


class SessionState(dict):
    __getattr__ = dict.get

    def __setattr__(self, key, value):
        self[key] = value


os.environ["CAFE_LOGIN_EMAIL"] = "owner@gmail.com"
os.environ["CAFE_LOGIN_PASSWORD"] = "Owner#12345"
from database.database import Database                                      # noqa: E402
from models.cart import Cart                                                # noqa: E402
from services.auth_service import AuthService                               # noqa: E402
from services.cart_service import CartService                               # noqa: E402
from services.delivery_service import DeliveryService                       # noqa: E402
from services.feedback_service import FeedbackService                       # noqa: E402
from services.menu_service import MenuService                               # noqa: E402
from services.notification_service import NotificationService               # noqa: E402
from services.order_service import OrderService                             # noqa: E402
from services.report_service import ReportService                           # noqa: E402
from utils.excel_utils import to_excel_bytes                                # noqa: E402
from utils.labels import label                                              # noqa: E402
from utils.validators import area_of, display_name, validate_mobile, validate_name, validate_password  # noqa: E402

ADDRESS = "RAM KUMAR, Mobile: 9812345609, 12 Rose Villa, Main Road, Bhubaneswar - 751001"


class Base(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.multiple(st, session_state=SessionState(), secrets={}, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = Database(os.path.join(self.folder.name, "test.db"))
        self.mails = []
        test = self

        class FakeMail(NotificationService):
            @staticmethod
            def _smtp_send(settings, recipients, subject, body, attachments):
                test.mails.append((recipients, subject, body))

        settings = {"sender": "s@gmail.com", "app_password": "x", "smtp_host": "h", "smtp_port": 587,
                    "cafe_email": "", "app_url": ""}
        self.notifier = FakeMail(self.db, settings_loader=lambda: dict(settings), background=False)
        self.auth = AuthService(self.db, self.notifier)
        self.orders = OrderService(self.db, self.notifier)
        self.menu = MenuService(self.db)
        self.delivery = DeliveryService(self.db)
        self.owner = self.auth.login("owner@gmail.com", "Owner#12345")
        self.assertTrue(self.auth.register_customer("Ram Kumar", "ram@gmail.com", "secret12", "9812345609")[0])
        self.ram = self.auth.login("ram@gmail.com", "secret12")
        self.assertTrue(self.auth.register_delivery_boy("Raju Singh", "raju@gmail.com", "secret12", self.owner, "9123456078")[0])
        self.boy = self.auth.login("raju@gmail.com", "secret12")
        self.menu.add_item("Burger", "Fast Food", 100, "tasty", True, None)
        self.item = [i for i in self.menu.get_all_items() if i.name == "Burger"][0]

    def place(self, method="CASH_ON_DELIVERY", quantity=1, item=None, customer=None):
        cart = Cart((customer or self.ram).user_id)
        cart.add_item(item or self.item, quantity)
        return self.orders.create_order((customer or self.ram).user_id, cart, method, "PENDING", ADDRESS, "9812345609")

    def available_ids(self):
        return [r["order_id"] for r in self.delivery.get_available_orders()]


class ValidatorTests(unittest.TestCase):
    def test_mobile_rules(self):
        self.assertEqual(validate_mobile("+91 98123 45609"), (True, "9812345609"))
        for bad in ("5812345609", "7777777777", "7888888888", "9876543210", "98123", "98123456090"):
            self.assertFalse(validate_mobile(bad)[0], bad)

    def test_name_rules(self):
        self.assertEqual(validate_name("  ram kumar "), (True, "RAM KUMAR"))
        for bad in ("Ram  Kumar", "Ram1", "R", ""):
            self.assertFalse(validate_name(bad)[0], bad)

    def test_text_helpers(self):
        self.assertFalse(validate_password("abc")[0])
        self.assertTrue(validate_password("abcdef")[0])
        self.assertEqual(display_name("  ram    kumar"), "RAM KUMAR")
        self.assertEqual(area_of(ADDRESS), "Bhubaneswar - 751001")
        self.assertEqual(label("CASH_ON_DELIVERY"), "Cash on Delivery (COD)")
        self.assertEqual(label("OUT_FOR_DELIVERY"), "Out for Delivery")
        self.assertEqual(label("delivery_boy"), "Delivery Boy")


class AuthTests(Base):
    def test_password_is_salted_hash(self):
        stored = sqlite3.connect(os.path.join(self.folder.name, "test.db")).execute(
            "SELECT password FROM users WHERE email = 'ram@gmail.com'").fetchone()[0]
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertNotIn(hashlib.sha256(b"secret12").hexdigest(), stored)
        self.assertIsNone(self.auth.login("ram@gmail.com", "wrong"))

    def test_old_hash_is_upgraded_at_login(self):
        path = os.path.join(self.folder.name, "test.db")
        with sqlite3.connect(path) as c:
            c.execute("UPDATE users SET password = ? WHERE email = 'ram@gmail.com'", (hashlib.sha256(b"secret12").hexdigest(),))
        self.assertIsNotNone(self.auth.login("ram@gmail.com", "secret12"))
        self.assertTrue(sqlite3.connect(path).execute("SELECT password FROM users WHERE email='ram@gmail.com'").fetchone()[0].startswith("pbkdf2_sha256$"))

    def test_lockout_after_five_wrong_passwords(self):
        for _ in range(5):
            self.auth.login("ram@gmail.com", "bad")
        self.assertGreater(self.auth.lockout_seconds("ram@gmail.com"), 0)
        self.assertIsNone(self.auth.login("ram@gmail.com", "secret12"))
        self.assertIsNotNone(self.auth.login("raju@gmail.com", "secret12"))

    def test_change_password(self):
        self.assertFalse(self.auth.change_password(self.ram.user_id, "wrong", "newpass1")[0])
        self.assertFalse(self.auth.change_password(self.ram.user_id, "secret12", "secret12")[0])
        self.assertTrue(self.auth.change_password(self.ram.user_id, "secret12", "newpass1")[0])
        self.assertIsNotNone(self.auth.login("ram@gmail.com", "newpass1"))
        self.assertIsNone(self.auth.login("ram@gmail.com", "secret12"))

    def test_delivery_boy_cannot_be_removed_with_active_order(self):
        order_id = self.place()[2]
        self.orders.confirm_order(order_id)
        self.delivery.accept_order(order_id, self.boy.user_id)
        self.assertFalse(self.auth.remove_delivery_boy(self.boy.user_id, self.owner)[0])
        self.delivery.mark_delivered(order_id, self.boy.user_id)
        self.assertTrue(self.auth.remove_delivery_boy(self.boy.user_id, self.owner)[0])
        self.assertIsNone(self.auth.login("raju@gmail.com", "secret12"))


class CartTests(Base):
    def test_maximum_ten_of_one_item(self):
        service = CartService()
        service.add_item(self.ram.user_id, self.item, 8)
        ok, message = service.add_item(self.ram.user_id, self.item, 5)
        self.assertEqual(service.get_quantity(self.ram.user_id, self.item.item_id), 10)
        self.assertIn("10", message)
        self.assertFalse(service.add_item(self.ram.user_id, self.item, 1)[0])
        service.update_quantity(self.ram.user_id, self.item.item_id, 50)
        self.assertEqual(service.get_quantity(self.ram.user_id, self.item.item_id), 10)


class OrderTests(Base):
    def test_changed_price_is_not_charged_silently(self):
        cart = Cart(self.ram.user_id)
        cart.add_item(self.item, 2)
        self.menu.update_item(self.item.item_id, "Burger", "Fast Food", 250, "tasty", True)
        ok, message, _ = self.orders.create_order(self.ram.user_id, cart, "CASH_ON_DELIVERY", "PENDING", ADDRESS, "9812345609")
        self.assertFalse(ok)
        self.assertIn("price changed", message)
        self.assertEqual(cart.items[0].price, 250)                       # the cart now shows the new price
        self.assertTrue(self.orders.create_order(self.ram.user_id, cart, "CASH_ON_DELIVERY", "PENDING", ADDRESS, "9812345609")[0])

    def test_unavailable_and_deleted_items_are_refused_politely(self):
        cart = Cart(self.ram.user_id)
        cart.add_item(self.item, 1)
        self.menu.update_item(self.item.item_id, "Burger", "Fast Food", 100, "tasty", False)
        ok, message, _ = self.orders.create_order(self.ram.user_id, cart, "CASH_ON_DELIVERY", "PENDING", ADDRESS, "9812345609")
        self.assertFalse(ok)
        self.assertIn("Not available", message)
        self.menu.add_item("Temp", "Snacks", 20, "x", True, None)
        temp = [i for i in self.menu.get_all_items() if i.name == "Temp"][0]
        self.menu.delete_item(temp.item_id)
        ok, message, _ = self.place(item=temp)
        self.assertFalse(ok)
        self.assertNotIn("FOREIGN KEY", message)

    def test_upi_order_reaches_delivery_boys_only_after_confirmation(self):
        order_id = self.place("UPI")[2]
        self.assertEqual(self.orders.get_order(order_id)["payment_status"], "PENDING")
        self.assertNotIn(order_id, self.available_ids())
        self.assertFalse(self.orders.update_status(order_id, "CONFIRMED")[0])
        self.assertTrue(self.orders.confirm_order(order_id)[0])
        self.assertEqual(self.orders.get_order(order_id)["payment_status"], "SUCCESS")
        self.assertIn(order_id, self.available_ids())

    def test_status_rules(self):
        order_id = self.place()[2]
        self.assertFalse(self.orders.update_status(order_id, "DELIVERED")[0])            # nobody delivered it
        self.assertFalse(self.orders.update_status(order_id, "OUT_FOR_DELIVERY")[0])
        self.orders.confirm_order(order_id)
        self.assertFalse(self.orders.update_status(order_id, "PLACED")[0])                # no way back
        self.assertEqual(self.orders.selectable_statuses("CONFIRMED", False), ["CONFIRMED", "PREPARING", "CANCELLED"])
        self.assertEqual(len(self.mails), 3)                                             # owner + customer receipt, then the boys once
        self.mails.clear()
        self.orders.update_status(order_id, "PREPARING")
        self.assertEqual(self.mails, [])                                                 # no repeated mail

    def test_numbers_cancel_and_refund(self):
        first, second = self.place()[2], self.place()[2]
        self.assertEqual([o["customer_order_no"] for o in self.orders.get_customer_orders(self.ram.user_id)], [2, 1])
        self.assertTrue(self.orders.cancel_order(first, self.ram.user_id)[0])
        self.assertEqual(self.orders.get_customer_orders(self.ram.user_id)[0]["customer_order_no"], 1)
        paid = self.place("UPI")[2]
        with sqlite3.connect(os.path.join(self.folder.name, "test.db")) as c:
            c.execute("UPDATE payments SET status = 'SUCCESS' WHERE order_id = ?", (paid,))
        self.orders.cancel_order(paid, self.ram.user_id)
        self.assertEqual(self.orders.get_order(paid)["status"], "CANCELLED")             # kept: refund pending
        self.assertTrue(self.orders.mark_refunded(paid)[0])
        self.assertIsNone(self.orders.get_order(paid))

    def test_full_delivery_and_feedback(self):
        order_id = self.place()[2]
        feedback = FeedbackService(self.db)
        self.assertFalse(feedback.submit_feedback(order_id, self.ram.user_id, 5, "x")[0])
        self.orders.confirm_order(order_id)
        self.assertTrue(self.delivery.accept_order(order_id, self.boy.user_id))
        self.assertTrue(self.delivery.mark_delivered(order_id, self.boy.user_id))
        self.assertTrue(feedback.submit_feedback(order_id, self.ram.user_id, 5, "great")[0])
        self.assertFalse(feedback.submit_feedback(order_id, self.ram.user_id, 4, "again")[0])

    def test_delivery_boys_get_no_customer_details(self):
        order_id = self.place()[2]
        self.mails.clear()
        self.orders.confirm_order(order_id)
        body = self.mails[-1][2]
        for secret in ("Rose Villa", "9812345609", "ram@gmail.com", "RAM KUMAR"):
            self.assertNotIn(secret, body)
        self.assertIn("Bhubaneswar - 751001", body)


class ReportAndDatabaseTests(Base):
    def test_reports_and_excel_file(self):
        order_id = self.place(quantity=2)[2]
        reports = ReportService(self.db)
        self.assertEqual(reports.get_monthly_report()[0]["orders"], 1)
        self.assertEqual(reports.get_daily_report()[0]["revenue"], 240.0)
        self.assertEqual(self.orders.get_order(order_id)["total_amount"], 240.0)
        import pandas as pd
        frame = pd.DataFrame({"Date": ["2026-11-10"], "Revenue": [240.0]})
        frame.index.name = "No."
        with zipfile.ZipFile(io.BytesIO(to_excel_bytes(frame))) as archive:
            sheet = archive.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("2026-11-10", sheet)
        self.assertIn("<col ", sheet)

    def test_database_uses_wal_mode(self):
        mode = sqlite3.connect(os.path.join(self.folder.name, "test.db")).execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode, "wal")


if __name__ == "__main__":
    unittest.main()
