import unittest

from app.cli import _redact_secrets


class RedactSecretsTest(unittest.TestCase):
    def test_redacts_path_query_and_fragment(self) -> None:
        text = "failed https://rpc.example/v2/SECRET?api-key=TOPSECRET#fragment"

        redacted = _redact_secrets(text)

        self.assertEqual(redacted, "failed https://rpc.example/***")
        self.assertNotIn("SECRET", redacted)
        self.assertNotIn("TOPSECRET", redacted)

    def test_redacts_basic_auth_userinfo(self) -> None:
        text = "failed https://api-user:api-password@rpc.example:8545/v2/key"

        redacted = _redact_secrets(text)

        self.assertEqual(redacted, "failed https://rpc.example:8545/***")
        self.assertNotIn("api-user", redacted)
        self.assertNotIn("api-password", redacted)

    def test_redacts_multiple_urls(self) -> None:
        text = "first http://one.example/key then https://two.example?q=secret"

        self.assertEqual(
            _redact_secrets(text),
            "first http://one.example/*** then https://two.example/***",
        )


if __name__ == "__main__":
    unittest.main()
