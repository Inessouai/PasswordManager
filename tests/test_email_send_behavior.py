import unittest

from src.auth.auth_manager import AuthManager


class EmailSendBehaviorTests(unittest.TestCase):
    def test_register_user_fails_when_email_send_fails(self):
        auth = AuthManager()
        auth._user_by_email = lambda _email: None
        auth._create_user = lambda _username, _email, _password: 123
        auth._send_mail = lambda *_args, **_kwargs: False

        ok, msg, extra = auth.register_user("alice", "alice@example.com", "StrongPass123!")

        self.assertFalse(ok)
        self.assertIn("Impossible d'envoyer l'email", msg)
        self.assertEqual(extra.get("user_id"), 123)

    def test_resend_verification_returns_false_when_send_fails(self):
        auth = AuthManager()
        auth._user_by_email = lambda _email: {
            "id": 1,
            "username": "alice",
            "email": "alice@example.com",
            "email_verified": False,
        }
        auth._send_mail = lambda *_args, **_kwargs: False

        ok = auth.resend_verification_code("alice@example.com")

        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
