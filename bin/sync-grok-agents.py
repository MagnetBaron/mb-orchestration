#!/usr/bin/env python3
"""Atomically install/check the three standing Grok CLI profiles.

This narrow distributor intentionally does not require unrelated live MCP inventory. The full
role generator still validates every role; this path validates only the standing profiles it owns.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import stat
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location("generate_roles_for_sync", HERE / "generate-roles.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

ROLE_NAMES = ("review-d", "heat-map", "marketplace-intelligence")
STANDING_GROK_SEATS = {
    "review-d": "grok-bot-review-d",
    "heat-map": "grok-bot-heat-map",
    "marketplace-intelligence": "grok-bot-marketplace-intelligence",
}
STANDING_GROK_TOOLS = {
    "review-d": ("Read", "Grep", "Glob"),
    "heat-map": ("Read", "Grep", "Glob"),
    "marketplace-intelligence": ("Read", "Grep", "Glob"),
}
MAX_PROFILE_BYTES = 256 * 1024
MAX_CANONICAL_CONFIG_BYTES = 2 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
EXPECTED_PROFILE_MODE = 0o644
DEFAULT_TRUSTED_ORIGIN = "https://github.com/MagnetBaron/mb-orchestration"


def _file_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_stable_regular_bytes(
    path: Path,
    *,
    max_bytes: int,
    label: str,
    required_uid: int | None = None,
    required_mode: int | None = None,
) -> bytes:
    """Bounded, stable, no-follow read with a final path-identity checkpoint."""
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError("O_NOFOLLOW is unavailable")
    try:
        fd = os.open(
            path,
            os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0),
        )
    except OSError as exc:
        raise ValueError(f"{label} cannot open as a regular non-symlink file: {exc}") from exc
    chunks = []
    total = 0
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"{label} is not a regular file")
        if required_uid is not None and before.st_uid != required_uid:
            raise ValueError(f"{label} is not owned by the current uid")
        if required_mode is not None and stat.S_IMODE(before.st_mode) != required_mode:
            raise ValueError(f"{label} mode must be exact {required_mode:04o}")
        while True:
            chunk = os.read(fd, min(READ_CHUNK_BYTES, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"{label} exceeds {max_bytes} bytes")
            chunks.append(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    identity = _file_identity(before)
    if _file_identity(after) != identity:
        raise ValueError(f"{label} changed during its bounded read")
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise ValueError(f"{label} changed after its bounded read: {exc}") from exc
    if not stat.S_ISREG(current.st_mode) or _file_identity(current) != identity:
        raise ValueError(f"{label} path changed after its bounded read")
    return b"".join(chunks)


def read_installed_profile(path: Path) -> str:
    """Bounded, stable, no-follow read for the installed-state drift gate."""
    try:
        return _read_stable_regular_bytes(
            path,
            max_bytes=MAX_PROFILE_BYTES,
            label="installed profile",
            required_uid=os.getuid(),
            required_mode=EXPECTED_PROFILE_MODE,
        ).decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("installed profile is not valid UTF-8") from exc


def _load_canonical_json(filename: str) -> dict:
    path = ROOT / "config" / filename
    try:
        raw = _read_stable_regular_bytes(
            path,
            max_bytes=MAX_CANONICAL_CONFIG_BYTES,
            label=f"canonical {filename}",
        )
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"cannot safely load canonical {filename}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"canonical {filename} must contain one JSON object")
    return data


def grok_tools_from_profile(text: str) -> tuple[str, ...] | None:
    if not isinstance(text, str) or not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    tools = None
    for line in text[4:end].splitlines():
        if line.startswith("tools:"):
            if tools is not None:
                return None
            names = tuple(part.strip() for part in line[6:].split(",") if part.strip())
            if not names:
                return None
            tools = names
    return tools


def standing_tools_problem(role_name: str, tools) -> str | None:
    allowed = STANDING_GROK_TOOLS.get(role_name)
    if allowed is None:
        return f"{role_name}: unknown standing Grok role"
    if tools is None:
        return f"{role_name}: standing Grok profile is missing an exact tools allowlist"
    if tuple(tools) != allowed:
        return f"{role_name}: standing Grok tools must be exact {list(allowed)!r}"
    return None


def standing_profile_problem(role_name: str, text: str, description: str) -> str | None:
    """Require the exact no-extension frontmatter owned by the standing launcher."""
    allowed = STANDING_GROK_TOOLS.get(role_name)
    if allowed is None:
        return f"{role_name}: unknown standing Grok role"
    if not isinstance(text, str) or not isinstance(description, str):
        return f"{role_name}: standing Grok profile metadata is invalid"
    expected_header = "\n".join((
        "---",
        f"name: mb-{role_name}",
        f"description: {json.dumps(description)}",
        "tools: " + ", ".join(allowed),
        "---",
        "",
    ))
    if not text.startswith(expected_header):
        return (
            f"{role_name}: standing Grok frontmatter must be the exact name, "
            "description, and tools allowlist with no skills, plugins, MCP, or extra fields"
        )
    return None


def expected() -> dict[str, str]:
    # Distribution is tied to the authoritative checkout, never an ambient
    # MB_CONFIG_DIR overlay. Per-user overlays may change routing, not the
    # canonical standing-role policy bytes installed on the machine.
    roles = _load_canonical_json("roles.json")["roles"]
    providers = _load_canonical_json("providers.json")["providers"]
    out = {}
    for name in ROLE_NAMES:
        role = roles.get(name)
        if not isinstance(role, dict) or not role.get("read_only"):
            raise ValueError(f"{name}: missing read-only role definition")
        expected_seat = STANDING_GROK_SEATS[name]
        if role.get("seat") != expected_seat:
            raise ValueError(f"{name}: seat must be exact {expected_seat!r}")
        seat = providers.get(role.get("seat"))
        if not isinstance(seat, dict) or seat.get("enabled", True) is not True:
            raise ValueError(f"{name}: standing Grok provider must be enabled with exact true")
        if seat.get("kind") != "cli" or seat.get("model") != "grok-4.6":
            raise ValueError(f"{name}: seat must be a Grok CLI provider pinned to grok-4.6")
        host_override = role.get("grok")
        if host_override is not None and (
            not isinstance(host_override, dict) or set(host_override) != {"tools"}
        ):
            raise ValueError(
                f"{name}: standing Grok host override may contain exact tools only; "
                "skills, plugins, MCP, and extra fields are forbidden"
            )
        declared = (role.get("tools") or {}).get("grok")
        if host_override is not None:
            declared = host_override.get("tools")
        problem = standing_tools_problem(name, declared)
        if problem:
            raise ValueError(problem)
        body = gen.grok(role, name)
        profile_problem = standing_profile_problem(name, body, role.get("description"))
        if profile_problem:
            raise ValueError(profile_problem)
        rendered = grok_tools_from_profile(body)
        problem = standing_tools_problem(name, rendered)
        if problem:
            raise ValueError(problem)
        out[f"mb-{name}.md"] = body
    return out


def _normalize_github_origin(value: str) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    prefixes = (
        ("https://github.com/", "github.com/"),
        ("git@github.com:", "github.com/"),
        ("ssh://git@github.com/", "github.com/"),
    )
    for prefix, replacement in prefixes:
        if value.startswith(prefix):
            suffix = value[len(prefix):]
            return replacement + suffix if suffix and "/" in suffix else None
    if value.startswith("github.com/") and value.count("/") >= 2:
        return value
    return None


def _git_origin(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            start_new_session=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or result.stderr or len(result.stdout.encode("utf-8")) > 4096:
        return None
    return result.stdout.strip()


def canonical_checkout_problem() -> str | None:
    """Share sync-commands.sh's canonical-checkout and trusted-origin boundary."""
    expected = Path(
        os.environ.get("ORCA_REPO", str(Path.home() / "git" / "mb-orchestration"))
    ).expanduser()
    try:
        actual_root = ROOT.resolve(strict=True)
        expected_root = expected.resolve(strict=True)
    except OSError as exc:
        return f"canonical checkout cannot be resolved: {exc}"
    if actual_root != expected_root:
        return f"refusing non-canonical checkout: {actual_root} (expected {expected_root})"
    origin_url = _git_origin(actual_root)
    origin = _normalize_github_origin(origin_url or "")
    trusted = _normalize_github_origin(
        os.environ.get("ORCA_TRUSTED_ORIGIN", DEFAULT_TRUSTED_ORIGIN)
    )
    if origin is None or trusted is None or origin != trusted:
        return f"refusing untrusted origin: {origin_url or 'missing'}"
    return None


def _open_owned_directory(path, *, dir_fd: int | None = None, label: str) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory is None:
        raise ValueError("O_NOFOLLOW/O_DIRECTORY are unavailable")
    fd = os.open(
        path,
        os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0),
        dir_fd=dir_fd,
    )
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"{label} is not a directory")
        if info.st_uid != os.getuid():
            raise ValueError(f"{label} is not owned by the current uid")
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_target_agents(target_home: Path, *, create: bool) -> tuple[int, int, int]:
    home_fd = _open_owned_directory(target_home, label="target home")
    grok_fd = agents_fd = None
    try:
        if create:
            try:
                os.mkdir(".grok", 0o700, dir_fd=home_fd)
            except FileExistsError:
                pass
        grok_fd = _open_owned_directory(".grok", dir_fd=home_fd, label="target .grok")
        if create:
            try:
                os.mkdir("agents", 0o700, dir_fd=grok_fd)
            except FileExistsError:
                pass
        agents_fd = _open_owned_directory(
            "agents", dir_fd=grok_fd, label="target .grok/agents"
        )
        return home_fd, grok_fd, agents_fd
    except Exception:
        if agents_fd is not None:
            os.close(agents_fd)
        if grok_fd is not None:
            os.close(grok_fd)
        os.close(home_fd)
        raise


def _directory_binding_problem(
    target_home: Path, home_fd: int, grok_fd: int, agents_fd: int
) -> str | None:
    """Confirm names still identify the exact directory handles used for I/O."""
    try:
        current_home = os.lstat(target_home)
        current_grok = os.stat(".grok", dir_fd=home_fd, follow_symlinks=False)
        current_agents = os.stat("agents", dir_fd=grok_fd, follow_symlinks=False)
    except OSError as exc:
        return f"target directory binding changed: {exc}"
    pairs = (
        ("target home", current_home, os.fstat(home_fd)),
        ("target .grok", current_grok, os.fstat(grok_fd)),
        ("target .grok/agents", current_agents, os.fstat(agents_fd)),
    )
    for label, current, bound in pairs:
        if not stat.S_ISDIR(current.st_mode) or (
            current.st_dev, current.st_ino, current.st_uid
        ) != (bound.st_dev, bound.st_ino, bound.st_uid):
            return f"{label} changed during profile distribution"
    return None


def _read_installed_profile_at(agents_fd: int, filename: str) -> str:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError("O_NOFOLLOW is unavailable")
    fd = os.open(
        filename,
        os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=agents_fd,
    )
    chunks = []
    total = 0
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("installed profile is not a regular file")
        if before.st_uid != os.getuid():
            raise ValueError("installed profile is not owned by the current uid")
        if stat.S_IMODE(before.st_mode) != EXPECTED_PROFILE_MODE:
            raise ValueError(f"installed profile mode must be exact {EXPECTED_PROFILE_MODE:04o}")
        while True:
            chunk = os.read(fd, min(READ_CHUNK_BYTES, MAX_PROFILE_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_PROFILE_BYTES:
                raise ValueError(f"installed profile exceeds {MAX_PROFILE_BYTES} bytes")
            chunks.append(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if _file_identity(after) != _file_identity(before):
        raise ValueError("installed profile changed during its bounded read")
    current = os.stat(filename, dir_fd=agents_fd, follow_symlinks=False)
    if not stat.S_ISREG(current.st_mode) or _file_identity(current) != _file_identity(before):
        raise ValueError("installed profile name changed after its bounded read")
    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("installed profile is not valid UTF-8") from exc


def _write_atomic_at(agents_fd: int, filename: str, text: str) -> None:
    if not filename or filename in {".", ".."} or "/" in filename or "\x00" in filename:
        raise ValueError("profile filename must be one safe path component")
    payload = text.encode("utf-8")
    if len(payload) > MAX_PROFILE_BYTES:
        raise ValueError(f"generated profile exceeds {MAX_PROFILE_BYTES} bytes")
    tmp = None
    fd = None
    for _ in range(32):
        candidate = f".{filename}.{secrets.token_hex(16)}.tmp"
        try:
            fd = os.open(
                candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=agents_fd,
            )
            tmp = candidate
            break
        except FileExistsError:
            continue
    if fd is None or tmp is None:
        raise ValueError("cannot allocate an atomic profile staging file")
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write while staging profile")
            view = view[written:]
        os.fchmod(fd, EXPECTED_PROFILE_MODE)
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(tmp, filename, src_dir_fd=agents_fd, dst_dir_fd=agents_fd)
        tmp = None
        os.fsync(agents_fd)
    finally:
        if fd is not None:
            os.close(fd)
        if tmp is not None:
            try:
                os.unlink(tmp, dir_fd=agents_fd)
            except FileNotFoundError:
                pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-home", type=Path, default=Path.home())
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    target = args.target_home / ".grok" / "agents"
    provenance_problem = canonical_checkout_problem()
    if provenance_problem:
        print(f"ERROR   {provenance_problem}")
        return 2
    try:
        profiles = expected()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR   cannot generate Grok profiles: {exc}")
        return 2
    try:
        home_fd, grok_fd, agents_fd = _open_target_agents(
            args.target_home, create=not args.check
        )
    except FileNotFoundError:
        print(f"BROKEN  {target} (required owned non-symlink directory is missing)")
        return 1 if args.check else 2
    except (OSError, ValueError) as exc:
        print(f"ERROR   unsafe profile target {target}: {exc}")
        return 2
    try:
        binding_problem = _directory_binding_problem(
            args.target_home, home_fd, grok_fd, agents_fd
        )
        if binding_problem:
            print(f"ERROR   {binding_problem}")
            return 2
        if args.check:
            rc = 0
            statuses = []
            for filename, body in profiles.items():
                path = target / filename
                try:
                    installed = _read_installed_profile_at(agents_fd, filename)
                except (OSError, ValueError):
                    installed = None
                if installed == body:
                    statuses.append(
                        f"OK      {path} (exact 0644 snapshot at completed checkpoint)"
                    )
                else:
                    statuses.append(f"BROKEN  {path}")
                    rc = 1
        else:
            for filename, body in profiles.items():
                _write_atomic_at(agents_fd, filename, body)
            statuses = []
            for filename, body in profiles.items():
                installed = _read_installed_profile_at(agents_fd, filename)
                if installed != body:
                    raise ValueError(f"{filename}: atomic profile verification failed")
                statuses.append(
                    f"SYNCED  {target / filename} (exact 0644 snapshot at completed checkpoint)"
                )
            rc = 0
        binding_problem = _directory_binding_problem(
            args.target_home, home_fd, grok_fd, agents_fd
        )
        if binding_problem:
            print(f"ERROR   {binding_problem}")
            return 2
        for line in statuses:
            print(line)
        return rc
    except (OSError, ValueError) as exc:
        print(f"ERROR   profile distribution failed closed: {exc}")
        return 2
    finally:
        os.close(agents_fd)
        os.close(grok_fd)
        os.close(home_fd)


if __name__ == "__main__":
    raise SystemExit(main())
