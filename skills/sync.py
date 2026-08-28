#!/usr/bin/env python3
"""Maintain low-context routers over private, pinned skill libraries."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REGISTRY = HERE / "registry.json"


def skill_spec(source: dict, item: str | dict) -> dict[str, str]:
    if isinstance(item, str):
        name = directory = item
        prefix = source.get("path_prefix", "")
        path = f"{prefix}/{item}" if prefix else item
    elif isinstance(item, dict):
        name = item.get("name", "")
        directory = item.get("directory", name)
        path = item.get("path", "")
    else:
        raise ValueError("skill entries must be names or objects")
    if not name or not directory or not path:
        raise ValueError("skill entries require name, directory, and source path")
    if "/" in directory or directory in {".", ".."}:
        raise ValueError(f"invalid private skill directory: {directory}")
    return {"name": name, "directory": directory, "path": path}


def leaf_catalog(data: dict) -> list[dict[str, str]]:
    leaves: list[dict[str, str]] = []
    for bundle_name, bundle in data["bundles"].items():
        root = str(Path(bundle["library_root"]).expanduser())
        for source_name, source in bundle["sources"].items():
            for item in source["skills"]:
                leaf = skill_spec(source, item)
                leaf.update(bundle=bundle_name, source=source_name, root=root)
                leaves.append(leaf)
    return leaves


def load_registry(path: Path = REGISTRY) -> dict:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 3:
        raise ValueError("skills registry must use schema_version 3")
    for key in ("legacy_install_root", "universal_root"):
        if not data.get(key):
            raise ValueError(f"skills registry requires {key}")
    bundles = data.get("bundles")
    if not isinstance(bundles, dict) or not bundles:
        raise ValueError("skills registry requires bundles")

    router_names: list[str] = []
    for bundle_name, bundle in bundles.items():
        if not bundle.get("library_root"):
            raise ValueError(f"{bundle_name}: library_root is required")
        router = bundle.get("router")
        if not isinstance(router, dict) or not router.get("name") or not router.get("path"):
            raise ValueError(f"{bundle_name}: named router path is required")
        router_names.append(router["name"])
        sources, routes = bundle.get("sources"), bundle.get("routes")
        if not isinstance(sources, dict) or not sources:
            raise ValueError(f"{bundle_name}: sources are required")
        if not isinstance(routes, dict) or not routes:
            raise ValueError(f"{bundle_name}: routes are required")
        bundle_leaves: list[str] = []
        for source_name, source in sources.items():
            if not source.get("repository") or not source.get("revision"):
                raise ValueError(f"{bundle_name}/{source_name}: repository and revision are required")
            skills = source.get("skills")
            if not isinstance(skills, list) or not skills:
                raise ValueError(f"{bundle_name}/{source_name}: skills must be non-empty")
            bundle_leaves.extend(skill_spec(source, item)["name"] for item in skills)
        if len(bundle_leaves) != len(set(bundle_leaves)):
            raise ValueError(f"{bundle_name}: leaf skill names must be unique")
        allowed = set(bundle_leaves) | {router["name"]}
        for route_name, route in routes.items():
            activation, skills = route.get("activation"), route.get("skills")
            if activation not in {"disabled", "progressive", "direct"}:
                raise ValueError(f"{bundle_name}/{route_name}: invalid activation")
            if not isinstance(skills, list) or len(skills) != len(set(skills)):
                raise ValueError(f"{bundle_name}/{route_name}: skills must be a unique list")
            unknown = set(skills) - allowed
            if unknown:
                raise ValueError(f"{bundle_name}/{route_name}: unknown skills: {sorted(unknown)}")
            if activation == "disabled" and skills:
                raise ValueError(f"{bundle_name}/{route_name}: disabled routes cannot enable skills")
            if activation == "progressive" and set(skills) - {router["name"]}:
                raise ValueError(f"{bundle_name}/{route_name}: progressive routes expose only the router")
    if len(router_names) != len(set(router_names)):
        raise ValueError("router names must be unique")
    names = [leaf["name"] for leaf in leaf_catalog(data)]
    if len(names) != len(set(names)):
        raise ValueError("a leaf skill name may belong to only one bundle")
    return data


def q(value: str) -> str:
    return json.dumps(value)


def skill_entries(paths: list[Path], enabled: bool) -> str:
    blocks = []
    for path in paths:
        blocks.append("[[skills.config]]\n" f"path = {q(str(path))}\n" f"enabled = {'true' if enabled else 'false'}")
    return "\n\n".join(blocks) + "\n"


def agent_toml(name: str, description: str, instructions: str, skill_paths: list[Path], read_only: bool) -> str:
    return "\n".join([
        f"name = {q(name)}", f"description = {q(description)}",
        f"sandbox_mode = {q('read-only' if read_only else 'workspace-write')}",
        f"developer_instructions = {q(instructions)}", "",
        skill_entries(skill_paths, True).rstrip(), "",
    ])


def bundle_leaf(data: dict, bundle_name: str, leaf_name: str) -> Path:
    for leaf in leaf_catalog(data):
        if leaf["bundle"] == bundle_name and leaf["name"] == leaf_name:
            return Path(leaf["root"]) / leaf["directory"] / "SKILL.md"
    raise ValueError(f"missing {bundle_name} leaf: {leaf_name}")


def expected_files(data: dict) -> dict[Path, str]:
    mobile = data["bundles"]["mobile"]
    accessibility = mobile["routes"]["mobile-accessibility-reviewer"]["skills"]
    accessibility_paths = [bundle_leaf(data, "mobile", name) for name in accessibility]
    router_path = REPO / mobile["router"]["path"] / "SKILL.md"
    return {
        REPO / ".codex/agents/mb-mobile-accessibility-reviewer.toml": agent_toml(
            "mb-mobile-accessibility-reviewer",
            "Read-only iOS accessibility reviewer for UIKit, SwiftUI, VoiceOver, Dynamic Type, and assistive-technology work.",
            "Review only the assigned iOS accessibility scope. Load ios-accessibility, inspect evidence, and return ship, fix-list, or blocked. Do not edit files or treat automated checks as a substitute for manual assistive-technology testing.",
            accessibility_paths, True,
        ),
        REPO / ".codex/agents/mb-mobile-tooling.toml": (
            'name = "mb-mobile-tooling"\n'
            'description = "Dart and Flutter implementation role with the mobile router and local Dart MCP tooling."\n'
            'sandbox_mode = "workspace-write"\n'
            'developer_instructions = "Work only within the assigned mobile scope. Invoke mobile-dev-router, load no more leaf playbooks than it selects, use Dart MCP only when live analysis, app, LSP, or widget evidence improves the result, and return files, tests, and remaining manual validation."\n\n'
            '[mcp_servers.dart-mcp-server]\ncommand = "dart"\nargs = ["mcp-server"]\n'
            'startup_timeout_sec = 30\ntool_timeout_sec = 120\n\n[[skills.config]]\n'
            f'path = {q(str(router_path))}\nenabled = true\n'
        ),
    }


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
    os.replace(tmp, path)


def migrate_libraries(data: dict, legacy_root: Path) -> None:
    moves: list[tuple[Path, Path]] = []
    for leaf in leaf_catalog(data):
        root = Path(leaf["root"])
        root.mkdir(parents=True, exist_ok=True)
        source, destination = legacy_root / leaf["directory"], root / leaf["directory"]
        if (destination / "SKILL.md").is_file():
            if source.exists() or source.is_symlink():
                raise SystemExit(f"both legacy and private copies exist for {leaf['name']}")
        elif (source / "SKILL.md").is_file():
            moves.append((source, destination))
    for source, destination in moves:
        os.replace(source, destination)


def remove_leaf_exposure(data: dict, legacy_root: Path, universal_root: Path, check: bool) -> list[str]:
    problems: list[str] = []
    repo_skill_root = REPO / ".agents/skills"
    for leaf in leaf_catalog(data):
        private = Path(leaf["root"]) / leaf["directory"]
        candidate_names = {leaf["name"], leaf["directory"]}
        expected_targets = {str(legacy_root / name) for name in candidate_names} | {str(private)}
        for name in candidate_names:
            for link in (repo_skill_root / name, universal_root / name, legacy_root / name):
                if not (link.exists() or link.is_symlink()):
                    continue
                if not link.is_symlink() or os.readlink(link) not in expected_targets:
                    problems.append(f"refusing to remove unexpected leaf exposure: {link}")
                elif check:
                    problems.append(f"leaf skill is still exposed: {link}")
                else:
                    link.unlink()
    return problems


def ensure_router_links(data: dict, universal_root: Path, check: bool) -> list[str]:
    problems: list[str] = []
    for bundle_name, bundle in data["bundles"].items():
        router = bundle["router"]
        target, link = REPO / router["path"], universal_root / router["name"]
        if not (target / "SKILL.md").is_file():
            problems.append(f"{bundle_name}: missing router skill: {target}")
        elif link.is_symlink() and link.resolve() == target.resolve():
            continue
        elif link.exists() or link.is_symlink():
            problems.append(f"{bundle_name}: collision or wrong router target: {link}")
        elif check:
            problems.append(f"{bundle_name}: missing router link: {link}")
        else:
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target, target_is_directory=True)
    return problems


def remove_legacy_config(check: bool) -> list[str]:
    path = REPO / ".codex/config.toml"
    marker = "# Generated by skills/sync.py. Dispatch and ordinary agents do not load mobile skills."
    if not path.is_file() or not path.read_text().startswith(marker):
        return []
    if check:
        return [f"legacy generated Codex skill config remains: {path}"]
    path.unlink()
    return []


def sync(check: bool = False, migrate: bool = False) -> None:
    data = load_registry()
    legacy_root = Path(data["legacy_install_root"]).expanduser()
    universal_root = Path(data["universal_root"]).expanduser()
    if migrate:
        if check:
            raise SystemExit("--check and --migrate-library are mutually exclusive")
        migrate_libraries(data, legacy_root)

    missing = []
    for leaf in leaf_catalog(data):
        path = Path(leaf["root"]) / leaf["directory"] / "SKILL.md"
        if not path.is_file():
            missing.append(path)
    if missing:
        raise SystemExit("\n".join(["missing private leaf skills:", *[str(path) for path in missing]]))

    problems = remove_leaf_exposure(data, legacy_root, universal_root, check)
    problems.extend(ensure_router_links(data, universal_root, check))
    problems.extend(remove_legacy_config(check))
    for path, text in expected_files(data).items():
        if path.exists() and path.read_text() == text:
            continue
        if check:
            problems.append(f"missing or stale generated file: {path}")
        else:
            write_atomic(path, text)
    if problems:
        raise SystemExit("\n".join(problems))
    action = "verified" if check else "migrated and generated" if migrate else "linked and generated"
    print(f"{action} {len(data['bundles'])} routers over {len(leaf_catalog(data))} private leaf skills")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--migrate-library", action="store_true")
    args = parser.parse_args()
    sync(check=args.check, migrate=args.migrate_library)


if __name__ == "__main__":
    main()
