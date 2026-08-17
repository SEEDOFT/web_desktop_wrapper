from __future__ import annotations

import unittest

from app.config_validators import (
    ConfigError,
    get_config_value,
    normalize_host,
    normalize_web_app_url,
    parse_bool,
    parse_hex_color,
    parse_int,
    parse_string,
    parse_url_list,
    slugify,
)


class ConfigValidatorsTests(unittest.TestCase):
    def test_parse_bool(self) -> None:
        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("1"))
        self.assertTrue(parse_bool("yes"))
        self.assertTrue(parse_bool("on"))
        self.assertTrue(parse_bool(True))

        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("0"))
        self.assertFalse(parse_bool("no"))
        self.assertFalse(parse_bool("off"))
        self.assertFalse(parse_bool(False))
        self.assertFalse(parse_bool(None, default=False))

        with self.assertRaises(ConfigError):
            parse_bool("invalid_bool_value")

    def test_parse_int(self) -> None:
        self.assertEqual(parse_int("1280", default=800), 1280)
        self.assertEqual(parse_int(None, default=800), 800)
        self.assertEqual(parse_int("100", minimum=50, maximum=150), 100)

        with self.assertRaises(ConfigError):
            parse_int("not_a_number")

        with self.assertRaises(ConfigError):
            parse_int("30", minimum=50)

        with self.assertRaises(ConfigError):
            parse_int("200", maximum=150)

    def test_parse_hex_color(self) -> None:
        self.assertEqual(parse_hex_color("#ffffff"), "#ffffff")
        self.assertEqual(parse_hex_color("#111827"), "#111827")
        self.assertEqual(parse_hex_color("#FFF000"), "#fff000")

        with self.assertRaises(ConfigError):
            parse_hex_color("white")

        with self.assertRaises(ConfigError):
            parse_hex_color("#12345")

    def test_parse_string(self) -> None:
        self.assertEqual(parse_string("  Hello World  "), "Hello World")
        self.assertEqual(parse_string(None, default="fallback"), "fallback")

    def test_parse_url_list(self) -> None:
        self.assertEqual(
            parse_url_list("a.com, b.com , c.com"),
            ["a.com", "b.com", "c.com"],
        )
        self.assertEqual(parse_url_list(["a.com", "b.com"]), ["a.com", "b.com"])
        self.assertEqual(parse_url_list(None, default=[]), [])

    def test_normalize_host(self) -> None:
        self.assertEqual(normalize_host(" App.Example.Com. "), "app.example.com")

    def test_normalize_web_app_url(self) -> None:
        self.assertEqual(normalize_web_app_url("localhost:8000"), "http://localhost:8000")
        self.assertEqual(normalize_web_app_url("127.0.0.1:3000"), "http://127.0.0.1:3000")
        self.assertEqual(
            normalize_web_app_url("https://app.example.com"),
            "https://app.example.com",
        )

    def test_slugify(self) -> None:
        self.assertEqual(slugify("DIGI Express Admin"), "DIGI-Express-Admin")
        self.assertEqual(slugify("Company / App #1"), "Company-App-1")

    def test_get_config_value(self) -> None:
        embedded = {"app_name": "Embedded App"}
        self.assertEqual(
            get_config_value("APP_NAME", embedded, "app_name", is_frozen=True),
            "Embedded App",
        )


if __name__ == "__main__":
    unittest.main()
