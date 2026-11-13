import math
from datetime import datetime, timedelta, timezone
from config.app_config import ESTIMATED_DELIVERY_MINUTES
# Indian Standard Time. Streamlit Cloud servers run in UTC, so we always
# use IST explicitly, otherwise the order time would be 5.5 hours behind.
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    """Current IST time as a naive datetime."""
    return datetime.now(IST).replace(tzinfo=None)

def now_iso():
    """Current IST time as 'YYYY-MM-DDTHH:MM:SS' (stored in the database)."""
    return now_ist().isoformat(timespec="seconds")

def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None

def format_clock(dt):
    return dt.strftime("%I:%M %p").lstrip("0")

def format_datetime(value):
    dt = parse_dt(value)
    if dt is None:
        return str(value or "")
    return dt.strftime("%d %b %Y, ") + format_clock(dt)

def delivery_eta(created_at, status, delivery_time=None, minutes=ESTIMATED_DELIVERY_MINUTES):
    """Return (kind, message) to show the delivery time to the customer.

    kind is one of: "info", "success", "warning" or None (nothing to show).
    """
    if status == "CANCELLED":
        return None, ""
    created = parse_dt(created_at)
    if status == "DELIVERED":
        delivered = parse_dt(delivery_time)
        if created and delivered:
            taken = max(0, int((delivered - created).total_seconds() // 60))
            return "success", (f"✅ Delivered at {format_clock(delivered)} " f"(took {taken} min)")
        return "success", "✅ Delivered"
    if created is None:
        return "info", (f"⏱️ Delivery time: {minutes} minutes")
    expected = created + timedelta(minutes=minutes)
    seconds_left = (expected - now_ist()).total_seconds()
    if seconds_left > 0:
        minutes_left = math.ceil(seconds_left / 60)
        return "info", (
            f"⏱️ Your food will be delivered in about "
            f"**{minutes_left} min** (by {format_clock(expected)}). "
            f"Fixed delivery time: {minutes} min."
        )
    if seconds_left < -3 * 3600:
        return "warning", (
            f"⚠️ This order is very late (expected by "
            f"{format_clock(expected)} on {expected.strftime('%d %b')}). "
            "Please contact the cafe."
        )
    return "warning", (
        f"⏱️ Delivery is taking a little longer than {minutes} min "
        f"(expected by {format_clock(expected)}). "
        "Thank you for your patience."
    )
