from datetime import timedelta
from utils.time_utils import now_ist

class ReportService:
    def __init__(self, database):
        self.database = database

    def get_total_orders(self):
        connection = self.database.get_connection()
        cursor = connection.cursor()
        cursor.execute("""SELECT COUNT(*) AS total
            FROM orders
            WHERE status != 'CANCELLED'""")
        result = cursor.fetchone()
        connection.close()
        return result["total"]

    def get_total_revenue(self):
        connection = self.database.get_connection()
        cursor = connection.cursor()
        cursor.execute("""SELECT COALESCE(SUM(total_amount), 0) AS revenue
            FROM orders
            WHERE status != 'CANCELLED'""")
        result = cursor.fetchone()
        connection.close()
        return result["revenue"]

    def get_total_customers(self):
        connection = self.database.get_connection()
        cursor = connection.cursor()
        cursor.execute("""SELECT COUNT(*) AS total
            FROM users
            WHERE role = 'customer'""")
        result = cursor.fetchone()
        connection.close()
        return result["total"]

    def get_delivery_performance(self):
        connection = self.database.get_connection()
        cursor = connection.cursor()
        cursor.execute("""SELECT SUM( CASE WHEN status = 'DELIVERED' THEN 1 ELSE 0 END ) AS
                delivered, SUM( CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END ) AS
                cancelled, SUM( CASE WHEN status NOT IN ( 'DELIVERED', 'CANCELLED' )
                THEN 1 ELSE 0 END ) AS pending
            FROM deliveries""")
        result = cursor.fetchone()
        connection.close()
        return {
            "delivered": result["delivered"] or 0,
            "pending": result["pending"] or 0,
            "cancelled": result["cancelled"] or 0
        }

    # COMBINED REPORTS (ORDERS + REVENUE + CUSTOMERS)
    #
    # Cancelled orders are not counted.
    #   Customers      = different customers who placed an order
    #   New Customers  = customers who registered in that period
    #                    (accounts created before this feature have no
    #                    registration date, so they are not counted here)
    def _grouped_report(self, length):
        """length 7 -> 'YYYY-MM' (monthly), 10 -> 'YYYY-MM-DD' (daily)."""
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(f"""
                SELECT
                    substr(created_at, 1, {length}) AS period,
                    COUNT(*) AS orders,
                    COALESCE(SUM(total_amount), 0) AS revenue,
                    COUNT(DISTINCT customer_id) AS customers
                FROM orders
                WHERE status != 'CANCELLED'
                GROUP BY period
            """)
            data = {
                row["period"]: {
                    "orders": row["orders"],
                    "revenue": float(row["revenue"]),
                    "customers": row["customers"],
                    "new_customers": 0
                }
                for row in cursor.fetchall()
            }
            cursor.execute(f"""
                SELECT
                    substr(created_at, 1, {length}) AS period,
                    COUNT(*) AS new_customers
                FROM users
                WHERE role = 'customer'
                  AND created_at IS NOT NULL
                GROUP BY period
            """)
            for row in cursor.fetchall():
                entry = data.setdefault(row["period"], {
                    "orders": 0,
                    "revenue": 0.0,
                    "customers": 0,
                    "new_customers": 0
                })
                entry["new_customers"] = row["new_customers"]
            return data
        finally:
            connection.close()

    def get_monthly_report(self):
        """One row per month (latest month first)."""
        data = self._grouped_report(7)
        months = sorted(data)
        rows = []
        previous_revenue = None
        for month in months:
            entry = data[month]
            if previous_revenue is None or previous_revenue == 0:
                growth = None
            else:
                growth = ((entry["revenue"] - previous_revenue) / previous_revenue * 100)
            previous_revenue = entry["revenue"]
            rows.append({
                "month": month,
                "orders": entry["orders"],
                "revenue": entry["revenue"],
                "customers": entry["customers"],
                "new_customers": entry["new_customers"],
                "growth": growth
            })
        rows.reverse()
        return rows

    def get_daily_report(self, start_date=None, end_date=None):
        """One row per day between the dates (latest day first).

        Days without any order are shown with zeros.
        """
        if end_date is None:
            end_date = now_ist().date()
        if start_date is None:
            start_date = end_date - timedelta(days=29)
        data = self._grouped_report(10)
        rows = []
        day = start_date
        while day <= end_date:
            key = day.isoformat()
            entry = data.get(key, {"orders": 0, "revenue": 0.0, "customers": 0, "new_customers": 0})
            rows.append({
                "date": key,
                "orders": entry["orders"],
                "revenue": entry["revenue"],
                "customers": entry["customers"],
                "new_customers": entry["new_customers"]
            })
            day += timedelta(days=1)
        rows.reverse()
        return rows
