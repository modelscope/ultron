# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest

from ultron.utils.sanitizer import DataSanitizer


class TestDataSanitizerPII(unittest.TestCase):
    """Tests for Presidio-based PII detection in DataSanitizer."""

    @classmethod
    def setUpClass(cls):
        cls.sanitizer = DataSanitizer()

    def test_email_redacted(self):
        """Test that email addresses are redacted."""
        result = self.sanitizer.sanitize("Contact me at user@example.com")
        self.assertNotIn("user@example.com", result)
        self.assertIn("<EMAIL_ADDRESS>", result)

    def test_phone_number_redacted(self):
        """Test that US phone numbers are redacted."""
        result = self.sanitizer.sanitize("Call me at 212-555-5555")
        self.assertNotIn("212-555-5555", result)
        self.assertIn("<PHONE_NUMBER>", result)

    def test_chinese_phone_number_redacted(self):
        """Test that Chinese mobile numbers are redacted by regex fallback."""
        result = self.sanitizer.sanitize("手机号: 13812345678")
        self.assertNotIn("13812345678", result)
        self.assertIn("<PHONE_NUMBER>", result)

    def test_ip_address_redacted(self):
        """Test that IP addresses are redacted."""
        result = self.sanitizer.sanitize("Server IP: 192.168.1.100")
        self.assertNotIn("192.168.1.100", result)
        self.assertIn("<IP_ADDRESS>", result)

    def test_empty_string_returned_as_is(self):
        """Test that empty string input is returned unchanged."""
        self.assertEqual(self.sanitizer.sanitize(""), "")

    def test_none_returned_as_is(self):
        """Test that None input is returned unchanged."""
        self.assertIsNone(self.sanitizer.sanitize(None))

    def test_clean_text_unchanged(self):
        """Test that text with no PII passes through unchanged."""
        text = "The server returned a 404 error for the requested resource."
        result = self.sanitizer.sanitize(text)
        self.assertEqual(result, text)


class TestDataSanitizerChinesePII(unittest.TestCase):
    """Tests for Chinese PII detection in DataSanitizer."""

    @classmethod
    def setUpClass(cls):
        cls.sanitizer = DataSanitizer()

    def test_chinese_phone_number_redacted(self):
        """Test that Chinese mobile numbers in Chinese text are redacted."""
        result = self.sanitizer.sanitize("我的手机号是13812345678")
        self.assertNotIn("13812345678", result)
        self.assertIn("<PHONE_NUMBER>", result)

    def test_chinese_email_redacted(self):
        """Test that email addresses in Chinese text are redacted."""
        result = self.sanitizer.sanitize("联系邮箱：user@example.com，请尽快回复")
        self.assertNotIn("user@example.com", result)
        self.assertIn("<EMAIL_ADDRESS>", result)

    def test_chinese_person_name_redacted(self):
        """PERSON is excluded from Presidio to preserve useful context.
        Phone numbers should still be redacted."""
        result = self.sanitizer.sanitize("用户张三的手机号是13912345678")
        self.assertNotIn("13912345678", result)
        # PERSON is now excluded — name should be preserved
        self.assertNotIn("<PERSON>", result)
        self.assertIn("张三", result)

    def test_chinese_mixed_pii_redacted(self):
        """Test that mixed PII in Chinese text is fully redacted."""
        result = self.sanitizer.sanitize(
            "用户张三的邮箱是zhang@corp.com，手机13912345678"
        )
        self.assertNotIn("zhang@corp.com", result)
        self.assertNotIn("13912345678", result)


class TestDataSanitizerCredentials(unittest.TestCase):
    """Tests for regex-based credential and key redaction in DataSanitizer."""

    @classmethod
    def setUpClass(cls):
        cls.sanitizer = DataSanitizer()

    def test_openai_key_redacted(self):
        """Test that OpenAI/LLM API keys are redacted."""
        result = self.sanitizer.sanitize("sk-abcdefghijklmnopqrstuvwxyz123456")
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", result)
        self.assertIn("<LLM_API_KEY>", result)

    def test_github_token_redacted(self):
        """Test that GitHub personal access tokens are redacted."""
        result = self.sanitizer.sanitize("ghp_" + "a" * 36)
        self.assertNotIn("ghp_", result)
        self.assertIn("<GITHUB_TOKEN>", result)

    def test_github_oauth_token_redacted(self):
        """Test that GitHub OAuth tokens are redacted."""
        result = self.sanitizer.sanitize("gho_" + "b" * 36)
        self.assertNotIn("gho_", result)
        self.assertIn("<GITHUB_OAUTH_TOKEN>", result)

    def test_aws_access_key_redacted(self):
        """Test that AWS access keys are redacted."""
        result = self.sanitizer.sanitize("AKIAIOSFODNN7EXAMPLE")
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", result)
        self.assertIn("<AWS_ACCESS_KEY>", result)

    def test_bearer_token_redacted(self):
        """Test that Bearer authorization headers are redacted."""
        result = self.sanitizer.sanitize("Authorization: Bearer abc123token")
        self.assertNotIn("abc123token", result)
        self.assertIn("Bearer <REDACTED_TOKEN>", result)

    def test_basic_auth_redacted(self):
        """Test that Basic authorization headers are redacted."""
        result = self.sanitizer.sanitize("Authorization: Basic dXNlcjpwYXNz")
        self.assertNotIn("dXNlcjpwYXNz", result)
        self.assertIn("Basic <REDACTED>", result)

    def test_generic_password_field_redacted(self):
        """Test that generic password= assignments are redacted."""
        result = self.sanitizer.sanitize("password='mysecret123'")
        self.assertNotIn("mysecret123", result)
        self.assertIn("<REDACTED_CREDENTIAL>", result)

    def test_uuid_redacted(self):
        """Test that UUIDs are redacted."""
        result = self.sanitizer.sanitize("id: 550e8400-e29b-41d4-a716-446655440000")
        self.assertNotIn("550e8400-e29b-41d4-a716-446655440000", result)
        self.assertIn("<UUID>", result)


class TestDataSanitizerPaths(unittest.TestCase):
    """Tests for file path sanitization in DataSanitizer."""

    @classmethod
    def setUpClass(cls):
        cls.sanitizer = DataSanitizer()

    def test_unix_home_path_redacted(self):
        """Test that /home/<username> paths are redacted."""
        result = self.sanitizer.sanitize("/home/xinyin/project/config.py")
        self.assertNotIn("xinyin", result)
        self.assertIn("/home/<USER>", result)

    def test_macos_users_path_redacted(self):
        """Test that /Users/<username> paths are redacted."""
        result = self.sanitizer.sanitize("/Users/john/Documents/secret.txt")
        self.assertNotIn("john", result)
        self.assertIn("/Users/<USER>", result)

    def test_filename_preserved_after_path_redaction(self):
        """Test that the filename is preserved after path username is redacted."""
        result = self.sanitizer.sanitize("/home/xinyin/project/secret.py")
        self.assertIn("secret.py", result)


class TestDataSanitizerCustomPatterns(unittest.TestCase):
    """Tests for custom pattern support in DataSanitizer."""

    def test_custom_pattern_applied(self):
        """Test that custom patterns are applied during sanitization."""
        sanitizer = DataSanitizer(custom_patterns=[(r"PROJ-\d+", "<TICKET>")])
        result = sanitizer.sanitize("Fixed in PROJ-1234")
        self.assertNotIn("PROJ-1234", result)
        self.assertIn("<TICKET>", result)

    def test_multiple_custom_patterns(self):
        """Test that multiple custom patterns are all applied."""
        sanitizer = DataSanitizer(
            custom_patterns=[
                (r"PROJ-\d+", "<TICKET>"),
                (r"release-\d+", "<RELEASE>"),
            ]
        )
        result = sanitizer.sanitize("Fixed PROJ-42 in release-99")
        self.assertIn("<TICKET>", result)
        self.assertIn("<RELEASE>", result)


if __name__ == "__main__":
    unittest.main()
