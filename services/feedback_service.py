import sqlite3
from utils.time_utils import now_iso

class FeedbackService:
    MAX_COMMENT_LENGTH = 500

    def __init__(self, database):
        self.database = database

    # SUBMIT FEEDBACK (ONLY FOR DELIVERED ORDERS)
    def submit_feedback(self, order_id, customer_id, rating, comment=""):
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return False, "Please select a rating."
        if rating < 1 or rating > 5:
            return False, "Rating must be between 1 and 5 stars."
        comment = (comment or "").strip()[:self.MAX_COMMENT_LENGTH]
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT status
                FROM orders
                WHERE order_id = ? AND customer_id = ?""", (order_id, customer_id))
            order = cursor.fetchone()
            if order is None:
                return False, "Order not found."
            if order["status"] != "DELIVERED":
                return False, ("You can give feedback only after " "the order is delivered.")
            cursor.execute("""INSERT INTO feedback (order_id, customer_id, rating, comment,
                    created_at)
                VALUES (?, ?, ?, ?, ?)""", (
                order_id,
                customer_id,
                rating,
                comment,
                now_iso()
            ))
            connection.commit()
            return True, "Thank you! Your feedback has been submitted."
        except sqlite3.IntegrityError:
            connection.rollback()
            return False, "Feedback is already submitted for this order."
        except Exception as error:
            connection.rollback()
            return False, f"Could not save feedback: {error}"
        finally:
            connection.close()

    # CUSTOMER: MY FEEDBACK  ->  {order_id: row}
    def get_customer_feedback(self, customer_id):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT order_id, rating, comment, created_at
                FROM feedback
                WHERE customer_id = ?
                ORDER BY feedback_id DESC""", (customer_id,))
            return {row["order_id"]: row for row in cursor.fetchall()}
        finally:
            connection.close()

    # CAFE: ALL FEEDBACK
    def get_all_feedback(self):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT f.feedback_id, f.order_id, (SELECT COUNT(*) FROM orders ox
                    WHERE ox.order_id <= f.order_id) AS order_no, f.rating, f.comment,
                    f.created_at, u.name AS customer_name, o.total_amount
                FROM feedback f
                JOIN users u ON f.customer_id = u.user_id
                JOIN orders o ON f.order_id = o.order_id
                ORDER BY f.feedback_id DESC""")
            return cursor.fetchall()
        finally:
            connection.close()

    def get_summary(self):
        """Return (number_of_feedbacks, average_rating)."""
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT COUNT(*) AS total, AVG(rating) AS average
                FROM feedback""")
            row = cursor.fetchone()
            return row["total"], float(row["average"] or 0)
        finally:
            connection.close()
