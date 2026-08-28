#!/usr/bin/env python3
"""Deterministic tests for the selective skill registry."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import sync


class RegistryTests(unittest.TestCase):
    def test_live_registry_shape(self):
        data = sync.load_registry()
        self.assertEqual(data["schema_version"], 3)
        self.assertEqual(set(data["bundles"]), {"mobile", "cloudflare", "knowledge", "engineering"})
        self.assertEqual(len(sync.leaf_catalog(data)), 44)
        self.assertEqual(
            {bundle["router"]["name"] for bundle in data["bundles"].values()},
            {"mobile-dev-router", "cloudflare-dev-router", "knowledge-vault-router", "engineering-dev-router"},
        )

    def load_copy(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps(data))
            return sync.load_registry(path)

    def test_rejects_duplicate_leaf_across_bundles(self):
        data = copy.deepcopy(sync.load_registry())
        data["bundles"]["engineering"]["sources"]["anthropic-mcp"]["skills"] = ["cloudflare"]
        with self.assertRaisesRegex(ValueError, "only one bundle"):
            self.load_copy(data)

    def test_rejects_leaf_on_progressive_route(self):
        data = copy.deepcopy(sync.load_registry())
        data["bundles"]["knowledge"]["routes"]["default"]["skills"] = ["obsidian-markdown"]
        with self.assertRaisesRegex(ValueError, "expose only the router"):
            self.load_copy(data)

    def test_rejects_unknown_route_skill(self):
        data = copy.deepcopy(sync.load_registry())
        data["bundles"]["cloudflare"]["routes"]["default"]["skills"] = ["invented"]
        with self.assertRaisesRegex(ValueError, "unknown skills"):
            self.load_copy(data)

    def test_custom_source_path_keeps_frontmatter_name(self):
        data = sync.load_registry()
        leaf = next(item for item in sync.leaf_catalog(data) if item["name"] == "vercel-composition-patterns")
        self.assertEqual(leaf["directory"], "composition-patterns")
        self.assertEqual(leaf["path"], "skills/composition-patterns")

    def test_all_router_sources_exist(self):
        data = sync.load_registry()
        for bundle in data["bundles"].values():
            self.assertTrue((sync.REPO / bundle["router"]["path"] / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
