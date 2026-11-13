import sqlite3
from models.menu_item import MenuItem

class MenuService:
    def __init__(self, database):
        self.database = database

    def add_item(self, name, category, price, description, available=True, image_bytes=None):
        name = name.strip()
        category = category.strip()
        description = description.strip()
        if not name:
            return False, "Food name is required."
        if not category:
            return False, "Category is required."
        try:
            price = float(price)
        except (ValueError, TypeError):
            return False, "Price must be a valid number."
        if price <= 0:
            return False, "Price must be greater than 0."
        connection = self.database.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """INSERT INTO menu_items (name, category, price, description, available, image)
                VALUES (?, ?, ?, ?, ?, ?)""",
            (
                name,
                category,
                price,
                description,
                1 if available else 0,
                image_bytes
            )
        )
        connection.commit()
        connection.close()
        return True, "Food item added successfully."

    def get_all_items(self):
        connection = self.database.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """SELECT item_id, name, category, price, description, available, image
                FROM menu_items
                ORDER BY item_id DESC"""
        )
        rows = cursor.fetchall()
        connection.close()
        return [
            MenuItem(
                item_id=row["item_id"],
                name=row["name"],
                category=row["category"],
                price=row["price"],
                description=row["description"] or "",
                available=bool(row["available"]),
                image=row["image"]
            )
            for row in rows
        ]

    def get_available_items(self):
        connection = self.database.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """SELECT item_id, name, category, price, description, available, image
                FROM menu_items
                WHERE available = 1
                ORDER BY category, name"""
        )
        rows = cursor.fetchall()
        connection.close()
        return [
            MenuItem(
                item_id=row["item_id"],
                name=row["name"],
                category=row["category"],
                price=row["price"],
                description=row["description"] or "",
                available=True,
                image=row["image"]
            )
            for row in rows
        ]

    def update_item(
        self,
        item_id,
        name,
        category,
        price,
        description,
        available,
        image_bytes=None,
        remove_image=False
    ):
        name = name.strip()
        category = category.strip()
        description = description.strip()
        if not name:
            return False, "Food name is required."
        if not category:
            return False, "Category is required."
        try:
            price = float(price)
        except (ValueError, TypeError):
            return False, "Price must be a valid number."
        if price <= 0:
            return False, "Price must be greater than 0."
        connection = self.database.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """UPDATE menu_items
                SET name = ?, category = ?, price = ?, description = ?, available = ?
                WHERE item_id = ?""",
            (
                name,
                category,
                price,
                description,
                1 if available else 0,
                item_id
            )
        )
        # photo: replace with a new one, or remove, else keep old photo
        if image_bytes is not None:
            cursor.execute(
                "UPDATE menu_items SET image = ? WHERE item_id = ?",
                (image_bytes, item_id)
            )
        elif remove_image:
            cursor.execute("UPDATE menu_items SET image = NULL WHERE item_id = ?", (item_id,))
        connection.commit()
        updated = cursor.rowcount > 0
        connection.close()
        if not updated:
            return False, "Food item not found."
        return True, "Food item updated successfully."

    def delete_item(self, item_id):
        connection = self.database.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """SELECT item_id
                FROM menu_items
                WHERE item_id = ?""",
            (item_id,)
        )
        item = cursor.fetchone()
        if item is None:
            connection.close()
            return False, "Food item not found."
        try:
            cursor.execute(
                """DELETE
                    FROM menu_items
                    WHERE item_id = ?""",
                (item_id,)
            )
            connection.commit()
        except sqlite3.IntegrityError:
            # The food was ordered before, so the database does not allow
            # deleting it. Hide it from the customer menu instead.
            connection.rollback()
            cursor.execute(
                """UPDATE menu_items
                    SET available = 0
                    WHERE item_id = ?""",
                (item_id,)
            )
            connection.commit()
            connection.close()
            return True, (
                "This food was already ordered by customers, so it "
                "cannot be deleted. It is now marked Unavailable."
            )
        connection.close()
        return True, "Food item deleted successfully."

    def toggle_availability(self, item_id):
        connection = self.database.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """SELECT available
                FROM menu_items
                WHERE item_id = ?""",
            (item_id,)
        )
        row = cursor.fetchone()
        if row is None:
            connection.close()
            return False, "Food item not found."
        new_status = 0 if row["available"] else 1
        cursor.execute(
            """UPDATE menu_items
                SET available = ?
                WHERE item_id = ?""",
            (new_status, item_id)
        )
        connection.commit()
        connection.close()
        return True, "Food availability updated."
