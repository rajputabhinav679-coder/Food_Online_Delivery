class Delivery:
    VALID_STATUSES = {"PENDING", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"}

    def __init__(self, delivery_id=None, order_id=None, status="PENDING", delivery_time=None):
        self.delivery_id = delivery_id
        self.order_id = order_id
        self.status = status
        self.delivery_time = delivery_time

    def update_status(self, new_status):
        if new_status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid delivery status: {new_status}")
        self.status = new_status
