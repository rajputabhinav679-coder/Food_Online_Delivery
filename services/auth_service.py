import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from models.user import User
from utils.validators import validate_mobile, validate_name, validate_password
from utils.time_utils import now_iso, now_ist, parse_dt

PBKDF2_ROUNDS = 600_000

class AuthService:
    MAX_LOGIN_FAILURES = 5
    LOCK_MINUTES = 15

    def __init__(self, database, notifier=None):
        self.database = database
        self.notifier = notifier
        self.create_default_cafe()

    # PASSWORD AND TOKEN HASHING
    @staticmethod
    def hash_password(password):
        """Salted PBKDF2-SHA256 hash: pbkdf2_sha256$rounds$salt$hash."""
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS)
        return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${digest.hex()}"

    @staticmethod
    def verify_password(password, stored):
        """Checks a new PBKDF2 hash, or an old unsalted SHA-256 hash (upgraded at the next login)."""
        stored = stored or ""
        if stored.startswith("pbkdf2_sha256$"):
            _, rounds, salt, digest = stored.split("$")
            check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(rounds))
            return hmac.compare_digest(check.hex(), digest)
        return hmac.compare_digest(hashlib.sha256(password.encode("utf-8")).hexdigest(), stored)

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    # EMAIL VALIDATION
    @staticmethod
    def validate_gmail(email):
        """Validate and normalize an email address (Gmail or other provider)."""
        email = (email or "").strip().lower()
        if not email:
            return False, "Email is required."
        # Basic practical validation; accepts Gmail aliases and other valid domains.
        pattern = r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+$"
        if len(email) > 254 or not re.fullmatch(pattern, email):
            return False, "Please enter a valid email address."
        return True, email

    # CREATE DEFAULT CAFE ACCOUNT
    def create_default_cafe(self):
        """Create/update the Cafe Owner only when credentials are configured.

        Configure [auth] cafe_email and cafe_password in Streamlit secrets.
        No real credentials are hard-coded in the source code.
        """
        import os
        try:
            import streamlit as st
            auth_settings = st.secrets.get("auth", {})
        except Exception:
            auth_settings = {}
        cafe_email = str(
            os.environ.get("CAFE_LOGIN_EMAIL", auth_settings.get("cafe_email", "abhinavsinghh0019@gmail.com"))
        ).strip().lower()
        cafe_password = str(
            os.environ.get("CAFE_LOGIN_PASSWORD", auth_settings.get("cafe_password", ""))
        )
        cafe_name = str(auth_settings.get("cafe_name", "Cafe Owner")).strip() or "Cafe Owner"
        cafe_phone = str(auth_settings.get("cafe_phone", "9263747538")).strip()
        if not cafe_email or not cafe_password:
            return
        valid, normalized_email = self.validate_gmail(cafe_email)
        if not valid:
            return
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT user_id FROM users WHERE lower(trim(email)) = ?",
                (normalized_email,)
            )
            existing = cursor.fetchone()
            password_hash = self.hash_password(cafe_password)
            if existing is None:
                cursor.execute("""INSERT INTO users (name, email, password, role, phone,
                        created_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, 1)""", (
                    cafe_name, normalized_email, password_hash,
                    "cafe", cafe_phone, now_iso()
                ))
            else:
                # The password from secrets is only the FIRST password. Later it is changed
                # inside the app (Change Password). Set [auth] reset_cafe_password = true
                # to force the secrets password again.
                cursor.execute("""UPDATE users
                    SET name = ?, role = 'cafe', phone = ?, is_active = 1
                    WHERE user_id = ?""", (cafe_name, cafe_phone, existing["user_id"]))
                if str(auth_settings.get("reset_cafe_password", "")).lower() in ("true", "1", "yes"):
                    cursor.execute("UPDATE users SET password = ? WHERE user_id = ?",
                                   (password_hash, existing["user_id"]))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # CUSTOMER REGISTRATION
    def register_customer(self, name, email, password, phone):
        name_valid, name_result = validate_name(name)
        if not name_valid:
            return False, name_result
        name = name_result
        valid, result = self.validate_gmail(email)
        if not valid:
            return False, result
        email = result
        phone_valid, phone_result = validate_mobile(phone)
        if not phone_valid:
            return False, phone_result
        phone = phone_result
        if len(password) < 6:
            return False, "Password must contain at least 6 characters."
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT user_id
                FROM users
                WHERE lower(trim(email)) = ?""", (email,))
            if cursor.fetchone() is not None:
                return False, "Email already registered."
            password_hash = self.hash_password(password)
            cursor.execute("""INSERT INTO users (name, email, password, role, phone, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""", (
                name,
                email,
                password_hash,
                "customer",
                phone,
                now_iso()
            ))
            connection.commit()
            return True, "Customer registration successful."
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # DELIVERY BOY REGISTRATION
    def register_delivery_boy(self, name, email, password, current_user, phone):
        if current_user is None or not current_user.is_cafe():
            return False, "Only Cafe Owner can create Delivery Boy accounts."
        name_valid, name_result = validate_name(name)
        if not name_valid:
            return False, name_result
        name = name_result
        valid, result = self.validate_gmail(email)
        if not valid:
            return False, result
        email = result
        phone_valid, phone_result = validate_mobile(phone)
        if not phone_valid:
            return False, phone_result
        phone = phone_result
        if len(password) < 6:
            return False, "Password must contain at least 6 characters."
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT user_id
                FROM users
                WHERE lower(trim(email)) = ?""", (email,))
            if cursor.fetchone() is not None:
                return False, "Email already registered."
            password_hash = self.hash_password(password)
            cursor.execute("""INSERT INTO users (name, email, password, role, phone)
                VALUES (?, ?, ?, ?, ?)""", (
                name,
                email,
                password_hash,
                "delivery_boy",
                phone
            ))
            connection.commit()
            return True, "Delivery Boy account created successfully."
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # USER LOGIN
    def login(self, email, password):
        valid, email = self.validate_gmail(email)
        if not valid or not password or self.lockout_seconds(email) > 0:
            return None
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT user_id, name, email, password, role, phone
                FROM users
                WHERE lower(trim(email)) = ? AND is_active = 1""", (email,))
            row = cursor.fetchone()
            if row is None or not self.verify_password(password, row["password"]):
                self._login_failed(email)
                return None
            if not row["password"].startswith("pbkdf2_sha256$"):      # old hash -> upgrade now
                cursor.execute("UPDATE users SET password = ? WHERE user_id = ?",
                               (self.hash_password(password), row["user_id"]))
                connection.commit()
            self._login_ok(email)
            return User(user_id=row["user_id"], name=row["name"], email=row["email"], password="",
                        role=row["role"], phone=row["phone"])
        finally:
            connection.close()

    # LOGIN LOCKOUT: 5 wrong passwords -> this email is locked for 15 minutes
    def lockout_seconds(self, email):
        connection = self.database.get_connection()
        try:
            row = connection.execute("SELECT locked_until FROM login_attempts WHERE email = ?",
                                     ((email or "").strip().lower()[:254],)).fetchone()
        finally:
            connection.close()
        if row is None or not row["locked_until"]:
            return 0
        return max(0, int((parse_dt(row["locked_until"]) - now_ist()).total_seconds()))

    def _login_failed(self, email):
        email = email.strip().lower()[:254]
        connection = self.database.get_connection()
        try:
            row = connection.execute("SELECT failures FROM login_attempts WHERE email = ?", (email,)).fetchone()
            failures = (row["failures"] if row else 0) + 1
            locked = None
            if failures >= self.MAX_LOGIN_FAILURES:
                failures, locked = 0, (now_ist() + timedelta(minutes=self.LOCK_MINUTES)).isoformat(timespec="seconds")
            connection.execute("INSERT OR REPLACE INTO login_attempts VALUES (?, ?, ?, ?)", (email, failures, locked, now_iso()))
            connection.execute("DELETE FROM login_attempts WHERE updated_at < ?",
                               ((now_ist() - timedelta(days=1)).isoformat(timespec="seconds"),))
            connection.commit()
        finally:
            connection.close()

    def _login_ok(self, email):
        connection = self.database.get_connection()
        try:
            connection.execute("DELETE FROM login_attempts WHERE email = ?", (email.strip().lower()[:254],))
            connection.commit()
        finally:
            connection.close()

    # DELIVERY BOY LIST AND PHONE UPDATE (CAFE OWNER)
    def get_delivery_boys(self):
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT user_id, name, email, phone
                FROM users
                WHERE role = 'delivery_boy' AND is_active = 1
                ORDER BY user_id DESC""")
            return cursor.fetchall()
        finally:
            connection.close()

    def update_delivery_boy_phone(self, delivery_boy_id, phone, current_user):
        if current_user is None or not current_user.is_cafe():
            return False, "Only Cafe Owner can update this number."
        valid, result = validate_mobile(phone)
        if not valid:
            return False, result
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""UPDATE users
                SET phone = ?
                WHERE user_id = ? AND role = 'delivery_boy'""", (result, delivery_boy_id))
            if cursor.rowcount != 1:
                connection.rollback()
                return False, "Delivery Boy not found."
            connection.commit()
            return True, "Mobile number saved."
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # REMOVE DELIVERY BOY (CAFE OWNER)
    #
    # The account is deactivated, not deleted, so old orders still show
    # who delivered them. The email address is released so that it can be
    # used again, and the Delivery Boy is logged out.
    def remove_delivery_boy(self, delivery_boy_id, current_user):
        if current_user is None or not current_user.is_cafe():
            return False, "Only Cafe Owner can remove a Delivery Boy."
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("""SELECT user_id, name, email
                FROM users
                WHERE user_id = ? AND role = 'delivery_boy' AND is_active =
                    1""", (delivery_boy_id,))
            boy = cursor.fetchone()
            if boy is None:
                return False, "Delivery Boy not found."
            # not possible while he is carrying an order
            cursor.execute("""SELECT COUNT(*) AS active
                FROM deliveries d
                JOIN orders o ON d.order_id = o.order_id
                WHERE d.delivery_boy_id = ? AND o.status NOT IN ('DELIVERED',
                    'CANCELLED')""", (delivery_boy_id,))
            active = cursor.fetchone()["active"]
            if active:
                return False, (
                    f"{boy['name']} has {active} active order(s). "
                    "Remove this Delivery Boy after the delivery is completed."
                )
            released_email = f"removed.{boy['user_id']}.{boy['email']}"
            cursor.execute("""UPDATE users
                SET is_active = 0, email = ?
                WHERE user_id = ?""", (released_email, delivery_boy_id))
            connection.commit()
            return True, f"{boy['name']} has been removed."
        except Exception as error:
            connection.rollback()
            return False, f"Could not remove Delivery Boy: {error}"
        finally:
            connection.close()

    # CHANGE PASSWORD (logged-in user)
    def change_password(self, user_id, old_password, new_password):
        valid, message = validate_password(new_password)
        if not valid:
            return False, message
        if new_password == old_password:
            return False, "The new password must be different from the current password."
        connection = self.database.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT name, email, password FROM users WHERE user_id = ? AND is_active = 1", (user_id,))
            user = cursor.fetchone()
            if user is None or not self.verify_password(old_password or "", user["password"]):
                return False, "The current password is wrong."
            cursor.execute("UPDATE users SET password = ? WHERE user_id = ?",
                           (self.hash_password(new_password), user_id))
            connection.commit()
        except Exception as error:
            connection.rollback()
            return False, f"Could not change the password: {error}"
        finally:
            connection.close()
        self._notify_changed(user)
        return True, "Password changed successfully."

    def _notify_changed(self, user):
        if self.notifier is not None:
            try:
                self.notifier.notify_password_changed(user["email"], user["name"])
            except Exception:
                pass
