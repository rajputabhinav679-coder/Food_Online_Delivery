"""Renders every screen with a fake Streamlit and checks the text a person would read."""
import unittest

from tests import fake_streamlit
from tests.helpers import ShopTestCase

RAW_CODES = ["OUT_FOR_DELIVERY", "CASH_ON_DELIVERY", "PLACED", "CONFIRMED", "PREPARING",
             "DELIVERED", "CANCELLED", "SUCCESS", "FAILED", "PENDING", "delivery_boy", "(A-Z)"]

class ScreenTestCase(ShopTestCase):
    def setUp(self):
        super().setUp()
        self.st, undo = fake_streamlit.install()
        self.addCleanup(undo)
        import importlib
        self.customer_ui = importlib.import_module("ui.customer_dashboard")
        self.cafe_ui = importlib.import_module("ui.cafe_dashboard")
        self.delivery_ui = importlib.import_module("ui.delivery_dashboard")
        self.login_ui = importlib.import_module("ui.login")
        from services.cart_service import CartService
        from services.payment_service import PaymentService
        from services.report_service import ReportService
        from models.user import User
        self.carts = CartService()
        self.payments = PaymentService()
        self.reports = ReportService(self.db)
        self.customer = User(self.customer_id, "Asha Rao", "asha@example.com", "", "customer", "9123456780")
        self.boy = User(self.boy_id, "Ravi Kumar", "ravi@example.com", "", "delivery_boy", "9876501234")
        self.owner_id = self.add_user("Cafe Boss", "boss@example.com", "cafe")
        self.owner = User(self.owner_id, "Cafe Boss", "boss@example.com", "", "cafe", "9123456789")

    def show(self, function, user, section_scope, section, *args, presses=()):
        self.st.texts.clear()
        self.st.session_state.user = user
        self.st.session_state[f"nav_{section_scope}"] = section
        self.st.press(*presses)
        try:
            function(*args)
        except (fake_streamlit.Rerun, fake_streamlit.Stop):
            pass
        return self.st.output()

    def customer_screen(self, section, presses=()):
        return self.show(self.customer_ui.show_customer_dashboard, self.customer, "customer", section,
                         self.menu, self.carts, self.orders, self.payments, self.feedback, presses=presses)

    def cafe_screen(self, section):
        return self.show(self.cafe_ui.show_cafe_dashboard, self.owner, "cafe", section,
                         self.menu, self.orders, self.reports, self.auth, self.feedback)

    def delivery_screen(self, section):
        return self.show(self.delivery_ui.show_delivery_dashboard, self.boy, "delivery", section,
                         self.delivery, self.boy, self.orders)

    def assertNoRawCodes(self, text, screen):
        for code in RAW_CODES:
            self.assertNotIn(code, text, f"raw code {code!r} is visible on the {screen} screen")

class RawCodeTests(ScreenTestCase):
    def make_orders_in_every_state(self):
        self.place(method="UPI")                                   # placed, UPI pending
        cod = self.place()
        self.orders.confirm_order(cod)                             # confirmed, available for delivery
        out = self.place()
        self.orders.confirm_order(out)
        self.delivery.accept_order(out, self.boy_id)               # out for delivery
        self.delivered_by_boy()                                    # delivered
        paid = self.place(method="UPI")
        self.orders.confirm_order(paid)
        self.orders.cancel_order(paid, self.customer_id)           # cancelled after payment

    def test_customer_screens(self):
        self.make_orders_in_every_state()
        for section in ("menu", "cart", "orders", "feedback"):
            self.assertNoRawCodes(self.customer_screen(section), f"customer {section}")
        orders = self.customer_screen("orders")
        for words in ("Out for delivery", "Cash on Delivery", "Delivered", "Cancelled", "Placed"):
            self.assertIn(words, orders)
        self.assertIn("Their name and number", orders)
        self.assertNotIn("His name", orders)

    def test_cafe_screens(self):
        self.make_orders_in_every_state()
        for section in ("menu", "orders", "reports", "delivery", "feedback"):
            self.assertNoRawCodes(self.cafe_screen(section), f"cafe {section}")
        orders = self.cafe_screen("orders")
        self.assertIn("Out for delivery", orders)
        self.assertIn("Cash on Delivery", orders)

    def test_delivery_screens(self):
        self.make_orders_in_every_state()
        for section in ("available", "mine"):
            self.assertNoRawCodes(self.delivery_screen(section), f"delivery {section}")

    def test_owner_status_box_hides_delivery_steps_without_delivery_boy(self):
        order_id = self.place()
        self.orders.confirm_order(order_id)
        text = self.cafe_screen("orders")
        self.assertIn("appear after a Delivery Boy accepts this order", text)
        self.assertNotIn("Out for delivery", text.split("Change Order Status", 1)[1].split("'Out for delivery' and", 1)[0])

    def test_delivery_boy_remove_text_is_gender_neutral(self):
        text = self.cafe_screen("delivery")
        self.assertIn("Remove this Delivery Boy", text)
        self.assertIn("Their old deliveries", text)
        self.assertNotIn(" his ", text.lower())

class CartScreenTests(ScreenTestCase):
    def test_old_price_in_cart_is_corrected_and_explained(self):
        cart = self.carts.get_cart(self.customer_id)
        cart.add_item(self.menu_item(self.pizza), 1)
        self.menu.update_item(self.pizza, "Pizza", "Other", 250.0, "", True)
        text = self.customer_screen("cart")
        self.assertIn("changed from ₹100.00 to ₹250.00", text)
        self.assertIn("₹290.00", text)                             # 250 + delivery charge

    def test_unavailable_item_is_removed_from_cart_screen(self):
        cart = self.carts.get_cart(self.customer_id)
        cart.add_item(self.menu_item(self.pizza), 1)
        self.menu.toggle_availability(self.pizza)
        text = self.customer_screen("cart")
        self.assertIn("currently unavailable", text)
        self.assertIn("Your cart is empty", text)

    def test_place_order_button_charges_the_new_price(self):
        cart = self.carts.get_cart(self.customer_id)
        cart.add_item(self.menu_item(self.pizza), 1)
        self.menu.update_item(self.pizza, "Pizza", "Other", 250.0, "", True)
        state = self.st.session_state
        state.update(checkout_open=True, delivery_name="Asha Rao", delivery_phone="9831274650",
                     house_details="12", area_details="Main Road", delivery_city="Rourkela",
                     delivery_pincode="769001", payment_method_choice="CASH_ON_DELIVERY")
        self.customer_screen("cart", presses=("Place Order",))
        row = self.row("SELECT total_amount FROM orders")
        self.assertEqual(row["total_amount"], 290.0)

class LoginScreenTests(ScreenTestCase):
    def test_login_page_uses_the_app_name(self):
        self.st.texts.clear()
        self.login_ui.show_login(self.auth)
        self.assertIn("Food Online Cafe", self.st.output())

if __name__ == "__main__":
    unittest.main()
