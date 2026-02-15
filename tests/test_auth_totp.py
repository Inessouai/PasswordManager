import importlib
import os
import tempfile
import unittest


class AuthTotpTests(unittest.TestCase):
    def setUp(self):
        fd, db_path = tempfile.mkstemp(prefix="pg_auth_totp_", suffix=".db")
        os.close(fd)
        self.db_path = db_path
        self.db_url = "sqlite:///" + db_path.replace("\\", "/")
        os.environ["DATABASE_URL"] = self.db_url

        import database.engine as engine_module
        import database.models as models_module
        import src.auth.auth_manager as auth_module

        self.engine_module = importlib.reload(engine_module)
        self.models_module = importlib.reload(models_module)
        self.auth_module = importlib.reload(auth_module)
        self.engine_module.init_db()

        self.auth = self.auth_module.AuthManager()
        self.email = "mfa-test@example.com"
        self.password = "StrongPass123!"
        password_hash, salt = self.auth_module.hash_password(self.password)

        with self.engine_module.SessionLocal() as s:
            user = self.models_module.User(
                username="mfa-test",
                email=self.email,
                password_hash=password_hash,
                salt=salt,
                email_verified=True,
            )
            s.add(user)
            s.commit()
            s.refresh(user)
            self.user_id = int(user.id)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_authenticate_requires_totp_when_enabled(self):
        setup = self.auth.enable_totp(self.email)
        self.assertIn("secret", setup)

        result = self.auth.authenticate(self.email, self.password)
        self.assertIsNone(result.get("error"))
        self.assertTrue(result.get("mfa_required"))
        self.assertEqual(result.get("mfa_method"), "totp")
        self.assertFalse(result.get("2fa_sent"))

    def test_verify_totp_code(self):
        setup = self.auth.enable_totp(self.email)
        self.assertIn("secret", setup)

        try:
            import pyotp
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"pyotp unavailable: {exc}")

        code = pyotp.TOTP(setup["secret"]).now()
        self.assertTrue(self.auth.verify_totp(self.email, code))
        self.assertFalse(self.auth.verify_totp(self.email, "000000"))

    def test_trusted_device_skips_totp_prompt(self):
        setup = self.auth.enable_totp(self.email)
        self.assertIn("secret", setup)
        self.assertTrue(self.auth.trust_device(int(self.user_id), device_name="test-device", days=30))

        result = self.auth.authenticate(self.email, self.password, send_2fa=False)
        self.assertIsNone(result.get("error"))
        self.assertFalse(result.get("mfa_required"))
        self.assertFalse(result.get("2fa_sent"))

    def test_email_otp_fallback_when_totp_disabled(self):
        self.auth.send_2fa_code = lambda *_args, **_kwargs: True
        result = self.auth.authenticate(self.email, self.password, send_2fa=True)
        self.assertIsNone(result.get("error"))
        self.assertFalse(result.get("mfa_required"))
        self.assertTrue(result.get("2fa_sent"))


if __name__ == "__main__":
    unittest.main()
