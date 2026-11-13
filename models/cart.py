class CartItem:
    def __init__(self, item_id, name, price, quantity=1):
        self.item_id = item_id
        self.name = name
        self.price = float(price)
        self.quantity = int(quantity)

    def get_total(self):
        return self.price * self.quantity

class Cart:
    def __init__(self, customer_id):
        self.customer_id = customer_id
        self.items = []

    def get_quantity(self, item_id):
        for cart_item in self.items:
            if cart_item.item_id == item_id:
                return cart_item.quantity
        return 0

    def add_item(self, item, quantity=1):
        quantity = int(quantity)
        for cart_item in self.items:
            if cart_item.item_id == item.item_id:
                cart_item.quantity += quantity
                return
        self.items.append(
            CartItem(
                item_id=item.item_id,
                name=item.name,
                price=item.price,
                quantity=quantity
            )
        )

    def remove_item(self, item_id):
        self.items = [item for item in self.items if item.item_id != item_id]

    def update_quantity(self, item_id, quantity):
        for item in self.items:
            if item.item_id == item_id:
                item.quantity = int(quantity)
                if item.quantity <= 0:
                    self.remove_item(item_id)
                return

    def get_subtotal(self):
        return sum(item.get_total() for item in self.items)

    def clear(self):
        self.items = []
