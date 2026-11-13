import json
from datetime import datetime
import urllib.error
import urllib.parse
import urllib.request
from config.sms_config import load_sms_settings
from utils.time_utils import now_ist, now_iso

API_URL = "https://www.fast2sms.com/dev/bulkV2"

class SmsService:
    """Sends the password-reset OTP as an SMS (Fast2SMS OTP route: "Your OTP: 123456")."""
    HOURLY_LIMIT = 30   # protects the wallet from SMS spamming

    def __init__(self, database, settings_loader=None, http_get=None):
        self.database = database
        self.settings_loader = settings_loader or load_sms_settings
        self.http_get = http_get or self._http_get

    def is_configured(self):
        return bool(self.settings_loader().get("api_key"))

    @staticmethod
    def _http_get(url, api_key):
        request = urllib.request.Request(url, headers={"authorization": api_key})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:       # Fast2SMS answers errors with a JSON body
            return json.loads(error.read().decode("utf-8") or "{}")

    def send_otp(self, phone, otp):
        """Returns True if the SMS was accepted by the provider."""
        settings = self.settings_loader()
        masked = phone[:2] + "*" * 6 + phone[-2:]
        if not settings.get("api_key"):
            return self._log(masked, "SKIPPED", "SMS is not configured (no api_key).")
        if self._sent_last_hour() >= self.HOURLY_LIMIT:
            return self._log(masked, "SKIPPED", "Hourly SMS limit reached.")
        query = urllib.parse.urlencode({"route": settings["route"], "variables_values": otp, "numbers": phone})
        try:
            answer = self.http_get(f"{API_URL}?{query}", settings["api_key"])
        except Exception as error:
            return self._log(masked, "FAILED", f"Could not reach the SMS server: {error}")
        if answer.get("return") is True:
            return self._log(masked, "SENT", "")
        message = answer.get("message")
        message = " ".join(message) if isinstance(message, list) else str(message)
        return self._log(masked, "FAILED", f"{answer.get('status_code', '')} {message}".strip())

    def _sent_last_hour(self):
        connection = self.database.get_connection()
        try:
            rows = connection.execute("SELECT created_at FROM notification_log WHERE kind = 'sms_otp' "
                                      "AND status = 'SENT' ORDER BY log_id DESC LIMIT ?", (self.HOURLY_LIMIT,)).fetchall()
        finally:
            connection.close()
        return sum(1 for row in rows if (now_ist() - datetime.fromisoformat(row["created_at"])).total_seconds() < 3600)

    def _log(self, masked, status, error):
        connection = self.database.get_connection()
        try:
            connection.execute("INSERT INTO notification_log (kind, recipient, subject, status, error, created_at) "
                               "VALUES ('sms_otp', ?, 'Password reset OTP (SMS)', ?, ?, ?)", (masked, status, error, now_iso()))
            connection.commit()
        finally:
            connection.close()
        return status == "SENT"
