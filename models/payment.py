class Payment:
    VALID_METHODS = {"UPI", "CARD", "CASH_ON_DELIVERY"}
    VALID_STATUSES = {"PENDING", "SUCCESS", "FAILED"}

    def __init__(self, payment_id=None, order_id=None, amount=0.0, method="", status="PENDING"):
        self.payment_id = payment_id
        self.order_id = order_id
        self.amount = float(amount)
        self.method = method
        self.status = status

    def process(self):
        if self.method not in self.VALID_METHODS:
            raise ValueError("Invalid payment method.")
        self.status = "SUCCESS"
        return True

    def fail(self):
        self.status = "FAILED"
