# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest

import jwt

from ultron.services.auth import AuthService


class TestAuthServicePassword(unittest.TestCase):
    def test_hash_and_verify(self):
        hashed = AuthService.hash_password("secret123")
        self.assertTrue(AuthService.verify_password("secret123", hashed))

    def test_wrong_password_fails(self):
        hashed = AuthService.hash_password("correct")
        self.assertFalse(AuthService.verify_password("wrong", hashed))

    def test_hash_is_different_each_time(self):
        h1 = AuthService.hash_password("pw")
        h2 = AuthService.hash_password("pw")
        self.assertNotEqual(h1, h2)

    def test_empty_password(self):
        hashed = AuthService.hash_password("")
        self.assertTrue(AuthService.verify_password("", hashed))


class TestAuthServiceJWT(unittest.TestCase):
    def setUp(self):
        self.svc = AuthService(secret="test-secret", expire_hours=1)

    def test_create_and_decode_token(self):
        token = self.svc.create_token("alice")
        username = self.svc.decode_token(token)
        self.assertEqual(username, "alice")

    def test_invalid_token_raises(self):
        with self.assertRaises(jwt.PyJWTError):
            self.svc.decode_token("not.a.valid.token")

    def test_wrong_secret_raises(self):
        token = self.svc.create_token("alice")
        other_svc = AuthService(secret="different-secret")
        with self.assertRaises(jwt.PyJWTError):
            other_svc.decode_token(token)

    def test_expired_token_raises(self):
        svc = AuthService(secret="test-secret", expire_hours=0)
        token = svc.create_token("alice")
        with self.assertRaises(jwt.PyJWTError):
            svc.decode_token(token)

    def test_token_contains_username(self):
        token = self.svc.create_token("bob")
        # Decode without verification to inspect payload
        payload = jwt.decode(token, options={"verify_signature": False})
        self.assertEqual(payload["sub"], "bob")


if __name__ == "__main__":
    unittest.main()
