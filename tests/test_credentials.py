import base64
import unittest

from api.credentials import decrypt_secret, encrypt_secret


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.env = {"SCOUTWISE_CREDENTIAL_ENCRYPTION_KEY": base64.urlsafe_b64encode(bytes(range(32))).decode()}

    def test_encrypt_decrypt_round_trip(self):
        encrypted = encrypt_secret("apify_test_token_123", environ=self.env)
        self.assertTrue(encrypted.startswith("v1."))
        self.assertNotIn("apify_test_token_123", encrypted)
        self.assertEqual(decrypt_secret(encrypted, environ=self.env), "apify_test_token_123")

    def test_wrong_key_cannot_decrypt(self):
        encrypted = encrypt_secret("apify_test_token_123", environ=self.env)
        wrong = {"SCOUTWISE_CREDENTIAL_ENCRYPTION_KEY": base64.urlsafe_b64encode(bytes(reversed(range(32)))).decode()}
        with self.assertRaises(Exception):
            decrypt_secret(encrypted, environ=wrong)


if __name__ == "__main__":
    unittest.main()
