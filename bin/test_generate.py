#!/usr/bin/env python3
"""Deterministic validation for the capability-level role registry (providers + roles split)."""
from __future__ import annotations
import importlib.util, json, sys, tempfile, tomllib, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parent / "config"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen = _load_module("generate_roles", HERE / "generate-roles.py")
LIVE_ROLES = CONFIG / "roles.json"
LIVE_PROV = CONFIG / "providers.json"


def live_roles():
    return json.loads(LIVE_ROLES.read_text())


def live_providers():
    return json.loads(LIVE_PROV.read_text())


def dump_and_load(roles=None, providers=None):
    roles = roles if roles is not None else live_roles()
    providers = providers if providers is not None else live_providers()
    with tempfile.TemporaryDirectory() as tmp:
        rp = Path(tmp) / "roles.json"
        pp = Path(tmp) / "providers.json"
        rp.write_text(json.dumps(roles, indent=2))
        pp.write_text(json.dumps(providers, indent=2))
        return gen.load(rp, pp)


class RegistrySchemaTests(unittest.TestCase):
    def test_live_registry_loads(self):
        reg = gen.load(LIVE_ROLES, LIVE_PROV)
        self.assertEqual(reg["providers"]["schema_version"], 4)
        self.assertEqual(tuple(reg["providers"]["capability_levels"]), gen.LEVELS)
        self.assertTrue(gen.REQUIRED_ROLES.issubset(reg["roles"]))
        self.assertEqual(reg["providers"]["review_order"],
                         ["opus-4.8", "codex-sol", "review-e"])

    def test_rejects_roles_schema_version_2(self):
        data = live_roles()
        data["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "schema_version 3"):
            dump_and_load(roles=data)

    def test_rejects_reordered_levels(self):
        prov = live_providers()
        prov["capability_levels"] = {
            "sole": prov["capability_levels"]["sole"],
            "frontier": prov["capability_levels"]["frontier"],
            "terra": prov["capability_levels"]["terra"],
            "luna": prov["capability_levels"]["luna"],
        }
        with self.assertRaisesRegex(ValueError, "frontier, sole, terra, luna"):
            dump_and_load(providers=prov)

    def test_rejects_model_family_requirement(self):
        data = live_roles()
        data["roles"]["seo-research"]["family"] = "anthropic"
        with self.assertRaisesRegex(ValueError, "model-family"):
            dump_and_load(roles=data)

    def test_rejects_seat_level_mismatch(self):
        data = live_roles()
        data["roles"]["review-d"]["level"] = "frontier"
        with self.assertRaisesRegex(ValueError, "terra provider, not frontier"):
            dump_and_load(roles=data)

    def test_rejects_unknown_review_order_provider(self):
        prov = live_providers()
        prov["review_order"] = ["anthropic", "openai"]
        with self.assertRaisesRegex(ValueError, "defined providers"):
            dump_and_load(providers=prov)

    def test_rejects_forbidden_model_selection(self):
        prov = live_providers()
        prov["providers"]["opus-4.8"]["model"] = "opus-5"
        with self.assertRaisesRegex(ValueError, "forbidden model"):
            dump_and_load(providers=prov)

    def test_rejects_unknown_seat(self):
        data = live_roles()
        data["roles"]["grok-build"]["seat"] = "nonesuch"
        with self.assertRaisesRegex(ValueError, "provider defined in providers.json"):
            dump_and_load(roles=data)


class ReadOnlyRestrictionTests(unittest.TestCase):
    def test_read_only_roles_have_no_write_tools(self):
        reg = gen.load(LIVE_ROLES, LIVE_PROV)
        for name, role in reg["roles"].items():
            if not role["read_only"]:
                continue
            hosts = role.get("hosts", list(gen.HOSTS))
            for host in hosts:
                tools = gen.host_config(role, host)["tools"]
                overlap = gen.WRITE_TOOLS.intersection(tools)
                self.assertFalse(overlap, f"{name} {host} has write tools {overlap}")

    def test_read_only_forbids_write_on_writing_agent(self):
        data = live_roles()
        data["roles"]["seo-research"]["deny_tools"] = ["Admin", "publish"]
        data["roles"]["seo-research"]["grok"]["tools"] = ["Read", "Write", "Grep", "Glob", "WebSearch", "WebFetch"]
        with self.assertRaisesRegex(ValueError, "read_only forbids write tools"):
            dump_and_load(roles=data)

    def test_read_only_rejects_unknown_tool(self):
        data = live_roles()
        data["roles"]["seo-research"]["grok"]["tools"].append("shell")
        with self.assertRaisesRegex(ValueError, "unknown or non-read-safe"):
            dump_and_load(roles=data)

    def test_read_only_forbids_write_on_claude_as_well(self):
        data = live_roles()
        data["roles"]["seo-research"]["deny_tools"] = ["Admin", "publish"]
        data["roles"]["seo-research"]["claude"]["tools"] = ["Read", "Write", "Glob", "Grep", "WebSearch", "WebFetch"]
        with self.assertRaisesRegex(ValueError, "read_only forbids write tools"):
            dump_and_load(roles=data)

    def test_non_read_only_may_grant_write(self):
        data = live_roles()
        data["roles"]["grok-build"]["tools"]["claude"] = ["Read", "Write", "Edit", "Glob", "Grep"]
        dump_and_load(roles=data)

    def test_mcp_names_rejected_on_grok(self):
        data = live_roles()
        data["roles"]["seo-research"]["grok"]["mcpServers"] = ["gsc-indexing"]
        with self.assertRaisesRegex(ValueError, "Grok mcpServers are unsupported"):
            dump_and_load(roles=data)

    def test_read_only_mcp_requires_mutation_denials(self):
        data = live_roles()
        data["roles"]["seo-research"]["mcp_deny_tools"]["claude"]["gsc-indexing"] = []
        with self.assertRaisesRegex(ValueError, "lacks mutation denials"):
            dump_and_load(roles=data)

    def test_read_only_rejects_unvetted_mcp_connector(self):
        # H1 fail-closed: a connector not declared in connectors.json cannot be used by a read_only role.
        data = live_roles()
        data["roles"]["seo-research"]["claude"]["mcpServers"] = ["gsc-indexing", "dfs-mcp", "totally-unknown-xyz"]
        with self.assertRaisesRegex(ValueError, "UNVETTED"):
            dump_and_load(roles=data)

    def test_rejects_model_pin(self):
        data = live_roles()
        data["roles"]["seo-research"]["claude"]["model"] = "fable-5"
        with self.assertRaisesRegex(ValueError, "model pins are not allowed"):
            dump_and_load(roles=data)

    def test_rejects_mcp_urls(self):
        data = live_roles()
        data["roles"]["seo-research"]["claude"]["mcpServers"] = ["https://example/mcp"]
        with self.assertRaisesRegex(ValueError, "connector names"):
            dump_and_load(roles=data)


class ArtifactTests(unittest.TestCase):
    def render(self):
        reg = gen.load(LIVE_ROLES, LIVE_PROV)
        tmp = Path(tempfile.mkdtemp())
        outputs = gen.artifacts(reg, tmp / "claude", tmp / "grok", tmp / "codex.toml")
        return tmp, outputs

    def test_idempotent_bytes(self):
        reg = gen.load(LIVE_ROLES, LIVE_PROV)
        tmp = Path(tempfile.mkdtemp())
        first = gen.artifacts(reg, tmp / "claude", tmp / "grok", tmp / "codex.toml")
        second = gen.artifacts(reg, tmp / "claude", tmp / "grok", tmp / "codex.toml")
        self.assertEqual(first, second)

    def test_toml_parses_and_carries_levels(self):
        _, outputs = self.render()
        toml_path = next(p for p in outputs if p.name == "codex.toml")
        parsed = tomllib.loads(outputs[toml_path])
        self.assertEqual(set(parsed["capability_levels"]), set(gen.LEVELS))
        self.assertEqual(parsed["review"]["order"], ["opus-4.8", "codex-sol", "review-e"])
        self.assertTrue(parsed["subagents"]["roles"]["review-d"]["read_only"])
        self.assertFalse(parsed["subagents"]["roles"]["grok-build"]["read_only"])
        self.assertEqual(parsed["subagents"]["roles"]["review-d"]["level"], "terra")
        blob = outputs[toml_path].lower()
        self.assertNotIn("model-family", blob)

    def test_host_markdown_read_only(self):
        _, outputs = self.render()
        grok_seo = next(p for p in outputs if p.name == "mb-seo-research.md" and "grok" in p.parts)
        grok_build = next(p for p in outputs if p.name == "mb-grok-build.md" and "grok" in p.parts)
        self.assertIn("Read-only: yes. Write tools stay denied for every host, including writing agents.", outputs[grok_seo])
        self.assertIn("tools: Read, Glob, Grep, WebSearch, WebFetch", outputs[grok_seo])
        self.assertNotIn("Write", outputs[grok_seo].split("---")[1])
        self.assertIn("Read-only: no. Write tools follow this role's host allowlists.", outputs[grok_build])
        self.assertIn("Write", outputs[grok_build].split("---")[1])

    def test_seo_omits_codex_and_declares_named_mcp(self):
        _, outputs = self.render()
        claude_seo = next(p for p in outputs if p.name == "mb-seo-research.md" and "claude" in p.parts)
        text = outputs[claude_seo]
        self.assertIn('mcpServers: ["gsc-indexing", "dfs-mcp"]', text)
        self.assertNotIn("sk-", text)
        self.assertTrue(all(p.name != "mb-seo-research.md" or "codex" not in p.parts for p in outputs))
        toml_path = next(p for p in outputs if p.name == "codex.toml")
        parsed = tomllib.loads(outputs[toml_path])
        self.assertNotIn("seo-research", parsed.get("subagents", {}).get("roles", {}))

    def test_check_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude = Path(tmp) / "claude"
            grok = Path(tmp) / "grok"
            codex = Path(tmp) / "codex.toml"
            gen.main(["--claude-dir", str(claude), "--grok-dir", str(grok),
                      "--codex-output", str(codex), "--check"])
            self.assertFalse(claude.exists())
            self.assertFalse(grok.exists())
            self.assertFalse(codex.exists())

    def test_refuses_protected_configs(self):
        for path in (Path.home() / ".codex/config.toml", Path.home() / ".claude/settings.json", Path.home() / ".grok/config.toml"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "protected config"):
                gen.write_atomic(path, "nope\n")


if __name__ == "__main__":
    unittest.main()
