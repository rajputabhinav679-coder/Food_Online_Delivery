"""Tests for the order bugs that were found in the audit (bugs 1 to 5)."""
from config.app_config import DELIVERY_CHARGE
from tests.helpers import ShopTestCase

class StalePriceTests(ShopTestCase):
    def test_changed_price_is_not_charged_silently(self):
        cart = self.cart_with(self.pizza)                 # customer saw Rs 100
        self.menu.update_item(self.pizza, "Pizza", "Other", 250.0, "", True)
        ok, message, order_id = self.orders.create_order(
            self.customer_id, cart, "CASH_ON_DELIVERY", "PENDING", "1 Main Road - 769001", "9123456780")
        self.assertFalse(ok)
        self.assertIn("₹100.00 to ₹250.00", message)
        self.assertEqual(self.count("orders"), 0)
        self.assertEqual(cart.items[0].price, 250.0)       # cart now shows the real price

    def test_after_review_the_new_price_is_charged(self):
        cart = self.cart_with(self.pizza)
        self.menu.update_item(self.pizza, "Pizza", "Other", 250.0, "", True)
        self.orders.create_order(self.customer_id, cart, "CASH_ON_DELIVERY", "PENDING", "x - 769001", "9123456780")
        order_id = self.place(cart)
        total = self.row("SELECT total_amount FROM orders WHERE order_id = ?", order_id)["total_amount"]
        self.assertEqual(total, 250.0 + DELIVERY_CHARGE)
        saved = self.row("SELECT price FROM order_items WHERE order_id = ?", order_id)["price"]
        self.assertEqual(saved, 250.0)

    def test_unchanged_price_still_works(self):
        order_id = self.place()
        total = self.row("SELECT total_amount FROM orders WHERE order_id = ?", order_id)["total_amount"]
        self.assertEqual(total, 100.0 + DELIVERY_CHARGE)

    def test_sync_cart_updates_price_for_the_screen(self):
        cart = self.cart_with(self.pizza)
        self.menu.update_item(self.pizza, "Pizza", "Other", 120.0, "", True)
        notes = self.orders.sync_cart(cart)
        self.assertEqual(len(notes), 1)
        self.assertEqual(cart.get_subtotal(), 120.0)
        self.assertEqual(self.orders.sync_cart(cart), [])   # second time nothing to tell

class UnavailableAndDeletedItemTests(ShopTestCase):
    def test_unavailable_item_cannot_be_ordered(self):
        cart = self.cart_with(self.pizza)
        self.menu.toggle_availability(self.pizza)
        ok, message, _ = self.orders.create_order(
            self.customer_id, cart, "CASH_ON_DELIVERY", "PENDING", "x - 769001", "9123456780")
        self.assertFalse(ok)
        self.assertIn("currently unavailable", message)
        self.assertEqual(self.count("orders"), 0)
        self.assertEqual(cart.items, [])

    def test_other_items_stay_in_the_cart(self):
        cart = self.cart_with(self.pizza, self.burger)
        self.menu.toggle_availability(self.pizza)
        ok, _, _ = self.orders.create_order(
            self.customer_id, cart, "CASH_ON_DELIVERY", "PENDING", "x - 769001", "9123456780")
        self.assertFalse(ok)
        self.assertEqual([i.name for i in cart.items], ["Burger"])
        self.assertEqual(self.place(cart) > 0, True)

    def test_deleted_item_gives_a_clear_message_not_a_database_error(self):
        cart = self.cart_with(self.pizza)
        self.assertTrue(self.menu.delete_item(self.pizza)[0])
        ok, message, _ = self.orders.create_order(
            self.customer_id, cart, "CASH_ON_DELIVERY", "PENDING", "x - 769001", "9123456780")
        self.assertFalse(ok)
        self.assertNotIn("FOREIGN KEY", message)
        self.assertIn("no longer on the menu", message)
        self.assertEqual(self.count("orders"), 0)

class DeliveryBoyRequiredTests(ShopTestCase):
    def test_owner_cannot_mark_delivered_without_delivery_boy(self):
        order_id = self.place()
        self.orders.confirm_order(order_id)
        ok, message = self.orders.update_status(order_id, "DELIVERED")
        self.assertFalse(ok)
        self.assertIn("Delivery Boy", message)
        self.assertEqual(self.order_status(order_id), "CONFIRMED")

    def test_owner_cannot_send_out_for_delivery_without_delivery_boy(self):
        order_id = self.place()
        self.orders.confirm_order(order_id)
        ok, _ = self.orders.update_status(order_id, "OUT_FOR_DELIVERY")
        self.assertFalse(ok)
        self.assertEqual(self.order_status(order_id), "CONFIRMED")
        # the order is still waiting in Available Orders
        self.assertEqual([o["order_id"] for o in self.delivery.get_available_orders()], [order_id])

    def test_normal_flow_with_delivery_boy_still_works(self):
        order_id = self.delivered_by_boy()
        self.assertEqual(self.order_status(order_id), "DELIVERED")

    def test_owner_can_mark_delivered_when_boy_is_assigned(self):
        order_id = self.place()
        self.orders.confirm_order(order_id)
        self.delivery.accept_order(order_id, self.boy_id)
        self.assertTrue(self.orders.update_status(order_id, "DELIVERED")[0])

    def test_status_choices_hide_delivery_steps_until_boy_accepts(self):
        self.assertEqual(
            self.orders.allowed_statuses("CONFIRMED", False),
            ["PLACED", "CONFIRMED", "PREPARING", "CANCELLED"])
        self.assertEqual(
            self.orders.allowed_statuses("CONFIRMED", True), self.orders.VALID_STATUSES)

    def test_old_stuck_order_can_be_moved_back_and_reappears(self):
        order_id = self.place()
        self.orders.confirm_order(order_id)
        # how the old bug left an order: out for delivery, nobody assigned
        conn = self.db.get_connection()
        conn.execute("UPDATE orders SET status='OUT_FOR_DELIVERY' WHERE order_id=?", (order_id,))
        conn.execute("UPDATE deliveries SET status='OUT_FOR_DELIVERY' WHERE order_id=?", (order_id,))
        conn.commit()
        conn.close()
        self.assertEqual(self.delivery.get_available_orders(), [])
        self.assertIn("OUT_FOR_DELIVERY", self.orders.allowed_statuses("OUT_FOR_DELIVERY", False))
        self.assertTrue(self.orders.update_status(order_id, "CONFIRMED")[0])
        self.assertEqual(len(self.delivery.get_available_orders()), 1)

class FeedbackTests(ShopTestCase):
    def test_feedback_after_real_delivery(self):
        order_id = self.delivered_by_boy()
        ok, _ = self.feedback.submit_feedback(order_id, self.customer_id, 5, "Nice")
        self.assertTrue(ok)

    def test_no_feedback_for_order_delivered_without_delivery_boy(self):
        order_id = self.place()
        conn = self.db.get_connection()      # data left behind by the old bug
        conn.execute("UPDATE orders SET status='DELIVERED' WHERE order_id=?", (order_id,))
        conn.commit()
        conn.close()
        ok, _ = self.feedback.submit_feedback(order_id, self.customer_id, 5, "")
        self.assertFalse(ok)
        self.assertEqual(self.count("feedback"), 0)

    def test_no_feedback_before_delivery(self):
        order_id = self.place()
        self.assertFalse(self.feedback.submit_feedback(order_id, self.customer_id, 4, "")[0])

class UnchangedBehaviourTests(ShopTestCase):
    def test_cancel_before_payment_removes_the_order(self):
        order_id = self.place()
        self.assertTrue(self.orders.cancel_order(order_id, self.customer_id)[0])
        self.assertEqual(self.count("orders"), 0)

    def test_upi_order_needs_verification_before_delivery_boy_sees_it(self):
        order_id = self.place(method="UPI")
        self.assertEqual(self.delivery.get_available_orders(), [])
        self.assertTrue(self.orders.confirm_order(order_id)[0])
        self.assertEqual(len(self.delivery.get_available_orders()), 1)

    def test_empty_cart_is_refused(self):
        ok, message, _ = self.orders.create_order(
            self.customer_id, self.cart_with(), "CASH_ON_DELIVERY", "PENDING", "x - 769001", "9123456780")
        self.assertFalse(ok)
        self.assertIn("empty", message.lower())
