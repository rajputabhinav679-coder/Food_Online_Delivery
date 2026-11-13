from models.cart import Cart
from config.app_config import DELIVERY_CHARGE, MAX_ITEM_QUANTITY

class CartService:
    DELIVERY_CHARGE = DELIVERY_CHARGE
    MAX_QUANTITY = MAX_ITEM_QUANTITY

    def __init__(self):
        pass

    def _get_carts(self):
        """
        Stores separate cart for every logged-in customer
        inside the current Streamlit session.
        """
        import streamlit as st
        if "customer_carts" not in st.session_state:
            st.session_state.customer_carts = {}
        return st.session_state.customer_carts

    def get_cart(self, customer_id):
        carts = self._get_carts()
        if customer_id not in carts:
            carts[customer_id] = Cart(customer_id)
        return carts[customer_id]

    def get_quantity(self, customer_id, item_id):
        return self.get_cart(customer_id).get_quantity(item_id)

    def add_item(self, customer_id, menu_item, quantity=1):
        cart = self.get_cart(customer_id)
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return False, "Please enter a valid quantity."
        if quantity < 1:
            return False, "Quantity must be at least 1."
        already_in_cart = cart.get_quantity(menu_item.item_id)
        allowed = self.MAX_QUANTITY - already_in_cart
        if allowed <= 0:
            return False, (f"Maximum {self.MAX_QUANTITY} of {menu_item.name} " "allowed per order.")
        if quantity > allowed:
            cart.add_item(menu_item, allowed)
            return True, (
                f"Only {allowed} more added. Maximum "
                f"{self.MAX_QUANTITY} of {menu_item.name} per order."
            )
        cart.add_item(menu_item, quantity)
        return True, f"{quantity} × {menu_item.name} added to cart."

    def remove_item(self, customer_id, item_id):
        cart = self.get_cart(customer_id)
        cart.remove_item(item_id)
        return True, "Item removed from cart."

    def update_quantity(self, customer_id, item_id, quantity):
        cart = self.get_cart(customer_id)
        quantity = int(quantity)
        if quantity < 1:
            cart.remove_item(item_id)
            return True, "Item removed from cart."
        quantity = min(quantity, self.MAX_QUANTITY)
        cart.update_quantity(item_id, quantity)
        return True, "Quantity updated."

    def get_subtotal(self, customer_id):
        cart = self.get_cart(customer_id)
        return cart.get_subtotal()

    def get_delivery_charge(self, customer_id):
        cart = self.get_cart(customer_id)
        if not cart.items:
            return 0.0
        return self.DELIVERY_CHARGE

    def get_total(self, customer_id):
        subtotal = self.get_subtotal(customer_id)
        delivery_charge = self.get_delivery_charge(customer_id)
        return subtotal + delivery_charge

    def get_item_count(self, customer_id):
        cart = self.get_cart(customer_id)
        return sum(item.quantity for item in cart.items)

    def clear_cart(self, customer_id):
        cart = self.get_cart(customer_id)
        cart.clear()
