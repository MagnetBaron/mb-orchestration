#!/usr/bin/env python3
"""Maintain a low-context mobile skill router and private leaf library."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REGISTRY = HERE / "registry.json"


def load_registry(path: Path = REGISTRY) -> dict:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 2:
        raise ValueError("skills registry must use schema_version 2")

    for key in ("library_root", "legacy_install_root", "universal_root"):
        if not data.get(key):
            raise ValueError(f"skills registry requires {key}")

    router = data.get("router")
    if not isinstance(router, dict) or not router.get("name") or not router.get("path"):
        raise ValueError("skills registry requires a named router path")

    sources = data.get("sources")
    routes = data.get("routes")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("skills registry requires sources")
    if not isinstance(routes, dict) or not routes:
        raise ValueError("skills registry requires routes")

    leaves: list[str] = []
    for source_name, source in sources.items():
        if not source.get("repository") or not source.get("revision"):
            raise ValueError(f"{source_name}: repository and revision are required")
        skills = source.get("skills")
        if not isinstance(skills, list) or not skills or len(skills) != len(set(skills)):
            raise ValueError(f"{source_name}: skills must be a non-empty unique list")
        leaves.extend(skills)
    if len(leaves) != len(set(leaves)):
        raise ValueError("a leaf skill may belong to only one source")

    allowed = set(leaves) | {router["name"]}
    for route_name, route in routes.items():
        if route.get("activation") not in {"disabled", "progressive", "direct"}:
            raise ValueError(f"{route_name}: invalid activation")
        skills = route.get("skills")
        if not isinstance(skills, list) or len(skills) != len(set(skills)):
            raise ValueError(f"{route_name}: skills must be a unique list")
        unknown = set(skills) - allowed
        if unknown:
            raise ValueError(f"{route_name}: unknown skills: {sorted(unknown)}")
        if route["activation"] == "disabled" and skills:
            raise ValueError(f"{route_name}: disabled routes cannot enable skills")
    return data


def leaf_catalog(data: dict) -> list[str]:
    return [skill for source in data["sources"].values() for skill in source["skills"]]


def q(value: str) -> str:
    return json.dumps(value)


def skill_entries(skills: list[str], root: Path, enabled: bool) -> str:
    blocks = []
    for name in skills:
        blocks.append(
            "[[skills.config]]\n"
            f"path = {q(str(root / name / 'SKILL.md'))}\n"
            f"enabled = {'true' if enabled else 'false'}"
        )
    return "\n\n".join(blocks) + "\n"


def agent_toml(
    name: str,
    description: str,
    instructions: str,
    skills: list[str],
    library_root: Path,
    read_only: bool,
) -> str:
    lines = [
        f"name = {q(name)}",
        f"description = {q(description)}",
        f"sandbox_mode = {q('read-only' if read_only else 'workspace-write')}",
        f"developer_instructions = {q(instructions)}",
        "",
        skill_entries(skills, library_root, True).rstrip(),
        "",
    ]
    return "\n".join(lines)


def expected_files(data: dict, library_root: Path) -> dict[Path, str]:
    accessibility = data["routes"]["mobile-accessibility-reviewer"]["skills"]
    return {
        REPO / ".codex/agents/mb-mobile-accessibility-reviewer.toml": agent_toml(
            "mb-mobile-accessibility-reviewer",
            "Read-only iOS accessibility reviewer for UIKit, SwiftUI, VoiceOver, Dynamic Type, and assistive-technology work.",
            "Review only the assigned iOS accessibility scope. Load ios-accessibility, inspect evidence, and return ship, fix-list, or blocked. Do not edit files or treat automated checks as a substitute for manual assistive-technology testing.",
            accessibility,
            library_root,
            True,
        ),
        REPO / ".codex/agents/mb-mobile-tooling.toml": (
            'name = "mb-mobile-tooling"\n'
            'description = "Dart and Flutter implementation role with the mobile router and local Dart MCP tooling."\n'
            'sandbox_mode = "workspace-write"\n'
            'developer_instructions = "Work only within the assigned mobile scope. Invoke mobile-dev-router, load no more leaf playbooks than it selects, use Dart MCP only when live analysis, app, LSP, or widget evidence improves the result, and return files, tests, and remaining manual validation."\n\n'
            '[mcp_servers.dart-mcp-server]\n'
            'command = "dart"\n'
            'args = ["mcp-server"]\n'
            'startup_timeout_sec = 30\n'
            'tool_timeout_sec = 120\n\n'
            '[[skills.config]]\n'
            f'path = {q(str(REPO / data["router"]["path"] / "SKILL.md"))}\n'
            'enabled = true\n'
        ),
    }


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
    os.replace(tmp, path)


def migrate_library(data: dict, library_root: Path, legacy_root: Path) -> None:
    library_root.mkdir(parents=True, exist_ok=True)
    moves: list[tuple[Path, Path]] = []
    for name in leaf_catalog(data):
        source = legacy_root / name
        destination = library_root / name
        if (destination / "SKILL.md").is_file():
            if source.exists() or source.is_symlink():
                raise SystemExit(f"both legacy and private copies exist for {name}")
            continue
        if not (source / "SKILL.md").is_file():
            raise SystemExit(f"cannot migrate missing legacy skill: {source}")
        moves.append((source, destination))
    for source, destination in moves:
        os.replace(source, destination)


def remove_leaf_exposure(data: dict, legacy_root: Path, universal_root: Path, check: bool) -> list[str]:
    problems: list[str] = []
    repo_skill_root = REPO / ".agents/skills"
    for name in leaf_catalog(data):
        expected = {
            str(legacy_root / name),
            str(universal_root / name),
        }
        for link in (repo_skill_root / name, universal_root / name):
            if not (link.exists() or link.is_symlink()):
                continue
            if not link.is_symlink() or os.readlink(link) not in expected:
                problems.append(f"refusing to remove unexpected leaf exposure: {link}")
            elif check:
                problems.append(f"leaf skill is still globally exposed: {link}")
            else:
                link.unlink()
    return problems


def ensure_router_link(data: dict, universal_root: Path, check: bool) -> list[str]:
    router = data["router"]
    target = REPO / router["path"]
    link = universal_root / router["name"]
    if not (target / "SKILL.md").is_file():
        return [f"missing router skill: {target}"]
    if link.is_symlink() and link.resolve() == target.resolve():
        return []
    if link.exists() or link.is_symlink():
        return [f"collision or wrong router target: {link}"]
    if check:
        return [f"missing router link: {link}"]
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target, target_is_directory=True)
    return []


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
    library_root = Path(data["library_root"]).expanduser()
    legacy_root = Path(data["legacy_install_root"]).expanduser()
    universal_root = Path(data["universal_root"]).expanduser()

    if migrate:
        if check:
            raise SystemExit("--check and --migrate-library are mutually exclusive")
        migrate_library(data, library_root, legacy_root)

    missing = [
        library_root / name / "SKILL.md"
        for name in leaf_catalog(data)
        if not (library_root / name / "SKILL.md").is_file()
    ]
    if missing:
        hint = "run skills/sync.py --migrate-library first" if not migrate else "migration did not produce the private library"
        raise SystemExit("\n".join([hint, *[f"missing private leaf skill: {path}" for path in missing]]))

    problems = remove_leaf_exposure(data, legacy_root, universal_root, check)
    problems.extend(ensure_router_link(data, universal_root, check))
    problems.extend(remove_legacy_config(check))

    for path, text in expected_files(data, library_root).items():
        if path.exists() and path.read_text() == text:
            continue
        if check:
            problems.append(f"missing or stale generated file: {path}")
        else:
            write_atomic(path, text)

    if problems:
        raise SystemExit("\n".join(problems))
    action = "verified" if check else "migrated and generated" if migrate else "linked and generated"
    print(f"{action} 1 router over {len(leaf_catalog(data))} private leaf skills")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--migrate-library", action="store_true")
    args = parser.parse_args()
    sync(check=args.check, migrate=args.migrate_library)


if __name__ == "__main__":
    main()
