from fastapi import FastAPI, HTTPException
from database.database import Database
from services.order_service import OrderService

app = FastAPI(title="Food Ordering Tracking API", version="1.0.0")
database = Database()
order_service = OrderService(database)

@app.get("/")
def home():
    return {"message": "Food Ordering Tracking API is running"}

@app.get("/api/orders/{order_id}")
def get_order_tracking(order_id: int):
    order = order_service.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "order_id": order["order_id"],
        "customer_id": order["customer_id"],
        "total_amount": order["total_amount"],
        "status": order["status"],
        "created_at": order["created_at"]
    }
