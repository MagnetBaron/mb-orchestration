#!/usr/bin/env python3
"""Deterministic validation for the capability-level role registry (providers + roles split)."""
from __future__ import annotations
import importlib.util, json, os, sys, tempfile, tomllib, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parent / "config"
os.environ.setdefault(
    "MB_INTEGRATION_FIXTURE",
    str(HERE.parent / "model-evals/fixtures/integrations/all-observed.json"),
)


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
                         ["opus-5", "codex-sol", "review-e"])
        self.assertIn("marketplace-intelligence", reg["roles"])
        marketplace = reg["providers"]["providers"]["grok-bot-marketplace-intelligence"]
        self.assertEqual(marketplace["model"], "grok-4.6")
        self.assertFalse(marketplace["wired"])

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
        prov["forbidden_models"] = {"do-not-run": {"aliases": ["never-this-model"]}}
        prov["providers"]["opus-5"]["model"] = "never-this-model"
        with self.assertRaisesRegex(ValueError, "forbidden model"):
            dump_and_load(providers=prov)

    def test_opus_5_is_not_auto_forbidden(self):
        dump_and_load()

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
        self.assertEqual(parsed["review"]["order"], ["opus-5", "codex-sol", "review-e"])
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

    def test_marketplace_role_is_generated_read_only_and_unwired(self):
        _, outputs = self.render()
        for host in ("claude", "grok"):
            path = next(
                p for p in outputs
                if p.name == "mb-marketplace-intelligence.md" and host in p.parts
            )
            text = outputs[path]
            self.assertIn("Read-only: yes", text)
            self.assertIn("owner-supplied marketplace", text)
            self.assertNotIn("tools: Read, Write", text)
        codex_path = next(p for p in outputs if p.name == "codex.toml")
        parsed = tomllib.loads(outputs[codex_path])
        role = parsed["subagents"]["roles"]["marketplace-intelligence"]
        self.assertTrue(role["read_only"])
        self.assertEqual(role["seat"], "grok-bot-marketplace-intelligence")
        self.assertIn("bid", role["deny_tools"])

    def test_marketplace_seat_exec_is_named_agent_cli_evidence_input(self):
        seat = json.loads((CONFIG / "seat-exec.json").read_text())
        recipe = seat["recipes"]["grok-bot-marketplace-intelligence"]
        self.assertEqual(recipe["bin"], "grok")
        self.assertEqual(recipe["required_agent"], "mb-marketplace-intelligence")
        self.assertIn("--agent", recipe["args_template"])
        self.assertIn("grok-4.6", recipe["args_template"])
        self.assertEqual(recipe["reads"], "marketplace-evidence")
        self.assertFalse(recipe["worktree"])
        self.assertTrue(recipe["never_metered_host"])

    def test_marketplace_cli_keeps_website_automation_and_activation_parked(self):
        text = (HERE.parent / "marketplace-intelligence.md").read_text()
        self.assertIn("approved deposited snapshots/exports", text)
        self.assertIn("Browser automation or scraping is never inferred", text)
        self.assertIn("route is `unwired`", text)
        self.assertIn("CLI/profile presence alone grants no", text)
        self.assertIn("marketplace permission", text)
        self.assertIn("Never browse/scrape eBay or Reverb", text)

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


routing = _load_module("routing_mod", HERE / "routing.py")
doc = _load_module("doctor_mod", HERE / "doctor.py")


class ConnectorLifecycleTests(unittest.TestCase):
    def test_missing_unknown_primed_ready_are_inert(self):
        self.assertFalse(routing.connector_is_active({}))
        self.assertFalse(routing.connector_is_active(None))
        self.assertFalse(routing.connector_is_active({"status": "unknown"}))
        self.assertFalse(routing.connector_is_active({"status": "bogus"}))
        self.assertFalse(routing.connector_is_active({"status": "primed"}))
        self.assertFalse(routing.connector_is_active({"status": "ready"}))
        self.assertTrue(routing.connector_is_active({"status": "active"}))

    def test_primed_shopify_does_not_satisfy_write_skill_gate(self):
        conns = {"mcp_connectors": {
            "shopify-mb-internal": {
                "status": "primed",
                "available_on": ["grok-build"],
                "mutating_tools": ["update-product"],
            },
        }}
        prov = {"providers": {"grok-build": {"capabilities": ["code"]}}}
        self.assertFalse(gen.seat_has_capability("grok-build", "shopify-mb-internal", prov, conns))
        conns["mcp_connectors"]["shopify-mb-internal"]["status"] = "unknown"
        self.assertFalse(gen.seat_has_capability("grok-build", "shopify-mb-internal", prov, conns))
        del conns["mcp_connectors"]["shopify-mb-internal"]["status"]
        self.assertFalse(gen.seat_has_capability("grok-build", "shopify-mb-internal", prov, conns))
        conns["mcp_connectors"]["shopify-mb-internal"]["status"] = "active"
        self.assertTrue(gen.seat_has_capability("grok-build", "shopify-mb-internal", prov, conns))

    def test_missing_status_is_not_granted_by_router(self):
        conns = json.loads((CONFIG / "connectors.json").read_text())
        del conns["mcp_connectors"]["github"]["status"]
        prov = live_providers()["providers"]
        for pid in conns["mcp_connectors"]["github"]["available_on"]:
            caps = routing.capabilities_of(pid, prov.get(pid, {}), conns)
            self.assertNotIn("github", caps)

    def test_live_active_connectors_still_grant(self):
        conns = json.loads((CONFIG / "connectors.json").read_text())
        self.assertEqual(conns["mcp_connectors"]["shopify-mb-internal"]["status"], "active")
        self.assertEqual(conns["mcp_connectors"]["mb-bundled-example"]["status"], "primed")
        prov = live_providers()["providers"]
        self.assertIn(
            "shopify-mb-internal",
            routing.capabilities_of("grok-build", prov["grok-build"], conns),
        )
        self.assertNotIn(
            "mb-bundled-example",
            routing.capabilities_of("grok-build", prov["grok-build"], conns),
        )

    def test_doctor_errors_on_missing_and_unknown_status(self):
        conns = json.loads((CONFIG / "connectors.json").read_text())
        provs = live_providers()
        del conns["mcp_connectors"]["github"]["status"]
        doc.ERRORS.clear()
        doc.check_connector_lifecycle(conns, provs)
        self.assertTrue(any("github" in e and "status" in e for e in doc.ERRORS), doc.ERRORS)
        conns["mcp_connectors"]["github"]["status"] = "wired-maybe"
        doc.ERRORS.clear()
        doc.check_connector_lifecycle(conns, provs)
        self.assertTrue(any("github" in e and "wired-maybe" in e for e in doc.ERRORS), doc.ERRORS)

    def _luna_github_primed(self):
        conns = json.loads((CONFIG / "connectors.json").read_text())
        provs = live_providers()
        provs["providers"]["codex-luna"]["capabilities"] = list(
            provs["providers"]["codex-luna"]["capabilities"]
        ) + ["github"]
        conns["mcp_connectors"]["github"]["status"] = "primed"
        return provs, conns

    def test_primed_github_coarse_label_does_not_leak_to_luna(self):
        """Exact regression: github on codex-luna.capabilities + primed connector."""
        provs, conns = self._luna_github_primed()
        luna = provs["providers"]["codex-luna"]
        caps = routing.capabilities_of("codex-luna", luna, conns)
        self.assertNotIn("github", caps)
        self.assertFalse(gen.seat_has_capability("codex-luna", "github", provs, conns))

    def test_primed_github_coarse_label_skill_gate_fails(self):
        provs, conns = self._luna_github_primed()
        self.assertFalse(gen.seat_has_capability("codex-luna", "github", provs, conns))
        skills = json.loads((CONFIG / "skills.json").read_text())
        skills["skills"]["magnet-baron-skills:shopify-theme"]["required_capability"] = "github"
        roles = live_roles()
        orig = gen.mborch.load_config

        def fake(name, required=True):
            if name == "connectors.json":
                return conns
            if name == "skills.json":
                return skills
            return orig(name, required=required)

        gen.mborch.load_config = fake
        try:
            with self.assertRaisesRegex(ValueError, r"lacks capability 'github'"):
                dump_and_load(roles=roles, providers=provs)
        finally:
            gen.mborch.load_config = orig

    def test_doctor_reports_github_capability_collision(self):
        provs, conns = self._luna_github_primed()
        doc.ERRORS.clear()
        doc.check_connector_lifecycle(conns, provs)
        blob = "\n".join(doc.ERRORS)
        self.assertTrue(
            any("codex-luna" in e and "github" in e and "collides" in e for e in doc.ERRORS),
            blob,
        )

    def test_missing_unknown_primed_coarse_labels_do_not_grant(self):
        conns = json.loads((CONFIG / "connectors.json").read_text())
        provs = live_providers()
        grok = provs["providers"]["grok-build"]
        grok["capabilities"] = list(grok["capabilities"]) + ["github"]
        for status in (None, "unknown", "primed", "ready"):
            if status is None:
                conns["mcp_connectors"]["github"].pop("status", None)
            else:
                conns["mcp_connectors"]["github"]["status"] = status
            caps = routing.capabilities_of("grok-build", grok, conns)
            self.assertNotIn("github", caps, status)
            self.assertFalse(gen.seat_has_capability("grok-build", "github", provs, conns), status)
            self.assertFalse(gen.seat_has_capability("codex-luna", "github", provs, conns), status)

    def test_doctor_inertness_checks_providers_not_in_available_on(self):
        """Coarse-label leak on a seat outside available_on is still a doctor error."""
        provs, conns = self._luna_github_primed()
        self.assertNotIn("codex-luna", conns["mcp_connectors"]["github"]["available_on"])
        doc.ERRORS.clear()
        doc.check_connector_lifecycle(conns, provs)
        self.assertTrue(
            any("codex-luna" in e and "github" in e for e in doc.ERRORS),
            doc.ERRORS,
        )

    def test_active_connector_still_grants_via_available_on_not_coarse_label(self):
        conns = json.loads((CONFIG / "connectors.json").read_text())
        provs = live_providers()
        self.assertEqual(conns["mcp_connectors"]["github"]["status"], "active")
        self.assertIn(
            "github",
            routing.capabilities_of("grok-build", provs["providers"]["grok-build"], conns),
        )
        self.assertNotIn(
            "github",
            routing.capabilities_of("codex-luna", provs["providers"]["codex-luna"], conns),
        )
        self.assertTrue(gen.seat_has_capability("grok-build", "github", provs, conns))
        self.assertFalse(gen.seat_has_capability("codex-luna", "github", provs, conns))

    def test_coarse_vocabulary_is_not_connector_derived(self):
        catalog = {k for k in live_providers()["capability_catalog"] if k != "_note"}
        self.assertEqual(catalog, set(routing.COARSE_CAPABILITIES))
        conns = json.loads((CONFIG / "connectors.json").read_text())
        derived = routing.connector_derived_labels(conns)
        self.assertTrue(derived.isdisjoint(routing.COARSE_CAPABILITIES))
        self.assertIn("google-mcp", derived)
        self.assertIn("github", derived)
        self.assertNotIn("code", derived)

    def test_coarse_code_survives_primed_github(self):
        conns = json.loads((CONFIG / "connectors.json").read_text())
        conns["mcp_connectors"]["github"]["status"] = "primed"
        grok = live_providers()["providers"]["grok-build"]
        caps = routing.capabilities_of("grok-build", grok, conns)
        self.assertIn("code", caps)
        self.assertNotIn("github", caps)

    def _luna_google_mcp_class_primed(self):
        conns = json.loads((CONFIG / "connectors.json").read_text())
        provs = live_providers()
        for meta in conns["mcp_connectors"].values():
            if isinstance(meta, dict) and meta.get("class") == "google-mcp":
                meta["status"] = "primed"
        luna = provs["providers"]["codex-luna"]
        luna["capabilities"] = list(luna["capabilities"]) + ["google-mcp"]
        return provs, conns

    def test_primed_google_mcp_class_does_not_leak_to_luna(self):
        """Exact regression: google-mcp on codex-luna.capabilities + every google-mcp primed."""
        provs, conns = self._luna_google_mcp_class_primed()
        luna = provs["providers"]["codex-luna"]
        caps = routing.capabilities_of("codex-luna", luna, conns)
        self.assertNotIn("google-mcp", caps)
        self.assertFalse(gen.seat_has_capability("codex-luna", "google-mcp", provs, conns))
        terra = provs["providers"]["codex-terra"]
        self.assertNotIn(
            "google-mcp",
            routing.capabilities_of("codex-terra", terra, conns),
        )

    def test_primed_google_mcp_class_skill_gate_fails(self):
        """luna.capabilities google-mcp must not satisfy a skill gate when every google-mcp is primed."""
        provs, conns = self._luna_google_mcp_class_primed()
        self.assertFalse(gen.seat_has_capability("codex-luna", "google-mcp", provs, conns))
        skills = json.loads((CONFIG / "skills.json").read_text())
        skills["skills"]["magnet-baron-skills:shopify-theme"]["required_capability"] = "google-mcp"
        roles = live_roles()
        roles["roles"]["shopify-theme-build"]["seat"] = "codex-luna"
        roles["roles"]["shopify-theme-build"]["level"] = "luna"
        # Priming every google-mcp connector also primes gsc-indexing; drop it so the
        # skill-gate error (luna lacks google-mcp) is the one we observe.
        roles["roles"]["seo-research"]["claude"]["mcpServers"] = []
        roles["roles"]["seo-research"]["mcp_deny_tools"] = {}
        orig = gen.mborch.load_config

        def fake(name, required=True):
            if name == "connectors.json":
                return conns
            if name == "skills.json":
                return skills
            return orig(name, required=required)

        gen.mborch.load_config = fake
        try:
            with self.assertRaisesRegex(ValueError, r"lacks capability 'google-mcp'"):
                dump_and_load(roles=roles, providers=provs)
        finally:
            gen.mborch.load_config = orig

    def test_doctor_reports_google_mcp_class_capability_collision(self):
        provs, conns = self._luna_google_mcp_class_primed()
        doc.ERRORS.clear()
        doc.check_connector_lifecycle(conns, provs)
        blob = "\n".join(doc.ERRORS)
        self.assertTrue(
            any("codex-luna" in e and "google-mcp" in e and "collides" in e for e in doc.ERRORS),
            blob,
        )

    def test_active_google_mcp_class_grants_via_connector_not_coarse_label(self):
        conns = json.loads((CONFIG / "connectors.json").read_text())
        provs = live_providers()
        terra = provs["providers"]["codex-terra"]
        luna = provs["providers"]["codex-luna"]
        self.assertIn("google-mcp", routing.capabilities_of("codex-terra", terra, conns))
        self.assertNotIn("google-mcp", routing.capabilities_of("codex-luna", luna, conns))
        self.assertTrue(gen.seat_has_capability("codex-terra", "google-mcp", provs, conns))
        self.assertFalse(gen.seat_has_capability("codex-luna", "google-mcp", provs, conns))
        self.assertIn("dfs-mcp", routing.capabilities_of("codex-terra", terra, conns))

    def test_github_class_code_stays_coarse_not_derived(self):
        """Class exception is catalog-only: github.class=code must not strip coarse `code`."""
        conns = json.loads((CONFIG / "connectors.json").read_text())
        self.assertEqual(conns["mcp_connectors"]["github"]["class"], "code")
        derived = routing.connector_derived_labels(conns)
        self.assertNotIn("code", derived)
        grok = live_providers()["providers"]["grok-build"]
        self.assertIn("code", routing.capabilities_of("grok-build", grok, conns))


class ConnectorCoarseCollisionTests(unittest.TestCase):
    """IDs and aliases stay connector-derived even when they equal a coarse word."""

    def _conns(self):
        return json.loads((CONFIG / "connectors.json").read_text())

    def _provs(self):
        return live_providers()

    def _assert_doctor_collision(self, conns, provs, needle):
        doc.ERRORS.clear()
        doc.check_connector_lifecycle(conns, provs)
        blob = "\n".join(doc.ERRORS)
        self.assertTrue(
            any("collides with coarse capability vocabulary" in e and needle in e for e in doc.ERRORS),
            blob,
        )

    def _assert_no_coarse_browser(self, conns, provs):
        review_d = provs["providers"]["grok-bot-review-d"]
        heat = provs["providers"]["grok-bot-heat-map"]
        self.assertNotIn("browser", review_d["capabilities"])
        self.assertNotIn("browser", heat["capabilities"])
        self.assertNotIn("browser", routing.capabilities_of("grok-bot-review-d", review_d, conns))
        self.assertNotIn("browser", routing.capabilities_of("grok-bot-heat-map", heat, conns))
        self.assertFalse(gen.seat_has_capability("grok-bot-review-d", "browser", provs, conns))
        self.assertFalse(gen.seat_has_capability("grok-bot-heat-map", "browser", provs, conns))
        luna = provs["providers"]["codex-luna"]
        self.assertNotIn("browser", routing.capabilities_of("codex-luna", luna, conns))
        self.assertFalse(gen.seat_has_capability("codex-luna", "browser", provs, conns))

    def test_primed_alias_browser_does_not_grant_coarse_and_doctor_errors(self):
        """Exact regression: primed connector alias `browser` cannot leak from coarse browser."""
        conns = self._conns()
        provs = self._provs()
        conns["mcp_connectors"]["mb-bundled-example"]["alias"] = "browser"
        self.assertEqual(conns["mcp_connectors"]["mb-bundled-example"]["status"], "primed")
        derived = routing.connector_derived_labels(conns)
        self.assertIn("browser", derived)
        self._assert_no_coarse_browser(conns, provs)
        grok = provs["providers"]["grok-build"]
        self.assertNotIn("browser", routing.capabilities_of("grok-build", grok, conns))
        self.assertFalse(gen.seat_has_capability("grok-build", "browser", provs, conns))
        self._assert_doctor_collision(conns, provs, "browser")

    def test_primed_alias_browser_skill_gate_fails(self):
        conns = self._conns()
        provs = self._provs()
        conns["mcp_connectors"]["mb-bundled-example"]["alias"] = "browser"
        grok = provs["providers"]["grok-build"]
        grok["capabilities"] = list(grok["capabilities"]) + ["browser"]
        self.assertFalse(gen.seat_has_capability("grok-build", "browser", provs, conns))
        skills = json.loads((CONFIG / "skills.json").read_text())
        skills["skills"]["magnet-baron-skills:shopify-theme"]["required_capability"] = "browser"
        roles = live_roles()
        orig = gen.mborch.load_config

        def fake(name, required=True):
            if name == "connectors.json":
                return conns
            if name == "skills.json":
                return skills
            return orig(name, required=required)

        gen.mborch.load_config = fake
        try:
            with self.assertRaisesRegex(ValueError, r"lacks capability 'browser'"):
                dump_and_load(roles=roles, providers=provs)
        finally:
            gen.mborch.load_config = orig

    def test_primed_id_browser_does_not_grant_coarse_and_doctor_errors(self):
        conns = self._conns()
        provs = self._provs()
        conns["mcp_connectors"]["browser"] = {
            "status": "primed",
            "available_on": ["grok-build"],
            "mutating_tools": [],
            "class": "bundled-sample",
        }
        derived = routing.connector_derived_labels(conns)
        self.assertIn("browser", derived)
        self._assert_no_coarse_browser(conns, provs)
        self._assert_doctor_collision(conns, provs, "browser")

    def test_active_alias_browser_does_not_grant_coarse_to_unassigned_seats(self):
        conns = self._conns()
        provs = self._provs()
        conns["mcp_connectors"]["github"]["alias"] = "browser"
        self.assertEqual(conns["mcp_connectors"]["github"]["status"], "active")
        derived = routing.connector_derived_labels(conns)
        self.assertIn("browser", derived)
        self._assert_no_coarse_browser(conns, provs)
        grok = provs["providers"]["grok-build"]
        self.assertIn("browser", routing.capabilities_of("grok-build", grok, conns))
        self.assertTrue(gen.seat_has_capability("grok-build", "browser", provs, conns))
        self._assert_doctor_collision(conns, provs, "browser")

    def test_active_unobserved_id_browser_grants_no_seat(self):
        conns = self._conns()
        provs = self._provs()
        conns["mcp_connectors"]["browser"] = {
            "status": "active",
            "available_on": ["grok-build"],
            "mutating_tools": [],
            "class": "bundled-sample",
        }
        derived = routing.connector_derived_labels(conns)
        self.assertIn("browser", derived)
        self._assert_no_coarse_browser(conns, provs)
        grok = provs["providers"]["grok-build"]
        self.assertNotIn("browser", routing.capabilities_of("grok-build", grok, conns))
        self.assertFalse(gen.seat_has_capability("grok-build", "browser", provs, conns))
        self._assert_doctor_collision(conns, provs, "browser")

    def test_class_browser_stays_coarse_id_alias_do_not(self):
        conns = self._conns()
        conns["mcp_connectors"]["mb-bundled-example"]["class"] = "browser"
        derived = routing.connector_derived_labels(conns)
        self.assertNotIn("browser", derived)
        grok_bot = live_providers()["providers"]["grok-bot-review-d"]
        self.assertNotIn(
            "browser",
            routing.capabilities_of("grok-bot-review-d", grok_bot, conns),
        )
        conns["mcp_connectors"]["mb-bundled-example"]["alias"] = "browser"
        derived = routing.connector_derived_labels(conns)
        self.assertIn("browser", derived)
        self.assertNotIn(
            "browser",
            routing.capabilities_of("grok-bot-review-d", grok_bot, conns),
        )

    def test_id_and_alias_collision_matrix_active_and_primed(self):
        cases = [
            ("primed_alias", "primed", "alias"),
            ("active_alias", "active", "alias"),
            ("primed_id", "primed", "id"),
            ("active_id", "active", "id"),
        ]
        for name, status, kind in cases:
            with self.subTest(name=name):
                conns = self._conns()
                provs = self._provs()
                if kind == "alias":
                    conns["mcp_connectors"]["mb-bundled-example"]["status"] = status
                    if status == "active":
                        conns["mcp_connectors"]["mb-bundled-example"].pop("server", None)
                    conns["mcp_connectors"]["mb-bundled-example"]["alias"] = "browser"
                else:
                    conns["mcp_connectors"]["browser"] = {
                        "status": status,
                        "available_on": ["grok-build"],
                        "mutating_tools": [],
                        "class": "bundled-sample",
                    }
                self.assertIn("browser", routing.connector_derived_labels(conns), name)
                review_d = provs["providers"]["grok-bot-review-d"]
                self.assertNotIn(
                    "browser",
                    routing.capabilities_of("grok-bot-review-d", review_d, conns),
                    name,
                )
                self._assert_doctor_collision(conns, provs, "browser")


if __name__ == "__main__":
    unittest.main()
