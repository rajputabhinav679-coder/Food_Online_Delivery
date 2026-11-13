from utils.time_utils import now_iso

class DeliveryService:
    def __init__(self, database):
        self.database = database

    # GET AVAILABLE ORDERS
    def get_available_orders(self):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT o.order_id, (SELECT COUNT(*) FROM orders ox WHERE
                    ox.order_id <= o.order_id) AS order_no, o.customer_id, u.name AS
                    customer_name, u.email AS customer_email, o.customer_phone,
                    u.phone AS customer_account_phone, o.total_amount,
                    o.delivery_address, o.created_at, o.status AS order_status,
                    d.status AS delivery_status, p.method AS payment_method, p.status
                    AS payment_status
                FROM orders o
                JOIN users u ON o.customer_id = u.user_id
                JOIN deliveries d ON o.order_id = d.order_id
                LEFT JOIN payments p ON o.order_id = p.order_id
                WHERE o.status IN ('CONFIRMED', 'PREPARING') AND ( COALESCE(p.method, '') !=
                    'UPI' OR p.status = 'SUCCESS' ) AND d.delivery_boy_id IS NULL AND d.status NOT
                    IN ('CANCELLED', 'DELIVERED')
                ORDER BY o.order_id ASC""")
            return cursor.fetchall()
        finally:
            connection.close()

    # GET MY ASSIGNED ORDERS
    def get_my_orders(self, delivery_boy_id):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT o.order_id, (SELECT COUNT(*) FROM orders ox WHERE
                    ox.order_id <= o.order_id) AS order_no, o.customer_id, u.name AS
                    customer_name, u.email AS customer_email, o.customer_phone,
                    u.phone AS customer_account_phone, o.total_amount,
                    o.delivery_address, o.created_at, o.status AS order_status,
                    d.status AS delivery_status, d.delivery_time, p.method AS
                    payment_method, p.status AS payment_status
                FROM orders o
                JOIN users u ON o.customer_id = u.user_id
                JOIN deliveries d ON o.order_id = d.order_id
                LEFT JOIN payments p ON o.order_id = p.order_id
                WHERE d.delivery_boy_id = ?
                ORDER BY o.order_id DESC""", (delivery_boy_id,))
            return cursor.fetchall()
        finally:
            connection.close()

    # ACCEPT ORDER
    def accept_order(self, order_id, delivery_boy_id):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""UPDATE deliveries
                SET delivery_boy_id = ?, status = 'OUT_FOR_DELIVERY'
                WHERE order_id = ? AND delivery_boy_id IS NULL AND status NOT IN ('CANCELLED',
                    'DELIVERED') AND EXISTS ( SELECT 1 FROM orders WHERE orders.order_id =
                    deliveries.order_id AND orders.status IN ('CONFIRMED', 'PREPARING') ) AND NOT
                    EXISTS ( SELECT 1 FROM payments WHERE payments.order_id = deliveries.order_id
                    AND payments.method = 'UPI' AND payments.status != 'SUCCESS' ) AND EXISTS (
                    SELECT 1 FROM users WHERE users.user_id = ? AND users.role = 'delivery_boy' AND
                    users.is_active = 1 )""", (
                delivery_boy_id,
                order_id,
                delivery_boy_id
            ))
            accepted = cursor.rowcount == 1
            if accepted:
                cursor.execute("""UPDATE orders
                    SET status = 'OUT_FOR_DELIVERY'
                    WHERE order_id = ?""", (order_id,))
            connection.commit()
            return accepted
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # MARK ORDER AS DELIVERED
    def mark_delivered(self, order_id, delivery_boy_id):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            delivery_time = now_iso()
            cursor.execute("""UPDATE deliveries
                SET status = 'DELIVERED', delivery_time = ?
                WHERE order_id = ? AND delivery_boy_id = ? AND status = 'OUT_FOR_DELIVERY' AND
                    EXISTS ( SELECT 1 FROM orders WHERE orders.order_id = deliveries.order_id AND
                    orders.status != 'CANCELLED' )""", (
                delivery_time,
                order_id,
                delivery_boy_id
            ))
            updated = cursor.rowcount == 1
            if updated:
                cursor.execute("""UPDATE orders
                    SET status = 'DELIVERED'
                    WHERE order_id = ? AND status = 'OUT_FOR_DELIVERY'""", (order_id,))
                if cursor.rowcount != 1:
                    connection.rollback()
                    return False
            connection.commit()
            return updated
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
