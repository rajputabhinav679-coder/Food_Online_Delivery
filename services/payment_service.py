class PaymentService:
    VALID_METHODS = {"UPI", "CASH_ON_DELIVERY"}
    VALID_STATUSES = {"PENDING", "SUCCESS", "FAILED"}

    # VALIDATE PAYMENT
    def simulate_payment(self, method, amount):
        method = method.strip().upper()
        if method not in self.VALID_METHODS:
            return False, "Invalid payment method."
        if amount <= 0:
            return False, "Invalid payment amount."
        if method == "UPI":
            return True, ("UPI payment submitted. " "Awaiting Cafe Owner verification.")
        if method == "CASH_ON_DELIVERY":
            return True, ("COD selected. Payment is due on delivery.")
        return False, "Payment could not be processed."

    # INITIAL PAYMENT STATUS
    def get_initial_status(self, method, has_screenshot=False):
        method = method.strip().upper()
        if method in self.VALID_METHODS:
            return "PENDING"
        return "FAILED"
