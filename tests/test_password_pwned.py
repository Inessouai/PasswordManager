import hashlib
import unittest
from unittest.mock import patch

from src.security.password_tools import check_pwned_password


class _Resp:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class PasswordPwnedTests(unittest.TestCase):
    def test_k_anonymity_sends_only_sha1_prefix(self):
        password = "password"
        sha1_hash = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
        prefix, suffix = sha1_hash[:5], sha1_hash[5:]

        with patch("src.security.password_tools.requests.get") as mock_get:
            mock_get.return_value = _Resp(200, f"{suffix}:12345\nABCDEF:2")
            compromised, count = check_pwned_password(password, timeout=3)

        self.assertTrue(compromised)
        self.assertEqual(count, 12345)
        called_url = mock_get.call_args.args[0]
        self.assertEqual(called_url, f"https://api.pwnedpasswords.com/range/{prefix}")
        self.assertNotIn(sha1_hash, called_url)
        self.assertTrue(called_url.endswith(f"/range/{prefix}"))

    def test_returns_not_compromised_for_non_200(self):
        with patch("src.security.password_tools.requests.get") as mock_get:
            mock_get.return_value = _Resp(503, "")
            compromised, count = check_pwned_password("StrongPass123!", timeout=2)
        self.assertFalse(compromised)
        self.assertEqual(count, 0)

    def test_ignores_malformed_lines(self):
        password = "StrongPass123!"
        with patch("src.security.password_tools.requests.get") as mock_get:
            mock_get.return_value = _Resp(200, "NO_COLON_LINE\nBAD:COUNT:EXTRA\n")
            compromised, count = check_pwned_password(password)
        self.assertFalse(compromised)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
