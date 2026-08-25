#!/usr/bin/env python3
"""Deterministic validation for the capability-level role registry."""
from __future__ import annotations
import json, sys, tempfile, tomllib, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import generate

LIVE = HERE / "roles.json"


def live_registry() -> dict:
    return json.loads(LIVE.read_text())


def dump_and_load(data: dict):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "roles.json"
        path.write_text(json.dumps(data, indent=2) + "\n")
        return generate.load(path)


class RegistrySchemaTests(unittest.TestCase):
    def test_live_registry_loads(self):
        data = generate.load(LIVE)
        self.assertEqual(data["schema_version"], 2)
        self.assertEqual(tuple(data["capability_levels"]), generate.LEVELS)
        self.assertTrue(generate.REQUIRED_ROLES.issubset(data["roles"]))
        self.assertEqual(
            data["compatibility_aliases"]["review_order"],
            ["fable-5", "codex-sol", "opus-4.8", "review-e"],
        )

    def test_rejects_schema_version_1(self):
        data = live_registry()
        data["schema_version"] = 1
        with self.assertRaisesRegex(ValueError, "schema_version 2"):
            dump_and_load(data)

    def test_rejects_missing_or_reordered_levels(self):
        data = live_registry()
        data["capability_levels"] = {
            "sole": data["capability_levels"]["sole"],
            "frontier": data["capability_levels"]["frontier"],
            "terra": data["capability_levels"]["terra"],
            "luna": data["capability_levels"]["luna"],
        }
        with self.assertRaisesRegex(ValueError, "capability_levels"):
            dump_and_load(data)

    def test_rejects_model_family_requirement(self):
        data = live_registry()
        data["roles"]["seo-research"]["family"] = "anthropic"
        with self.assertRaisesRegex(ValueError, "model-family"):
            dump_and_load(data)

    def test_rejects_seat_level_mismatch(self):
        data = live_registry()
        data["roles"]["review-d"]["level"] = "frontier"
        with self.assertRaisesRegex(ValueError, "terra provider, not frontier"):
            dump_and_load(data)

    def test_rejects_unknown_review_order_provider(self):
        data = live_registry()
        data["compatibility_aliases"]["review_order"] = ["anthropic", "openai"]
        with self.assertRaisesRegex(ValueError, "replaceable providers"):
            dump_and_load(data)

    def test_rejects_provider_on_two_levels(self):
        data = live_registry()
        data["capability_levels"]["sole"]["providers"].append("fable-5")
        with self.assertRaisesRegex(ValueError, "more than one capability level"):
            dump_and_load(data)


class ReadOnlyRestrictionTests(unittest.TestCase):
    def test_read_only_roles_have_no_write_tools(self):
        data = generate.load(LIVE)
        for name, role in data["roles"].items():
            if not role["read_only"]:
                continue
            hosts = role.get("hosts", list(generate.HOSTS))
            for host in hosts:
                tools = generate.host_config(role, host)["tools"]
                overlap = generate.WRITE_TOOLS.intersection(tools)
                self.assertFalse(overlap, f"{name} {host} has write tools {overlap}")

    def test_read_only_forbids_write_on_writing_agent(self):
        data = live_registry()
        data["roles"]["seo-research"]["deny_tools"] = ["Admin", "publish"]
        data["roles"]["seo-research"]["grok"]["tools"] = [
            "Read", "Write", "Grep", "Glob", "WebSearch", "WebFetch"
        ]
        with self.assertRaisesRegex(ValueError, "read_only forbids write tools"):
            dump_and_load(data)

    def test_read_only_rejects_unknown_tool(self):
        data = live_registry()
        data["roles"]["seo-research"]["grok"]["tools"].append("shell")
        with self.assertRaisesRegex(ValueError, "unknown or non-read-safe"):
            dump_and_load(data)

    def test_read_only_forbids_write_on_claude_as_well(self):
        data = live_registry()
        data["roles"]["seo-research"]["deny_tools"] = ["Admin", "publish"]
        data["roles"]["seo-research"]["claude"]["tools"] = [
            "Read", "Write", "Glob", "Grep", "WebSearch", "WebFetch"
        ]
        with self.assertRaisesRegex(ValueError, "read_only forbids write tools"):
            dump_and_load(data)

    def test_non_read_only_may_grant_write_on_any_writing_host(self):
        data = live_registry()
        data["roles"]["grok-build"]["tools"]["claude"] = [
            "Read", "Write", "Edit", "Glob", "Grep"
        ]
        dump_and_load(data)

    def test_mcp_names_rejected_on_grok_without_adapter(self):
        data = live_registry()
        data["roles"]["seo-research"]["grok"]["mcpServers"] = ["gsc-indexing"]
        with self.assertRaisesRegex(ValueError, "Grok mcpServers are unsupported"):
            dump_and_load(data)

    def test_read_only_mcp_requires_mutation_denials(self):
        data = live_registry()
        data["roles"]["seo-research"]["mcp_deny_tools"]["claude"]["gsc-indexing"] = []
        with self.assertRaisesRegex(ValueError, "lacks mutation denials"):
            dump_and_load(data)

    def test_rejects_model_pin(self):
        data = live_registry()
        data["roles"]["seo-research"]["claude"]["model"] = "fable-5"
        with self.assertRaisesRegex(ValueError, "model pins are not allowed"):
            dump_and_load(data)

    def test_rejects_mcp_urls_and_credentials(self):
        data = live_registry()
        data["roles"]["seo-research"]["claude"]["mcpServers"] = ["https://example/mcp"]
        with self.assertRaisesRegex(ValueError, "connector names"):
            dump_and_load(data)

    def test_rejects_mcp_names_with_spaces(self):
        data = live_registry()
        data["roles"]["seo-research"]["claude"]["mcpServers"] = ["gsc indexing"]
        with self.assertRaisesRegex(ValueError, "connector names"):
            dump_and_load(data)


class ArtifactTests(unittest.TestCase):
    def render(self, data=None):
        data = data or generate.load(LIVE)
        tmp = Path(tempfile.mkdtemp())
        outputs = generate.artifacts(data, tmp / "claude", tmp / "grok", tmp / "codex.toml")
        return tmp, outputs

    def test_idempotent_bytes(self):
        data = generate.load(LIVE)
        tmp = Path(tempfile.mkdtemp())
        first = generate.artifacts(data, tmp / "claude", tmp / "grok", tmp / "codex.toml")
        second = generate.artifacts(data, tmp / "claude", tmp / "grok", tmp / "codex.toml")
        self.assertEqual(first, second)

    def test_toml_parses_and_carries_levels(self):
        _, outputs = self.render()
        toml_path = next(path for path in outputs if path.name == "codex.toml")
        parsed = tomllib.loads(outputs[toml_path])
        self.assertEqual(set(parsed["capability_levels"]), set(generate.LEVELS))
        self.assertEqual(
            parsed["compatibility_aliases"]["review_order"],
            ["fable-5", "codex-sol", "opus-4.8", "review-e"],
        )
        self.assertTrue(parsed["subagents"]["roles"]["review-d"]["read_only"])
        self.assertFalse(parsed["subagents"]["roles"]["grok-build"]["read_only"])
        self.assertEqual(parsed["subagents"]["roles"]["review-d"]["level"], "terra")
        blob = outputs[toml_path].lower()
        self.assertNotIn("anthropic", blob)
        self.assertNotIn("openai", blob)
        self.assertNotIn("model-family", blob)
        self.assertNotIn("cross-family", blob)

    def test_host_markdown_read_only_on_writing_agent(self):
        _, outputs = self.render()
        grok_seo = next(path for path in outputs if path.name == "mb-seo-research.md" and "grok" in path.parts)
        grok_build = next(path for path in outputs if path.name == "mb-grok-build.md" and "grok" in path.parts)
        seo_text = outputs[grok_seo]
        build_text = outputs[grok_build]
        self.assertIn("Read-only: yes. Write tools stay denied for every host, including writing agents.", seo_text)
        self.assertIn("tools: Read, Glob, Grep, WebSearch, WebFetch", seo_text)
        self.assertNotIn("Write", seo_text.split("---")[1])
        self.assertIn("Read-only: no. Write tools follow this role's host allowlists.", build_text)
        self.assertIn("Write", build_text.split("---")[1])

    def test_seo_research_omits_codex_and_declares_named_mcp_only(self):
        _, outputs = self.render()
        claude_seo = next(path for path in outputs if path.name == "mb-seo-research.md" and "claude" in path.parts)
        text = outputs[claude_seo]
        self.assertIn('mcpServers: ["gsc-indexing", "dfs-mcp"]', text)
        self.assertNotIn("sk-", text)
        self.assertTrue(all(p.name != "mb-seo-research.md" or "codex" not in p.parts for p in outputs))
        toml_path = next(path for path in outputs if path.name == "codex.toml")
        parsed = tomllib.loads(outputs[toml_path])
        self.assertNotIn("seo-research", parsed.get("subagents", {}).get("roles", {}))

    def test_check_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude = Path(tmp) / "claude"
            grok = Path(tmp) / "grok"
            codex = Path(tmp) / "codex.toml"
            generate.main([
                "--root", str(HERE),
                "--claude-dir", str(claude),
                "--grok-dir", str(grok),
                "--codex-output", str(codex),
                "--check",
            ])
            self.assertFalse(claude.exists())
            self.assertFalse(grok.exists())
            self.assertFalse(codex.exists())

    def test_write_then_identical_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude = Path(tmp) / "claude"
            grok = Path(tmp) / "grok"
            codex = Path(tmp) / "codex.toml"
            args = [
                "--root", str(HERE),
                "--claude-dir", str(claude),
                "--grok-dir", str(grok),
                "--codex-output", str(codex),
            ]
            generate.main(args)
            before = {p: p.read_bytes() for p in list(claude.iterdir()) + list(grok.iterdir()) + [codex]}
            generate.main(args)
            after = {p: p.read_bytes() for p in before}
            self.assertEqual(before, after)

    def test_refuses_protected_configs(self):
        for path in (Path.home() / ".codex/config.toml", Path.home() / ".claude/settings.json", Path.home() / ".grok/config.toml"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "protected config"):
                generate.write_atomic(path, "nope\n")


if __name__ == "__main__":
    unittest.main()
