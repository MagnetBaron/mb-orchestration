#!/usr/bin/env python3
"""Regression tests for config-derived Website Visual QA tickets and safety metadata."""
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
    def test_two_narrow_routines_and_exact_live_prefix(self):
        policy = live_config()["slack"]["visual_qa"]
        self.assertEqual(policy["event_filter_semantics"], "contains-only")
        routines = policy["routines"]
        self.assertEqual(set(routines), {"preview-review", "live-storefront-audit"})
        self.assertEqual(routines["preview-review"]["event_contains"], "shopifypreview.com")
        live = routines["live-storefront-audit"]
        self.assertEqual(live["event_contains"], "visual-qa: live-audit")
        self.assertEqual(live["message_must_begin_exact"], "visual-qa: live-audit")
        self.assertEqual(live["host_match"], "exact")
        self.assertTrue(live["read_only"])

    def test_live_mode_denies_sensitive_paths_and_all_mutations(self):
        policy = live_config()["slack"]["visual_qa"]
        deny = policy["deny_before_navigation"]
        self.assertTrue({"admin.shopify.com", "partners.shopify.com"}.issubset(deny["hosts"]))
        self.assertTrue({
            "/admin", "/checkout", "/account", "/login", "/auth",
            "/customer_authentication", "/challenge", "/password", "/signin", "/sign-in",
        }.issubset(
            deny["path_prefixes"]
        ))
        self.assertIn("simgym", deny["case_insensitive_markers"])
        forbidden = set(policy["routines"]["live-storefront-audit"]["forbidden_actions"])
        self.assertTrue({
            "publish", "customize", "theme-editor", "form-submit", "purchase",
            "add-to-cart", "any-mutation",
        }.issubset(forbidden))

    def test_message_loop_and_mixed_token_guards(self):
        guards = live_config()["slack"]["visual_qa"]["message_guards"]
        self.assertTrue(guards["ignore_own_posts"])
        self.assertTrue(guards["ignore_quoted_or_thread_reposts"])
        self.assertTrue(guards["replies_omit_all_trigger_tokens"])
        self.assertEqual(set(guards["mixed_tokens_block"]), {
            "shopifypreview.com", "visual-qa: live-audit", "clarity deep-dive:",
        })

    def test_live_tickets_are_derived_for_each_configured_store(self):
        config = live_config()
        trigger = config["slack"]["visual_qa"]["routines"]["live-storefront-audit"][
            "message_must_begin_exact"
        ]
        for store, meta in config["stores"].items():
            with self.subTest(store=store):
                rendered = connectors.render_live_ticket(config, store)
                payload, routing_hint = rendered.split("\n--- non-copy routing hint ---\n", 1)
                first_nonblank = next(line for line in payload.splitlines() if line.strip())
                self.assertEqual(first_nonblank, trigger)
                self.assertTrue(rendered.startswith(trigger + "\n"))
                self.assertIn(f"url: https://{meta['live_hosts'][0]}/", payload)
                self.assertIn("scope: public storefront read-only", payload)
                self.assertNotIn("preview_theme_id", payload)
                self.assertNotIn("checkout", payload.lower())
                self.assertNotIn("Destination channel:", payload)
                expected_channel = config["slack"]["visual_qa_channel"]["name"]
                self.assertEqual(routing_hint, f"Destination channel: {expected_channel}\n")

    def test_preview_ticket_remains_preview_scoped(self):
        config = live_config()
        rendered = connectors.render_ticket(config, "magnet-baron")
        self.assertIn("shopifypreview.com", rendered)
        self.assertNotIn("visual-qa: live-audit", rendered)

    def test_allowlist_renders_live_mode_and_deny_gate_from_config(self):
        config = live_config()
        rendered = connectors.render_allowlist(config)
        policy = config["slack"]["visual_qa"]
        trigger = policy["routines"]["live-storefront-audit"]["message_must_begin_exact"]
        self.assertIn(trigger, rendered)
        for host in policy["deny_before_navigation"]["hosts"]:
            self.assertIn(host, rendered)
        for prefix in policy["deny_before_navigation"]["path_prefixes"]:
            self.assertIn(prefix, rendered)


if __name__ == "__main__":
    unittest.main()
