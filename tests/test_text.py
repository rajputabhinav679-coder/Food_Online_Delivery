"""Tests for the wording of the app (labels, messages, emails, spelling consistency)."""
import pathlib
import re
import unittest

from utils import labels
from utils.validators import validate_name
from tests.helpers import ShopTestCase

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW_CODES = ["OUT_FOR_DELIVERY", "CASH_ON_DELIVERY", "PLACED", "CONFIRMED", "PREPARING",
             "DELIVERED", "CANCELLED", "SUCCESS", "FAILED", "PENDING", "delivery_boy"]

def project_files(*suffixes):
    for path in ROOT.rglob("*"):
        if path.suffix in suffixes and "tests" not in path.parts and ".git" not in path.parts:
            yield path

class LabelTests(unittest.TestCase):
    def test_order_status_names(self):
        self.assertEqual(labels.status_label("OUT_FOR_DELIVERY"), "Out for delivery")
        self.assertEqual(labels.status_label("PLACED"), "Placed")

    def test_payment_names(self):
        self.assertEqual(labels.payment_method_label("CASH_ON_DELIVERY"), "Cash on Delivery")
        self.assertEqual(labels.payment_status_label("SUCCESS"), "Paid")

    def test_role_names(self):
        self.assertEqual(labels.role_label("delivery_boy"), "Delivery Boy")
        self.assertEqual(labels.role_label("cafe"), "Cafe Owner")

    def test_unknown_or_empty_codes_never_show_underscores(self):
        self.assertEqual(labels.status_label(None), "N/A")
        self.assertNotIn("_", labels.status_label("SOME_NEW_STATE"))

class NameMessageTests(unittest.TestCase):
    def test_message_does_not_claim_only_english_letters(self):
        ok, message = validate_name("Ram123")
        self.assertFalse(ok)
        self.assertNotIn("A-Z", message)
        self.assertIn("Hindi", message)

    def test_hindi_name_is_accepted(self):
        self.assertTrue(validate_name("राम कुमार")[0])

class SpellingConsistencyTests(unittest.TestCase):
    """One spelling everywhere, so a new screen cannot bring the old mix back."""
    BANNED = {
        r"\b[Ee]-mail": "write 'Email' / 'email', not 'E-mail'",
        r"\bRs\b": "use the rupee sign ₹, not 'Rs'",
        r"\bDelivery boys?\b": "write 'Delivery Boy' with capital B",
        r"\bdelivery boys?\b": "write 'Delivery Boy' with capital letters",
        r"\bCafe owners?\b": "write 'Cafe Owner' with capital O",
        r"\bcafe owners?\b": "write 'Cafe Owner' with capital letters",
        r"Food-Online-Cafe": "the name is 'Food Online Cafe' (config APP_NAME)",
        r"\b(his|him|He|he)\b": "use gender-neutral words such as 'their'",
        r"\(A-Z\)": "names may contain Hindi letters too",
    }

    def test_no_banned_spelling_in_code_and_docs(self):
        problems = []
        for path in project_files(".py", ".txt", ".example"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for pattern, advice in self.BANNED.items():
                    if re.search(pattern, line):
                        problems.append(f"{path.relative_to(ROOT)}:{number}: {advice}: {line.strip()}")
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

class EmailTextTests(ShopTestCase):
    def test_new_order_mails_use_rupee_sign_and_friendly_words(self):
        self.place(method="UPI")
        text = "\n".join(m["subject"] + "\n" + m["body"] for m in self.mail.mails)
        self.assertIn("₹", text)
        self.assertIn("Food Online Cafe", text)
        self.assertNotIn("Rs", text)
        self.assertNotIn("E-mail", text)

    def test_delivery_boy_mail_has_no_raw_codes(self):
        order_id = self.place(method="CASH_ON_DELIVERY")
        self.orders.confirm_order(order_id)
        mail = [m for m in self.mail.mails if m["kind"] == "order_confirmed"][0]
        self.assertIn("Cash on Delivery (Pending)", mail["body"])
        for code in ("CASH_ON_DELIVERY", "PENDING"):
            self.assertNotIn(code, mail["body"])
