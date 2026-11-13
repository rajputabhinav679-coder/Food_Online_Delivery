import sqlite3
from pathlib import Path

class Database:
    def __init__(self, db_path="data/food_ordering.db"):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.create_tables()
        with sqlite3.connect(self.db_path) as connection:     # WAL: readers and writers do not block each other
            connection.execute("PRAGMA journal_mode = WAL")

    # DATABASE CONNECTION
    def get_connection(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    # ADD A COLUMN TO AN OLD DATABASE (SAFE MIGRATION)
    @staticmethod
    def _add_column_if_missing(cursor, table, column, definition):
        cursor.execute(f"PRAGMA table_info({table})")
        existing_columns = [row["name"] for row in cursor.fetchall()]
        if column not in existing_columns:
            cursor.execute(f"ALTER TABLE {table} " f"ADD COLUMN {column} {definition}")

    # CREATE TABLES
    def create_tables(self):
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            # USERS TABLE
            cursor.execute("""CREATE TABLE IF NOT EXISTS users ( user_id INTEGER PRIMARY KEY
                    AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'customer'
                    )""")
            # MENU ITEMS TABLE
            cursor.execute("""CREATE TABLE IF NOT EXISTS menu_items ( item_id INTEGER PRIMARY
                    KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL,
                    price REAL NOT NULL, description TEXT, available INTEGER NOT NULL
                    DEFAULT 1 )""")
            # ORDERS TABLE
            cursor.execute("""CREATE TABLE IF NOT EXISTS orders ( order_id INTEGER PRIMARY KEY
                    AUTOINCREMENT, customer_id INTEGER NOT NULL, total_amount REAL NOT
                    NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
                    delivery_address TEXT NOT NULL DEFAULT '', FOREIGN KEY
                    (customer_id) REFERENCES users(user_id) )""")
            # ORDER ITEMS TABLE
            cursor.execute("""CREATE TABLE IF NOT EXISTS order_items ( order_item_id INTEGER
                    PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, item_id
                    INTEGER NOT NULL, quantity INTEGER NOT NULL, price REAL NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES orders(order_id), FOREIGN KEY
                    (item_id) REFERENCES menu_items(item_id) )""")
            # PAYMENTS TABLE
            cursor.execute("""CREATE TABLE IF NOT EXISTS payments ( payment_id INTEGER PRIMARY
                    KEY AUTOINCREMENT, order_id INTEGER NOT NULL, amount REAL NOT
                    NULL, method TEXT NOT NULL, status TEXT NOT NULL, FOREIGN KEY
                    (order_id) REFERENCES orders(order_id) )""")
            # DELIVERIES TABLE
            cursor.execute("""CREATE TABLE IF NOT EXISTS deliveries ( delivery_id INTEGER
                    PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, status TEXT
                    NOT NULL, delivery_time TEXT, delivery_boy_id INTEGER, FOREIGN KEY
                    (order_id) REFERENCES orders(order_id), FOREIGN KEY
                    (delivery_boy_id) REFERENCES users(user_id) )""")
            # FEEDBACK TABLE
            cursor.execute("""CREATE TABLE IF NOT EXISTS feedback ( feedback_id INTEGER PRIMARY
                    KEY AUTOINCREMENT, order_id INTEGER NOT NULL UNIQUE, customer_id
                    INTEGER NOT NULL, rating INTEGER NOT NULL CHECK (rating BETWEEN 1
                    AND 5), comment TEXT NOT NULL DEFAULT '', created_at TEXT NOT
                    NULL, FOREIGN KEY (order_id) REFERENCES orders(order_id), FOREIGN
                    KEY (customer_id) REFERENCES users(user_id) )""")
            # MIGRATION: PHONE NUMBERS AND FOOD NAME SNAPSHOT
            self._add_column_if_missing(cursor, "users", "phone", "TEXT NOT NULL DEFAULT ''")
            self._add_column_if_missing(
                cursor, "orders", "customer_phone",
                "TEXT NOT NULL DEFAULT ''"
            )
            self._add_column_if_missing(cursor, "order_items", "item_name", "TEXT")
            self._add_column_if_missing(cursor, "menu_items", "image", "BLOB")
            self._add_column_if_missing(cursor, "users", "created_at", "TEXT")
            self._add_column_if_missing(cursor, "users", "is_active", "INTEGER NOT NULL DEFAULT 1")
            cursor.execute("""CREATE TABLE IF NOT EXISTS notification_log ( log_id INTEGER
                    PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, recipient TEXT NOT
                    NULL DEFAULT '', subject TEXT NOT NULL DEFAULT '', status TEXT NOT
                    NULL, error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
                    )""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS login_attempts (email TEXT PRIMARY KEY,
                    failures INTEGER NOT NULL DEFAULT 0, locked_until TEXT, updated_at
                    TEXT NOT NULL)""")
            self._add_column_if_missing(cursor, "payments", "screenshot", "BLOB")
            self._add_column_if_missing(cursor, "payments", "screenshot_hash", "TEXT")
            # MIGRATION: DELIVERY ADDRESS
            cursor.execute("PRAGMA table_info(orders)")
            order_columns = [row["name"] for row in cursor.fetchall()]
            if "delivery_address" not in order_columns:
                cursor.execute("""ALTER TABLE orders ADD COLUMN delivery_address TEXT NOT NULL
                        DEFAULT ''""")
            # MIGRATION: DELIVERY BOY ID
            cursor.execute("PRAGMA table_info(deliveries)")
            delivery_columns = [row["name"] for row in cursor.fetchall()]
            if "delivery_boy_id" not in delivery_columns:
                cursor.execute("""ALTER TABLE deliveries ADD COLUMN delivery_boy_id INTEGER""")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
