from datetime import datetime

class Order:
    VALID_STATUSES = {
        "PLACED",
        "CONFIRMED",
        "PREPARING",
        "OUT_FOR_DELIVERY",
        "DELIVERED",
        "CANCELLED"
    }

    def __init__(
        self,
        order_id=None,
        customer_id=None,
        total_amount=0.0,
        status="PLACED",
        created_at=None
    ):
        self.order_id = order_id
        self.customer_id = customer_id
        self.total_amount = float(total_amount)
        self.status = status
        self.created_at = created_at or datetime.now()

    def update_status(self, new_status):
        if new_status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid order status: {new_status}")
        self.status = new_status

    def cancel(self):
        if self.status in {"DELIVERED", "CANCELLED"}:
            raise ValueError("This order cannot be cancelled.")
        self.status = "CANCELLED"
