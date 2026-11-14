import re
import unicodedata

INVALID_PATTERN_MESSAGE = (
    "Please enter a real mobile number. Numbers like 6666666666, "
    "7777777777 or 7888888888 are not allowed."
)

def _has_long_sequence(digits, length=8):
    """True for numbers such as 9876543210 or 6123456789."""
    for start in range(len(digits) - length + 1):
        window = [int(ch) for ch in digits[start:start + length]]
        steps = {window[i + 1] - window[i] for i in range(length - 1)}
        if steps == {1} or steps == {-1}:
            return True
    return False

def validate_mobile(raw_number):
    """Validate an Indian mobile number.

    Rules:
      * exactly 10 digits (+91 / 91 / 0 prefix is accepted and removed)
      * must start with 6, 7, 8 or 9
      * not a fake / pattern number:
          - fewer than 4 different digits (6666666666, 7888888888,
            9898989898 ...)
          - the same digit repeated 6 or more times in a row
          - a long running sequence (9876543210, 6123456789 ...)

    Returns (True, "10digitnumber") or (False, "error message").
    """
    digits = re.sub(r"\D", "", raw_number or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not digits:
        return False, "Mobile number is required."
    if len(digits) != 10:
        return False, "Mobile number must contain exactly 10 digits."
    if digits[0] not in "6789":
        return False, "Mobile number must start with 6, 7, 8 or 9."
    if len(set(digits)) < 4:
        return False, INVALID_PATTERN_MESSAGE
    if re.search(r"(\d)\1{5,}", digits):
        return False, INVALID_PATTERN_MESSAGE
    if _has_long_sequence(digits):
        return False, INVALID_PATTERN_MESSAGE
    return True, digits

def tel_link(phone, label=None):
    """Markdown link that opens the phone dialer when tapped."""
    phone = (phone or "").strip()
    if not phone:
        return ""
    return f"[📞 {label or phone}](tel:+91{phone})"

def validate_name(raw_name):
    """A name must contain only letters (and a single space between words).

    Digits and symbols such as 1234, Ram@12 or A_B are not allowed.
    Letters of any language (English, Hindi ...) are accepted.

    Returns (True, "CLEAN NAME") - saved in capital letters - or (False, "error message").
    """
    name = (raw_name or "").strip()
    if not name:
        return False, "Name is required."
    if re.search(r"\s{2,}", name):
        return False, "Name cannot have extra spaces. Use only one space between words."
    letters = 0
    for ch in name:
        if ch == " ":
            continue
        category = unicodedata.category(ch)
        # L* = letters, M* = marks of Hindi / other scripts (matras)
        if category[0] == "L":
            letters += 1
        elif category[0] == "M":
            continue
        else:
            return False, (
                "Name must contain only letters. "
                "Numbers and symbols are not allowed."
            )
    if letters < 2:
        return False, "Name must contain at least 2 letters."
    return True, name.upper()

def validate_city(raw_city):
    """A city name must contain only letters (and a single space between words).

    Digits and symbols such as 12345, Delhi1 or Pune@ are not allowed.
    Letters of any language (English, Hindi ...) are accepted.

    Returns (True, "Clean City") or (False, "error message").
    """
    city = (raw_city or "").strip()
    if not city:
        return False, "Please enter your city."
    if re.search(r"\s{2,}", city):
        return False, "City cannot have extra spaces. Use only one space between words."
    letters = 0
    for ch in city:
        if ch == " ":
            continue
        category = unicodedata.category(ch)
        # L* = letters, M* = marks of Hindi / other scripts (matras)
        if category[0] == "L":
            letters += 1
        elif category[0] == "M":
            continue
        else:
            return False, "City must contain only letters. Numbers and symbols are not allowed."
    if letters < 2:
        return False, "City must contain at least 2 letters."
    return True, " ".join(word.capitalize() for word in city.split(" "))

def validate_password(password):
    """Password rule: 6 to 64 characters. Returns (True, "") or (False, message)."""
    if not password or len(password) < 6:
        return False, "Password must contain at least 6 characters."
    if len(password) > 64:
        return False, "Password can have at most 64 characters."
    return True, ""

def display_name(name):
    """A name is always shown in CAPITAL letters with a single space between the words."""
    return " ".join((name or "").split()).upper()

def area_of(address):
    """Only the 'CITY - PIN' end of a delivery address (shown to Delivery Boys before they accept)."""
    return (address or "").split(",")[-1].strip() or "N/A"