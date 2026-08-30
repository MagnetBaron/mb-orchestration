#!/usr/bin/env python3
"""Regression tests for config-derived Grok CLI Visual QA packets and safety gates."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location("connectors_test_target", HERE / "connectors.py")
connectors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(connectors)


def live_config():
    return json.loads((ROOT / "config" / "connectors.json").read_text())


class VisualQaConfigTests(unittest.TestCase):
    def test_transport_is_named_grok_cli_without_slack(self):
        config = live_config()
        self.assertNotIn("slack", config)
        cli = config["grok_cli"]
        self.assertEqual((cli["transport"], cli["binary"], cli["model"]),
                         ("named-agent", "grok", "grok-4.6"))
        self.assertEqual(cli["roles"]["review-d"]["agent"], "mb-review-d")

    def test_two_modes_and_exact_live_policy(self):
        policy = live_config()["grok_cli"]["visual_qa"]
        modes = policy["modes"]
        self.assertEqual(set(modes), {"preview-review", "live-storefront-audit"})
        self.assertEqual(modes["preview-review"]["shared_preview_host"], "*.shopifypreview.com")
        self.assertEqual(modes["preview-review"]["configured_host_rules"], [{
            "store": "gadget-duke", "exact_host": "gadgetduke.com",
            "required_query_parameter": "preview_theme_id",
        }])
        self.assertEqual(modes["live-storefront-audit"]["host_match"], "exact")
        self.assertTrue(modes["live-storefront-audit"]["read_only"])

    def test_live_mode_denies_sensitive_paths_and_all_mutations(self):
        policy = live_config()["grok_cli"]["visual_qa"]
        deny = policy["deny_before_navigation"]
        self.assertTrue({"admin.shopify.com", "partners.shopify.com"}.issubset(deny["hosts"]))
        self.assertTrue({"/admin", "/checkout", "/account", "/login", "/auth"}.issubset(deny["path_prefixes"]))
        forbidden = set(policy["modes"]["live-storefront-audit"]["forbidden_actions"])
        self.assertTrue({"publish", "form-submit", "purchase", "add-to-cart", "any-mutation"}.issubset(forbidden))

    def test_cli_packets_are_derived_for_each_store_without_slack_tokens(self):
        config = live_config()
        for store, meta in config["stores"].items():
            with self.subTest(store=store):
                live = connectors.render_live_ticket(config, store)
                self.assertTrue(live.startswith("role: review-d\nmode: live-storefront-audit\n"))
                self.assertIn(f"url: https://{meta['live_hosts'][0]}/", live)
                if meta.get("review_d_preview_url"):
                    preview = connectors.render_ticket(config, store)
                    self.assertTrue(preview.startswith("role: review-d\nmode: preview-review\n"))
                else:
                    with self.assertRaisesRegex(SystemExit, "no concrete review_d_preview_url"):
                        connectors.render_ticket(config, store)
                    preview = ""
                self.assertNotIn("Slack", preview + live)
                self.assertNotIn("#visual-qa", preview + live)
                self.assertNotIn("@Website Visual QA", preview + live)

    def test_live_host_preview_fails_closed_without_exact_host_and_query(self):
        config = live_config()
        cases = [
            "https://gadgetduke.com/",
            "https://gadgetduke.com/?preview_theme_id=",
            "https://www.gadgetduke.com/?preview_theme_id=151997775942",
            "https://evil.example/?next=https://gadgetduke.com/?preview_theme_id=151997775942",
        ]
        for url in cases:
            with self.subTest(url=url):
                config["stores"]["gadget-duke"]["review_d_preview_url"] = url
                with self.assertRaisesRegex(SystemExit, "no safe configured CLI preview rule"):
                    connectors.render_ticket(config, "gadget-duke")

    def test_preview_denies_sensitive_paths_encoded_paths_and_markers(self):
        config = live_config()
        cases = [
            "https://gadgetduke.com/checkout?preview_theme_id=151997775942",
            "https://gadgetduke.com/%63heckout?preview_theme_id=151997775942",
            "https://gadgetduke.com/%2563heckout?preview_theme_id=151997775942",
            "https://gadgetduke.com/else/../checkout?preview_theme_id=151997775942",
            "https://gadgetduke.com/x/..%5Ccheckout?preview_theme_id=151997775942",
            "https://gadgetduke.com/products/simgym-demo?preview_theme_id=151997775942",
        ]
        for url in cases:
            with self.subTest(url=url):
                config["stores"]["gadget-duke"]["review_d_preview_url"] = url
                with self.assertRaisesRegex(SystemExit, "denied"):
                    connectors.render_ticket(config, "gadget-duke")

    def test_live_ticket_applies_same_deny_before_navigation_gate(self):
        config = live_config()
        config["stores"]["gadget-duke"]["live_hosts"] = ["admin.shopify.com"]
        with self.assertRaisesRegex(SystemExit, "denied host"):
            connectors.render_live_ticket(config, "gadget-duke")

    def test_allowlist_does_not_print_an_invalid_preview_url_as_usable(self):
        config = live_config()
        config["stores"]["gadget-duke"]["review_d_preview_url"] = (
            "https://gadgetduke.com/checkout?preview_theme_id=151997775942"
        )
        rendered = connectors.render_allowlist(config)
        self.assertIn("invalid; ticket renderer will refuse it", rendered)
        self.assertNotIn("https://gadgetduke.com/checkout?", rendered)

    def test_configured_live_host_preview_fails_if_rule_is_removed(self):
        config = live_config()
        config["grok_cli"]["visual_qa"]["modes"]["preview-review"]["configured_host_rules"] = []
        with self.assertRaisesRegex(SystemExit, "no safe configured CLI preview rule"):
            connectors.render_ticket(config, "gadget-duke")

    def test_allowlist_renders_mode_and_deny_gate_from_config(self):
        config = live_config()
        rendered = connectors.render_allowlist(config)
        policy = config["grok_cli"]["visual_qa"]
        self.assertIn("mode: live-storefront-audit", rendered)
        for host in policy["deny_before_navigation"]["hosts"]:
            self.assertIn(host, rendered)
        for prefix in policy["deny_before_navigation"]["path_prefixes"]:
            self.assertIn(prefix, rendered)


if __name__ == "__main__":
    unittest.main()
