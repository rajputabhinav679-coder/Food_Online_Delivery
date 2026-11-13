LABELS = {"cafe": "Cafe Owner", "delivery_boy": "Delivery Boy", "customer": "Customer", "UPI": "UPI", "CASH_ON_DELIVERY": "Cash on Delivery (COD)", "OUT_FOR_DELIVERY": "Out for Delivery"}

def label(code):
    """CASH_ON_DELIVERY -> Cash on Delivery (COD), OUT_FOR_DELIVERY -> Out for Delivery, PLACED -> Placed"""
    code = str(code or "")
    return LABELS.get(code) or code.replace("_", " ").capitalize()
