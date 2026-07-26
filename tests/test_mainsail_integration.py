import json
import pathlib
import sys
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "scripts"))
from mainsail_integration import add_nginx_include, merge_navigation


class MainsailIntegrationTests(unittest.TestCase):
    def test_navigation_is_idempotent_and_sorted(self):
        navigation = [
            {"title": "Configurator", "href": "/configure", "position": 80},
            {"title": "AutoPA", "href": "/old", "position": 10},
        ]
        entry = {
            "title": "AutoPA",
            "href": "/autopa/",
            "position": 83,
        }
        once = merge_navigation(navigation, entry)
        twice = merge_navigation(once, entry)
        self.assertEqual(once, twice)
        self.assertEqual(
            ["Configurator", "AutoPA"],
            [item["title"] for item in once])
        self.assertEqual("/autopa/", once[-1]["href"])
        json.dumps(once)

    def test_nginx_include_is_idempotent(self):
        source = "server {\n    listen 80;\n}\n"
        once = add_nginx_include(source)
        twice = add_nginx_include(once)
        self.assertEqual(once, twice)
        self.assertEqual(
            1, once.count("include /etc/nginx/snippets/autopa.conf;"))
        self.assertTrue(once.index("include /etc/nginx/snippets/autopa.conf;")
                        < once.rindex("\n}"))

    def test_unexpected_nginx_shape_is_rejected(self):
        with self.assertRaises(ValueError):
            add_nginx_include("events {}\n")


if __name__ == "__main__":
    unittest.main()
