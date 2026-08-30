#!/usr/bin/env python3
"""Validate and launch the three standing Grok roles through the real Grok CLI.

This is deliberately narrower than the general executor. It never uses Slack, never
constructs a shell string, and only renders recipes already pinned in seat-exec.json.
Normal execution fails closed unless the provider is wired and its catalog route is
live_verified. ``--smoke`` only proves CLI/profile/model selection; it does not prove
browser, Clarity, marketplace access, or a role result.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402
import integrations  # noqa: E402
import connectors as connector_packets  # noqa: E402
import handoff_policy  # noqa: E402

_SYNC_SPEC = importlib.util.spec_from_file_location(
    "grok_agent_sync_profiles", Path(__file__).resolve().parent / "sync-grok-agents.py"
)
sync_profiles = importlib.util.module_from_spec(_SYNC_SPEC)
_SYNC_SPEC.loader.exec_module(sync_profiles)

_REGISTRY_SPEC = importlib.util.spec_from_file_location(
    "grok_agent_model_registry", Path(__file__).resolve().parent / "model-registry.py"
)
model_registry = importlib.util.module_from_spec(_REGISTRY_SPEC)
_REGISTRY_SPEC.loader.exec_module(model_registry)

AGENTS = {
    "grok-bot-review-d": "mb-review-d",
    "grok-bot-heat-map": "mb-heat-map",
    "grok-bot-marketplace-intelligence": "mb-marketplace-intelligence",
}
REQUIRED_CAPABILITIES = {
    "grok-bot-review-d": ("browser", "pixels"),
    "grok-bot-heat-map": ("browser", "clarity-auth"),
    "grok-bot-marketplace-intelligence": ("deposited-evidence",),
}
# Only marketplace evidence currently has a concrete, code-owned path into the
# isolated CLI process. Browser/pixel and signed-in Clarity sources are not
# injected by this launcher, so registry/inventory attestations alone must never
# promote those role executions. Their transport-only smoke remains available.
EXECUTION_INPUT_BINDINGS = {
    "grok-bot-review-d": None,
    "grok-bot-heat-map": None,
    "grok-bot-marketplace-intelligence": "hash-bound-deposited-evidence",
}
SEATS = tuple(AGENTS)
SANDBOX_PROFILE_PREFIX = "mb-standing-"
SANDBOX_PROFILE_RE = re.compile(r"^mb-standing-[0-9a-f]{32}$")
EVIDENCE_STAGED_NAME = "evidence"
PROMPT_STAGED_NAME = "prompt.md"
STAGED_CWD_PLACEHOLDER = "<ephemeral-staging>"
STAGED_PROMPT_PLACEHOLDER = "<staged-prompt>"
STAGED_AGENT_PLACEHOLDER = "<staged-agent-profile>"
STAGED_SANDBOX_PLACEHOLDER = "<ephemeral-sandbox-profile>"
SMOKE_PROMPT = "CLI transport smoke only. Use no tools and return exactly: cli-agent-path-ok"
# Conservative cap for deposited CSV/JSON/text/image evidence. Parks before hashing/copy.
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
MAX_PROFILE_BYTES = 256 * 1024
MAX_AUTH_BYTES = 1024 * 1024
HASH_CHUNK_BYTES = 1024 * 1024
SMOKE_TIMEOUT_SEC = 90
EXECUTE_TIMEOUT_SEC = 300
VERSION_TIMEOUT_SEC = 10
INSPECT_TIMEOUT_SEC = 10
SUPPORTED_GROK_VERSION = "1.0.13"
# An isolated GROK_HOME intentionally has no updater-channel metadata, so the
# exact binary reports no trailing channel label. The code-owned SHA-256 below
# separately binds the full macOS arm64 executable bytes.
SUPPORTED_GROK_BUILD = "grok 1.0.13 (5e9a58528b76)"
SUPPORTED_GROK_BINARY_SHA256 = {
    ("darwin", "arm64"): "8669e0fdadceec25b8c159c355f427ffbd82583525d774b6ab1522197ea83b80",
}
RUNTIME_SOCKET_ERROR = "runtime-socket deny resolution failed"
# Documented Grok 1.0.x compatibility scanners. Child env disables them without
# changing user/global config or leaking secret values into prompts/logs.
COMPAT_DISABLE_ENV = {
    "GROK_CLAUDE_SKILLS_ENABLED": "0",
    "GROK_CLAUDE_RULES_ENABLED": "0",
    "GROK_CLAUDE_AGENTS_ENABLED": "0",
    "GROK_CLAUDE_MCPS_ENABLED": "0",
    "GROK_CLAUDE_HOOKS_ENABLED": "0",
    "GROK_CLAUDE_SESSIONS_ENABLED": "0",
    "GROK_CURSOR_SKILLS_ENABLED": "0",
    "GROK_CURSOR_RULES_ENABLED": "0",
    "GROK_CURSOR_AGENTS_ENABLED": "0",
    "GROK_CURSOR_MCPS_ENABLED": "0",
    "GROK_CURSOR_HOOKS_ENABLED": "0",
    "GROK_CURSOR_SESSIONS_ENABLED": "0",
    "GROK_CODEX_SKILLS_ENABLED": "0",
    "GROK_CODEX_RULES_ENABLED": "0",
    "GROK_CODEX_AGENTS_ENABLED": "0",
    "GROK_CODEX_MCPS_ENABLED": "0",
    "GROK_CODEX_HOOKS_ENABLED": "0",
    "GROK_CODEX_SESSIONS_ENABLED": "0",
    "GROK_SUBAGENTS": "0",
    "GROK_MEMORY": "0",
    "GROK_WORKFLOWS": "0",
    "GROK_WEB_FETCH": "0",
    "GROK_MANAGED_MCPS_ENABLED": "0",
    "GROK_MANAGED_MCP_GATEWAY_TOOLS_ENABLED": "0",
    "GROK_TELEMETRY_ENABLED": "0",
    "GROK_TELEMETRY_TRACE_UPLOAD": "0",
    "GROK_CRASH_HANDLER": "0",
    "GROK_CAMPAIGNS": "0",
}
APPROVED_STANDING_TEMPLATE = [
    "--cwd", "{repo}", "--sandbox", "{sandbox_profile}", "--agent", "{agent_profile}",
    "--prompt-file", "{brief_path}", "--model", "grok-4.6", "--reasoning-effort", "high",
    "--no-subagents", "--output-format", "plain",
    "--tools", "read_file,grep,list_dir",
    "--disallowed-tools", "run_terminal_cmd,search_replace,Agent",
    "--deny", "MCPTool(*)",
    "--disable-web-search",
    "--no-auto-update",
]


def generate_sandbox_profile_name() -> str:
    name = SANDBOX_PROFILE_PREFIX + secrets.token_hex(16)
    validate_sandbox_profile_name(name)
    return name


def validate_sandbox_profile_name(name: str) -> str:
    if not isinstance(name, str) or not SANDBOX_PROFILE_RE.fullmatch(name):
        raise ValueError("sandbox profile name is not a per-run unshadowable mb-standing id")
    return name


def _runtime_socket_candidates() -> list[Path]:
    paths = [
        Path("/run/docker.sock"),
        Path("/var/run/docker.sock"),
        Path("/run/podman/podman.sock"),
        Path("/var/run/podman/podman.sock"),
        Path("/run/containerd/containerd.sock"),
        Path("/var/run/containerd/containerd.sock"),
    ]
    uid = os.getuid()
    paths.extend([
        Path(f"/run/user/{uid}/docker.sock"),
        Path(f"/run/user/{uid}/podman/podman.sock"),
        Path(f"/run/user/{uid}/containerd/containerd.sock"),
    ])
    home = Path.home()
    paths.extend([
        home / ".docker" / "desktop" / "docker.sock",
        home / ".docker" / "run" / "docker.sock",
    ])
    return paths


def _endpoint_symlink_incompatible(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ValueError(f"runtime socket {path} cannot be inspected: {exc}") from exc
    return stat.S_ISLNK(metadata.st_mode)


def auto_runtime_socket_deny_incompatible() -> bool:
    """True when Grok 1.0.13 would refuse restrict_network auto-deny (symlink endpoints)."""
    return any(_endpoint_symlink_incompatible(path) for path in _runtime_socket_candidates())


def _safe_lstat_exists(path: Path) -> tuple[bool, bool]:
    """Return (exists_or_symlink, is_symlink) without following the path."""
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False, False
    except OSError as exc:
        raise ValueError(f"runtime socket {path} cannot be inspected: {exc}") from exc
    return True, stat.S_ISLNK(metadata.st_mode)


def resolve_runtime_socket_denies() -> list[str]:
    """Return unique resolved existing socket targets, or raise to PARK."""
    denies: list[str] = []
    for path in _runtime_socket_candidates():
        present, is_link = _safe_lstat_exists(path)
        if not present:
            continue
        try:
            resolved = Path(os.path.realpath(path))
        except OSError as exc:
            raise ValueError(
                f"runtime socket {path} exists or is a symlink but cannot be resolved: {exc}"
            ) from exc
        try:
            resolved_metadata = os.lstat(resolved)
        except FileNotFoundError as exc:
            raise ValueError(
                f"runtime socket {path} exists or is a symlink but has no safe "
                "existing non-symlink target"
            ) from exc
        except OSError as exc:
            raise ValueError(
                f"runtime socket {path} exists or is a symlink but cannot be resolved: {exc}"
            ) from exc
        if stat.S_ISLNK(resolved_metadata.st_mode):
            raise ValueError(
                f"runtime socket {path} exists or is a symlink but has no safe "
                "existing non-symlink target"
            )
        text = str(resolved)
        if text not in denies:
            denies.append(text)
        if is_link:
            # Presence as a symlink is already recorded via the resolved target.
            continue
    return denies


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _sandbox_profile_text(
    sandbox_profile: str,
    *,
    platform: str | None = None,
    denies: list[str] | None = None,
    incompatible: bool | None = None,
) -> str:
    name = validate_sandbox_profile_name(sandbox_profile)
    host = sys.platform if platform is None else platform
    lines = [f"[profiles.{name}]", 'extends = "strict"']
    # Grok 1.0.13 auto-appends well-known runtime sockets when restrict_network
    # is true (inherited from strict). Symlink endpoints such as OrbStack's
    # /var/run/docker.sock make that resolution fail closed inside Grok.
    # Child-network blocking is a documented no-op on macOS only.
    if incompatible is None:
        incompatible = auto_runtime_socket_deny_incompatible()
    if incompatible and host != "darwin":
        raise ValueError(
            "symlink runtime-socket endpoints require weakening inherited "
            "restrict_network, which is allowed only on macOS; PARK on this platform"
        )
    if denies is None:
        denies = resolve_runtime_socket_denies()
    if incompatible:
        lines.append("restrict_network = false")
    if denies:
        rendered = ", ".join(_toml_string(item) for item in denies)
        lines.append(f"deny = [{rendered}]")
    lines.append("")
    return "\n".join(lines)


def _child_env(runtime_root: Path) -> dict[str, str]:
    """Return a secret-scrubbed environment rooted only in private run directories."""
    root = runtime_root.resolve()
    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(root / "home"),
        "GROK_HOME": str(root / "grok-home"),
        "TMPDIR": str(root / "tmp"),
        "LANG": "C.UTF-8",
    }
    env.update(COMPAT_DISABLE_ENV)
    return env


def _stage_isolated_runtime(runtime_root: Path, auth_bytes: bytes | None) -> None:
    os.chmod(runtime_root, 0o700)
    for name in ("home", "grok-home", "tmp"):
        path = runtime_root / name
        path.mkdir(mode=0o700, exist_ok=False)
    if auth_bytes is None:
        return
    auth = runtime_root / "grok-home" / "auth.json"
    with auth.open("xb") as handle:
        handle.write(auth_bytes)
    os.chmod(auth, 0o600)
    if _read_regular_nofollow(auth, max_bytes=MAX_AUTH_BYTES, label="staged Grok auth") != auth_bytes:
        raise ValueError("staged Grok auth differs from validated snapshot")


def _staged_auth_problem(runtime_root: Path, expected: bytes) -> str | None:
    auth = runtime_root / "grok-home" / "auth.json"
    try:
        actual = _read_regular_nofollow(auth, max_bytes=MAX_AUTH_BYTES, label="staged Grok auth")
    except (OSError, ValueError) as exc:
        return f"isolated Grok auth could not be revalidated after launch: {exc}"
    if actual != expected:
        return (
            "isolated Grok auth was refreshed or changed during launch; the source credential "
            "was not overwritten, so re-authenticate Grok before the next run"
        )
    return None


def _auth_snapshot() -> tuple[bytes | None, str | None]:
    configured = os.environ.get("GROK_HOME")
    if configured:
        grok_home = Path(configured).expanduser()
        if not grok_home.is_absolute():
            return None, "GROK_HOME must be absolute before Grok auth can be isolated"
    else:
        grok_home = Path.home() / ".grok"
    auth = grok_home / "auth.json"
    try:
        fd = _open_regular_nofollow(auth, "Grok auth.json")
        with os.fdopen(fd, "rb") as handle:
            metadata = os.fstat(handle.fileno())
            if metadata.st_uid != os.getuid():
                return None, "Grok auth.json must be owned by the current user"
            if stat.S_IMODE(metadata.st_mode) & 0o077:
                return None, "Grok auth.json must not grant group or other permissions"
            raw = handle.read(MAX_AUTH_BYTES + 1)
            if len(raw) > MAX_AUTH_BYTES:
                return None, f"Grok auth.json exceeds {MAX_AUTH_BYTES} bytes"
            after = os.fstat(handle.fileno())
            stable_fields = (
                "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_mode", "st_uid", "st_gid"
            )
            if any(getattr(metadata, field) != getattr(after, field) for field in stable_fields):
                return None, "Grok auth.json changed while its private snapshot was being read"
        parsed = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return None, f"Grok auth.json cannot be safely staged: {exc}"
    if not isinstance(parsed, dict) or not parsed:
        return None, "Grok auth.json must contain a non-empty JSON object"
    return raw, None


def _open_regular_nofollow(path: Path, label: str) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError(f"{label} cannot be opened safely: O_NOFOLLOW is unavailable")
    try:
        fd = os.open(path, os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0))
    except OSError as exc:
        raise ValueError(f"{label} cannot be opened as a regular non-symlink file: {exc}") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{label} is not a regular non-symlink file")
    except Exception:
        os.close(fd)
        raise
    return fd


def _read_regular_nofollow(path: Path, *, max_bytes: int, label: str) -> bytes:
    fd = _open_regular_nofollow(path, label)
    chunks = []
    total = 0
    with os.fdopen(fd, "rb") as handle:
        while True:
            chunk = handle.read(min(HASH_CHUNK_BYTES, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"{label} exceeds {max_bytes} bytes")
            chunks.append(chunk)
    return b"".join(chunks)


def _stream_sha256(path: Path, *, max_bytes: int = MAX_EVIDENCE_BYTES) -> str:
    digest = hashlib.sha256()
    total = 0
    fd = _open_regular_nofollow(path, "bound evidence")
    with os.fdopen(fd, "rb") as handle:
        while True:
            chunk = handle.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(
                    f"bound evidence exceeds {max_bytes} bytes "
                    "(code-owned limit for deposited CSV/JSON/text/image evidence)"
                )
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _copy_evidence_streaming(source: Path, dest: Path, expected_digest: str) -> None:
    digest = hashlib.sha256()
    total = 0
    source_fd = _open_regular_nofollow(source, "bound evidence")
    with os.fdopen(source_fd, "rb") as src, dest.open("xb") as dst:
        while True:
            chunk = src.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_EVIDENCE_BYTES:
                raise ValueError(
                    f"bound evidence exceeds {MAX_EVIDENCE_BYTES} bytes "
                    "(code-owned limit for deposited CSV/JSON/text/image evidence)"
                )
            digest.update(chunk)
            dst.write(chunk)
    copied = "sha256:" + digest.hexdigest()
    if copied != expected_digest:
        raise ValueError("bound evidence digest does not match evidence-sha256")
    restaged = _stream_sha256(dest)
    if restaged != expected_digest:
        raise ValueError("staged evidence digest changed after copy")


def _evidence_size_problem(evidence: Path) -> str | None:
    try:
        metadata = os.lstat(evidence)
    except OSError as exc:
        return f"bound evidence is unreadable: {exc}"
    if not stat.S_ISREG(metadata.st_mode):
        return "bound evidence must be a regular non-symlink file"
    if metadata.st_size > MAX_EVIDENCE_BYTES:
        return (
            f"bound evidence exceeds {MAX_EVIDENCE_BYTES} bytes "
            "(code-owned limit for deposited CSV/JSON/text/image evidence)"
        )
    return None


def _provider_timeout_message(kind: str, timeout: int) -> str:
    return (
        f"PARK: Grok CLI {kind} timed out after {timeout}s; "
        "timeout is not a capacity/429 event"
    )


def _binary_file_snapshot(binary: str) -> tuple[tuple[int, int, int, int, int, str] | None, str | None]:
    expected_hash = SUPPORTED_GROK_BINARY_SHA256.get((sys.platform, platform.machine()))
    if expected_hash is None:
        return None, (
            "no exact Grok CLI binary hash is approved for "
            f"{sys.platform}/{platform.machine()}"
        )
    try:
        fd = _open_regular_nofollow(Path(binary), "resolved Grok executable")
    except ValueError as exc:
        return None, str(exc)
    digest = hashlib.sha256()
    try:
        before = os.fstat(fd)
        if not before.st_mode & 0o111:
            os.close(fd)
            return None, "resolved Grok executable is not executable"
        with os.fdopen(fd, "rb") as handle:
            while True:
                chunk = handle.read(HASH_CHUNK_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
            after = os.fstat(handle.fileno())
    except OSError as exc:
        return None, f"cannot hash resolved Grok executable: {exc}"
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_mode")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        return None, "resolved Grok executable changed while it was being attested"
    actual_hash = digest.hexdigest()
    if actual_hash != expected_hash:
        return None, "resolved Grok executable does not match the approved binary SHA-256"
    return (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_mode,
        actual_hash,
    ), None


def _copy_attested_binary(
    source: str,
    destination: Path,
    expected_identity: tuple[int, int, int, int, int, str] | None = None,
) -> tuple[tuple[int, int, int, int, int, str] | None, str | None]:
    expected_hash = SUPPORTED_GROK_BINARY_SHA256.get((sys.platform, platform.machine()))
    if expected_hash is None:
        return None, (
            "no exact Grok CLI binary hash is approved for "
            f"{sys.platform}/{platform.machine()}"
        )
    try:
        fd = _open_regular_nofollow(Path(source), "resolved Grok executable")
    except ValueError as exc:
        return None, str(exc)
    digest = hashlib.sha256()
    try:
        before = os.fstat(fd)
        if not before.st_mode & 0o111:
            os.close(fd)
            return None, "resolved Grok executable is not executable"
        source_fields = (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode
        )
        if expected_identity is not None and source_fields != expected_identity[:5]:
            os.close(fd)
            return None, "resolved Grok executable identity changed after preflight"
        with os.fdopen(fd, "rb") as src, destination.open("xb") as dst:
            while True:
                chunk = src.read(HASH_CHUNK_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())
            after = os.fstat(src.fileno())
    except OSError as exc:
        return None, f"cannot freeze resolved Grok executable: {exc}"
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_mode")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        return None, "resolved Grok executable changed while it was being frozen"
    actual_hash = digest.hexdigest()
    if actual_hash != expected_hash:
        return None, "resolved Grok executable does not match the approved binary SHA-256"
    identity = source_fields + (actual_hash,)
    if expected_identity is not None and identity != expected_identity:
        return None, "resolved Grok executable attestation changed after preflight"
    os.chmod(destination, 0o500)
    frozen_identity, frozen_problem = _binary_file_snapshot(str(destination))
    if frozen_problem:
        return None, f"frozen Grok executable failed verification: {frozen_problem}"
    if frozen_identity is None or frozen_identity[-1] != actual_hash:
        return None, "frozen Grok executable hash differs from the validated source"
    return identity, None


def _grok_version_snapshot(binary: str) -> tuple[str | None, str | None]:
    try:
        with tempfile.TemporaryDirectory(prefix="grok-version-") as runtime_dir:
            runtime_root = Path(runtime_dir)
            _stage_isolated_runtime(runtime_root, None)
            completed = subprocess.run(
                [binary, "--version"],
                executable=binary,
                check=False,
                text=True,
                capture_output=True,
                timeout=VERSION_TIMEOUT_SEC,
                env=_child_env(runtime_root),
            )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return None, f"cannot attest Grok CLI version: {exc}"
    version = (completed.stdout or "").strip()
    if completed.returncode != 0 or version != SUPPORTED_GROK_BUILD:
        return None, (
            "Grok CLI version is not the exact approved build "
            f"{SUPPORTED_GROK_BUILD}: {version or '<empty>'}"
        )
    return version, None


def _binary_snapshot(
    candidate: str,
) -> tuple[str | None, tuple[int, int, int, int, int, str] | None, str | None, str | None]:
    try:
        binary = str(Path(os.path.realpath(candidate)).resolve(strict=True))
    except (OSError, RuntimeError) as exc:
        return None, None, None, f"cannot resolve Grok executable: {exc}"
    try:
        with tempfile.TemporaryDirectory(prefix="grok-binary-attest-") as runtime_dir:
            runtime_root = Path(runtime_dir)
            _stage_isolated_runtime(runtime_root, None)
            frozen = runtime_root / "grok-executable"
            identity, identity_problem = _copy_attested_binary(binary, frozen)
            if identity_problem:
                return binary, None, None, identity_problem
            version, version_problem = _grok_version_snapshot(str(frozen))
    except (OSError, ValueError) as exc:
        return binary, None, None, f"cannot privately attest Grok executable: {exc}"
    return binary, identity, version, version_problem


def _binary_recheck_problem(
    binary: str, expected_identity: tuple[int, int, int, int, int, str],
    expected_version: str,
) -> str | None:
    identity, problem = _binary_file_snapshot(binary)
    if problem:
        return problem
    if identity != expected_identity:
        return "resolved Grok executable identity changed after preflight"
    version, problem = _grok_version_snapshot(binary)
    if problem:
        return problem
    if version != expected_version:
        return "resolved Grok executable version changed after preflight"
    return None


def _frozen_binary_problem(binary: str, expected_version: str) -> str | None:
    identity, problem = _binary_file_snapshot(binary)
    if problem:
        return problem
    if identity is None:
        return "frozen Grok executable has no validated identity"
    version, problem = _grok_version_snapshot(binary)
    if problem:
        return problem
    if version != expected_version:
        return "frozen Grok executable version differs from preflight"
    return None


def _effective_config_problem(binary: str, staging: Path, env: dict[str, str]) -> str | None:
    try:
        completed = subprocess.run(
            [binary, "inspect", "--json"],
            executable=binary,
            cwd=str(staging),
            check=False,
            text=True,
            capture_output=True,
            timeout=INSPECT_TIMEOUT_SEC,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"cannot verify isolated Grok effective configuration: {exc}"
    if completed.returncode != 0:
        return "isolated Grok effective-configuration inspection failed"
    try:
        data = json.loads(completed.stdout or "")
    except (TypeError, json.JSONDecodeError):
        return "isolated Grok effective-configuration inspection returned invalid JSON"
    if not isinstance(data, dict):
        return "isolated Grok effective-configuration inspection returned a non-object"
    if data.get("grokVersion") != SUPPORTED_GROK_VERSION:
        return "isolated Grok inspection reported the wrong version"
    if data.get("cwd") != str(staging) or data.get("projectRoot") is not None:
        return "isolated Grok inspection discovered an unexpected project root"
    if data.get("projectInstructions") != []:
        return "isolated Grok inspection discovered project instructions"
    for key in ("hooks", "skills", "plugins", "marketplaces", "mcpServers", "lspServers"):
        if data.get(key) != []:
            return f"isolated Grok inspection discovered {key}"
    expected_agents = {
        ("general-purpose", "builtin"),
        ("explore", "builtin"),
        ("plan", "builtin"),
    }
    agents = data.get("agents")
    if not isinstance(agents, list) or {
        (item.get("name"), (item.get("source") or {}).get("type"))
        for item in agents if isinstance(item, dict)
    } != expected_agents or len(agents) != len(expected_agents):
        return "isolated Grok inspection discovered non-builtin agents"
    permissions = data.get("permissions")
    if not isinstance(permissions, dict):
        return "isolated Grok inspection omitted permission provenance"
    if (
        permissions.get("sources") != []
        or permissions.get("loaded") != 0
        or permissions.get("skipped") != []
        or permissions.get("mcpServerAllowlist") != []
        or permissions.get("marketplaceAllowlist") != []
        or permissions.get("managedSettingsExists") is not False
        or permissions.get("managedSettingsActive") is not False
    ):
        return "isolated Grok inspection discovered managed or external permissions"
    login_policy = data.get("loginPolicy")
    if not isinstance(login_policy, dict) or (
        login_policy.get("disableApiKeyAuth") is not None
        or login_policy.get("forceLoginTeamUuid") is not None
        or login_policy.get("apiKeyAuthDisabled") is not False
    ):
        return "isolated Grok inspection discovered a managed login policy"
    config_sources = data.get("configSources")
    if not isinstance(config_sources, dict) or config_sources.get("layers") != []:
        return "isolated Grok inspection discovered a config or requirements layer"
    external = data.get("externalCompat")
    if not isinstance(external, dict) or external.get("remoteSettingsLoaded") is not False:
        return "isolated Grok inspection discovered remote compatibility settings"
    cells = external.get("cells")
    if not isinstance(cells, list) or not cells or any(
        not isinstance(cell, dict) or cell.get("enabled") is not False for cell in cells
    ):
        return "isolated Grok inspection found an enabled compatibility surface"
    return None


def _run_provider(cmd: list[str], *, executable: str, cwd: str, timeout: int, kind: str,
                  capture_output: bool, env: dict[str, str]) -> subprocess.CompletedProcess[str] | int:
    try:
        return subprocess.run(
            cmd,
            executable=executable,
            cwd=cwd,
            check=False,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        print(_provider_timeout_message(kind, timeout), file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"PARK: Grok CLI {kind} could not start: {exc}", file=sys.stderr)
        return 2


def _sandbox_apply_problem(stdout: str, stderr: str, sandbox_profile: str) -> str | None:
    blob = f"{stdout}\n{stderr}"
    named = sandbox_profile in blob and "could not apply the" in blob
    if RUNTIME_SOCKET_ERROR in blob:
        return (
            f"Grok CLI refused the {sandbox_profile} sandbox because a well-known "
            "runtime-socket deny endpoint is a symlink (Grok 1.0.13). "
            "Standing-role execution stays parked rather than falling back to "
            "workspace/read-only/off or an unenforced profile."
        )
    if named:
        return (
            f"Grok CLI refused the required per-run {sandbox_profile} sandbox. "
            "Standing-role execution stays parked rather than falling back to "
            "workspace/read-only/off or an unenforced profile."
        )
    return None


def _render(
    recipe: dict,
    *,
    cwd: Path,
    prompt_file: Path,
    agent_profile: Path,
    sandbox_profile: str,
) -> list[str]:
    context = {
        "repo": str(cwd),
        "brief_path": str(prompt_file),
        "agent_profile": str(agent_profile),
        "sandbox_profile": str(sandbox_profile),
    }
    argv = [str(recipe.get("bin") or "")]
    for raw in recipe.get("args_template") or []:
        token = str(raw)
        for key, value in context.items():
            token = token.replace("{" + key + "}", value)
        argv.append(token)
    return argv


def _role_name_for_agent(agent: str | None) -> str | None:
    if not agent or not agent.startswith("mb-"):
        return None
    name = agent[3:]
    if name not in sync_profiles.STANDING_GROK_TOOLS:
        return None
    return name


def _profile_snapshot(
    profile: Path | None, agent: str | None
) -> tuple[bytes | None, str | None]:
    if not agent or profile is None:
        return None, f"required Grok agent profile {agent!r} is not installed as a regular file"
    try:
        metadata = os.lstat(profile)
    except FileNotFoundError:
        return None, f"required Grok agent profile {agent!r} is not installed as a regular file"
    except OSError as exc:
        return None, f"cannot validate installed profile {profile}: {exc}"
    if not stat.S_ISREG(metadata.st_mode):
        return None, f"required Grok agent profile {agent!r} is not installed as a regular file"
    try:
        raw = _read_regular_nofollow(
            profile, max_bytes=MAX_PROFILE_BYTES, label="installed Grok agent profile"
        )
        actual = raw.decode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        return None, f"cannot validate installed profile {profile}: {exc}"
    role_name = _role_name_for_agent(agent)
    if role_name is None:
        return None, f"required Grok agent profile {agent!r} is not a standing read-only seat"
    tool_problem = sync_profiles.standing_tools_problem(
        role_name, sync_profiles.grok_tools_from_profile(actual)
    )
    if tool_problem:
        return None, (
            f"installed profile {profile} fails the standing Grok tool allowlist: {tool_problem}"
        )
    try:
        expected = sync_profiles.expected().get(profile.name)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        return None, f"cannot validate installed profile {profile}: {exc}"
    if expected is None or actual != expected:
        return None, f"installed profile {profile} does not byte-match generated read-only policy"
    expected_tools = sync_profiles.grok_tools_from_profile(expected)
    expected_tool_problem = sync_profiles.standing_tools_problem(role_name, expected_tools)
    if expected_tool_problem:
        return None, (
            f"generated profile {profile.name} fails the standing Grok tool allowlist: "
            f"{expected_tool_problem}"
        )
    return raw, None


def _profile_problem(profile: Path | None, agent: str | None) -> str | None:
    _raw, problem = _profile_snapshot(profile, agent)
    return problem


def _prompt_problem(
    seat: str,
    prompt_file: Path | None,
    cwd: Path | None = None,
    *,
    bind_changed_paths: bool = True,
    raw_snapshot: bytes | None = None,
) -> str | None:
    if prompt_file is None:
        return "prompt file must be a regular non-symlink file"
    if raw_snapshot is None:
        try:
            raw = _read_regular_nofollow(
                prompt_file, max_bytes=65_536, label="prompt file"
            )
        except (OSError, ValueError) as exc:
            return f"prompt file is not readable UTF-8: {exc}"
    else:
        raw = raw_snapshot
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        return f"prompt file is not readable UTF-8: {exc}"
    if not raw or "\x00" in text:
        return "prompt file must be non-empty UTF-8 and at most 65536 bytes"
    if seat == "grok-bot-review-d":
        config = connector_packets.load()
        try:
            canonical = connector_packets.reconstruct_review_d_packet(config, text)
        except SystemExit as exc:
            return str(exc) or "Review D prompt must byte-match a reconstructed packet"
        if canonical != text:
            return "Review D prompt must byte-match a reconstructed packet"
        parsed = connector_packets.parse_review_d_packet(text)
        if parsed["mode"] == "preview-review" and bind_changed_paths and cwd is not None:
            for rel in parsed["changed_paths"]:
                try:
                    connector_packets.bind_changed_path(cwd, rel)
                except ValueError as exc:
                    return f"PARK: changed-path cannot be proven in the repository: {exc}"
        elif parsed["mode"] == "live-storefront-audit" and parsed["changed_paths"]:
            return "live Review D packet must not carry changed paths"
        return None
    required_role = {
        "grok-bot-heat-map": "heat-map",
        "grok-bot-marketplace-intelligence": "marketplace-intelligence",
    }.get(seat)
    allowed_fields = {
        "role", "source", "artifact-class", "evidence-path", "evidence-sha256",
        "site", "date-range", "question", "scope",
    }
    fields = _parse_evidence_fields(text, allowed_fields)
    if isinstance(fields, str):
        return fields
    if fields.get("role") != required_role:
        return f"prompt must declare exact role: {required_role}"
    allowed_sources = ({"approved-clarity-export"} if seat == "grok-bot-heat-map"
                       else {"owner-deposited", "authorized-api-output"})
    if fields.get("source") not in allowed_sources:
        return "prompt must declare an approved evidence source"
    policy = mborch.load_config("handoff-policy.json", required=True)
    artifact_class = fields.get("artifact-class")
    ordinary = handoff_policy.configured_classes(policy, "ordinary_artifacts")
    restricted = handoff_policy.effective_restricted_artifacts(policy)
    if not artifact_class or artifact_class not in ordinary or artifact_class in restricted:
        return "prompt artifact-class must be an ordinary non-restricted handoff class"
    evidence_raw = fields.get("evidence-path")
    digest = fields.get("evidence-sha256")
    if not evidence_raw or not digest or not digest.startswith("sha256:"):
        return "prompt must bind evidence-path and evidence-sha256"
    evidence = Path(evidence_raw).expanduser()
    if not evidence.is_absolute():
        evidence = (prompt_file.parent / evidence).resolve()
    size_problem = _evidence_size_problem(evidence)
    if size_problem:
        return size_problem
    try:
        actual_digest = _stream_sha256(evidence)
    except (OSError, ValueError) as exc:
        return f"bound evidence is unreadable: {exc}"
    if actual_digest != digest:
        return "bound evidence digest does not match evidence-sha256"
    return None


def _prompt_snapshot(
    seat: str, prompt_file: Path | None, cwd: Path | None
) -> tuple[bytes | None, str | None]:
    if prompt_file is None:
        return None, "prompt file must be a regular non-symlink file"
    try:
        raw = _read_regular_nofollow(prompt_file, max_bytes=65_536, label="prompt file")
    except (OSError, ValueError) as exc:
        return None, f"prompt file is not readable UTF-8: {exc}"
    problem = _prompt_problem(
        seat, prompt_file, cwd, bind_changed_paths=True, raw_snapshot=raw
    )
    return raw, problem


def _parse_evidence_fields(text: str, allowed_fields: set[str]) -> dict[str, str] | str:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        key = key.strip()
        if not sep or not key or key not in allowed_fields:
            return "prompt contains an unknown or unstructured evidence field"
        if key in fields:
            return f"prompt contains duplicate field: {key}"
        fields[key] = value.strip()
    return fields


def _canonical_evidence_prompt(fields: dict[str, str], evidence_path: str) -> str:
    order = (
        "role", "source", "artifact-class", "evidence-path", "evidence-sha256",
        "site", "date-range", "question", "scope",
    )
    lines = []
    for key in order:
        if key in fields:
            value = evidence_path if key == "evidence-path" else fields[key]
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def _write_sandbox_profile(staging: Path, sandbox_profile: str) -> Path:
    grok_dir = staging / ".grok"
    grok_dir.mkdir(parents=True, exist_ok=False)
    profile = grok_dir / "sandbox.toml"
    profile.write_text(_sandbox_profile_text(sandbox_profile), encoding="utf-8")
    return profile


def _stage_workspace(
    seat: str, prompt_bytes: bytes, prompt_origin: Path, staging: Path
) -> Path:
    staged_prompt = staging / PROMPT_STAGED_NAME
    if seat == "grok-bot-review-d":
        staged_prompt.write_bytes(prompt_bytes)
    else:
        raw = prompt_bytes.decode("utf-8")
        allowed_fields = {
            "role", "source", "artifact-class", "evidence-path", "evidence-sha256",
            "site", "date-range", "question", "scope",
        }
        fields = _parse_evidence_fields(raw, allowed_fields)
        if isinstance(fields, str):
            raise ValueError(fields)
        source_evidence = Path(fields["evidence-path"]).expanduser()
        if not source_evidence.is_absolute():
            source_evidence = (prompt_origin.parent / source_evidence).resolve()
        size_problem = _evidence_size_problem(source_evidence)
        if size_problem:
            raise ValueError(size_problem)
        staged_evidence = staging / EVIDENCE_STAGED_NAME
        _copy_evidence_streaming(source_evidence, staged_evidence, fields["evidence-sha256"])
        staged_prompt.write_text(
            _canonical_evidence_prompt(fields, EVIDENCE_STAGED_NAME),
            encoding="utf-8",
        )
        if str(source_evidence) in staged_prompt.read_text(encoding="utf-8"):
            raise ValueError("staged prompt still contains the source evidence path")
    problem = _prompt_problem(seat, staged_prompt, bind_changed_paths=False)
    if problem:
        raise ValueError(problem)
    return staged_prompt


def _template_problem(recipe: dict) -> str | None:
    if recipe.get("args_template") != APPROVED_STANDING_TEMPLATE:
        return "recipe argv differs from the approved staged custom-sandbox contract"
    return None


def _executed_argv(
    recipe: dict,
    *,
    staging: Path,
    prompt_file: Path,
    agent_profile: Path,
    sandbox_profile: str,
) -> list[str]:
    problem = _template_problem(recipe)
    if problem:
        raise ValueError(problem)
    validate_sandbox_profile_name(sandbox_profile)
    executed = _render(
        recipe,
        cwd=staging,
        prompt_file=prompt_file,
        agent_profile=agent_profile,
        sandbox_profile=sandbox_profile,
    )
    expected = _render(
        {"bin": "grok", "args_template": APPROVED_STANDING_TEMPLATE},
        cwd=staging,
        prompt_file=prompt_file,
        agent_profile=agent_profile,
        sandbox_profile=sandbox_profile,
    )
    if executed != expected:
        raise ValueError("executed argv differs from the approved staged sandbox contract")
    if str(staging) in (None, "", ".") or Path(executed[2]) != staging:
        raise ValueError("executed cwd is not the ephemeral staging directory")
    if executed[executed.index("--sandbox") + 1] != sandbox_profile:
        raise ValueError("executed sandbox profile is not the per-run unshadowable id")
    return executed


def _smoke_argv(
    recipe: dict, *, staging: Path, agent_profile: Path, sandbox_profile: str
) -> list[str]:
    problem = _template_problem(recipe)
    if problem:
        raise ValueError(problem)
    validate_sandbox_profile_name(sandbox_profile)
    rendered = _render(
        recipe,
        cwd=staging,
        prompt_file=Path(STAGED_PROMPT_PLACEHOLDER),
        agent_profile=agent_profile,
        sandbox_profile=sandbox_profile,
    )
    prompt_idx = rendered.index("--prompt-file")
    return rendered[:prompt_idx] + ["-p", SMOKE_PROMPT] + rendered[prompt_idx + 2 :]


class LaunchContext:
    def __init__(self, providers_data: dict, recipes: dict, registry: dict):
        self.providers_data = providers_data
        self.recipes = recipes
        self.registry = registry


def load_launch_context() -> LaunchContext:
    providers_data = copy.deepcopy(mborch.load_config("providers.json", required=True))
    recipes = copy.deepcopy(mborch.load_config("seat-exec.json", required=True)["recipes"])
    registry = copy.deepcopy(mborch.load_config("model-registry.json", required=True))
    return LaunchContext(
        providers_data=providers_data,
        recipes=recipes,
        registry=registry,
    )


class LaunchPlan:
    __slots__ = (
        "seat", "agent", "_recipe_json", "route_id", "route_state", "profile",
        "binary", "binary_version", "binary_identity", "argv", "sandbox_profile",
        "ready", "problems", "profile_bytes", "prompt_bytes", "auth_bytes",
        "execution_input_binding",
    )

    def __init__(
        self,
        seat: str,
        agent: str,
        recipe: dict,
        route_id: str | None,
        route_state: str | None,
        profile: Path | None,
        binary: str | None,
        binary_version: str | None,
        binary_identity: tuple[int, int, int, int, int, str] | None,
        argv: list,
        sandbox_profile: str,
        ready: bool,
        problems: tuple[str, ...],
        profile_bytes: bytes | None = None,
        prompt_bytes: bytes | None = None,
        auth_bytes: bytes | None = None,
        execution_input_binding: str | None = None,
    ):
        object.__setattr__(self, "seat", seat)
        object.__setattr__(self, "agent", agent)
        object.__setattr__(
            self, "_recipe_json",
            json.dumps(recipe, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        )
        object.__setattr__(self, "route_id", route_id)
        object.__setattr__(self, "route_state", route_state)
        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "binary", binary)
        object.__setattr__(self, "binary_version", binary_version)
        object.__setattr__(self, "binary_identity", tuple(binary_identity) if binary_identity else None)
        object.__setattr__(self, "argv", tuple(argv))
        object.__setattr__(self, "sandbox_profile", sandbox_profile)
        object.__setattr__(self, "ready", bool(ready))
        object.__setattr__(self, "problems", tuple(problems))
        object.__setattr__(self, "profile_bytes", bytes(profile_bytes) if profile_bytes is not None else None)
        object.__setattr__(self, "prompt_bytes", bytes(prompt_bytes) if prompt_bytes is not None else None)
        object.__setattr__(self, "auth_bytes", bytes(auth_bytes) if auth_bytes is not None else None)
        object.__setattr__(self, "execution_input_binding", execution_input_binding)

    def __setattr__(self, _name, _value):
        raise AttributeError("LaunchPlan is immutable")

    @property
    def recipe(self) -> dict:
        return json.loads(self._recipe_json)

    def inspect_result(self) -> dict:
        inspect_argv = _render(
            self.recipe if self.recipe.get("args_template") == APPROVED_STANDING_TEMPLATE
            else {"bin": "grok", "args_template": APPROVED_STANDING_TEMPLATE},
            cwd=Path(STAGED_CWD_PLACEHOLDER),
            prompt_file=Path(STAGED_PROMPT_PLACEHOLDER),
            agent_profile=Path(STAGED_AGENT_PLACEHOLDER),
            sandbox_profile=STAGED_SANDBOX_PLACEHOLDER,
        )
        # Inspect must render the actual validated recipe with safe placeholders.
        # The code-owned template is used only as the equality validator above.
        if self.recipe.get("args_template") == APPROVED_STANDING_TEMPLATE:
            inspect_argv = _render(
                self.recipe,
                cwd=Path(STAGED_CWD_PLACEHOLDER),
                prompt_file=Path(STAGED_PROMPT_PLACEHOLDER),
                agent_profile=Path(STAGED_AGENT_PLACEHOLDER),
                sandbox_profile=STAGED_SANDBOX_PLACEHOLDER,
            )
        return {
            "seat": self.seat,
            "agent": self.agent,
            "route": self.route_id,
            "route_state": self.route_state,
            "required_capabilities": list(REQUIRED_CAPABILITIES[self.seat]),
            "execution_input_binding": self.execution_input_binding,
            "binary": self.binary,
            "binary_version": self.binary_version,
            "binary_sha256": self.binary_identity[-1] if self.binary_identity else None,
            "profile": str(self.profile) if self.profile else None,
            "argv": inspect_argv,
            "ready": self.ready,
            "problems": list(self.problems),
        }


def prepare_launch_plan(
    seat: str,
    cwd: Path,
    prompt_file: Path | None,
    agent_dir: Path,
    ctx: LaunchContext,
    *,
    smoke: bool = False,
) -> LaunchPlan:
    providers = ctx.providers_data.get("providers") or {}
    recipe = copy.deepcopy(ctx.recipes.get(seat) or {})
    registry = ctx.registry
    provider = providers.get(seat) or {}
    route_id = provider.get("route")
    route = (registry.get("routes") or {}).get(route_id) or {}
    agent = recipe.get("required_agent")
    profile = agent_dir / f"{agent}.md" if agent else None
    binary = None
    binary_version = None
    binary_identity = None
    sandbox_profile = generate_sandbox_profile_name()
    problems: list[str] = []
    prompt_bytes: bytes | None = None
    auth_bytes: bytes | None = None
    execution_input_binding = EXECUTION_INPUT_BINDINGS[seat]

    if not smoke:
        if execution_input_binding is None:
            problems.append(
                "code-owned role input transport is not implemented for this CLI seat; "
                "registry or inventory attestations cannot promote it"
            )
        registry_errors = model_registry.validate(registry, providers=ctx.providers_data)
        if registry_errors:
            problems.append("model registry is invalid: " + "; ".join(registry_errors))
        if provider.get("kind") != "cli":
            problems.append("provider is not a CLI seat")
        if provider.get("model") != "grok-4.6" or route.get("model") != "grok-4.6":
            problems.append("provider and route must pin exact model grok-4.6")
        if route.get("host") != "grok-cli" or route.get("harness") != "grok":
            problems.append("provider route is not the Grok CLI harness")
        if not provider.get("wired"):
            problems.append("provider wired is not true")
        if route.get("route_state") != "live_verified":
            problems.append(f"route {route_id!r} is not live_verified")
        prompt_bytes, prompt_problem = _prompt_snapshot(seat, prompt_file, cwd)
        if prompt_problem:
            problems.append(prompt_problem)
        for capability in REQUIRED_CAPABILITIES[seat]:
            ok, reason = integrations.effective(
                "grok", "capability", capability, require_callable=True
            )
            if not ok:
                problems.append(
                    f"required runtime capability {capability!r} is unavailable: {reason}"
                )

    if agent != AGENTS[seat]:
        problems.append(f"recipe required_agent must be exact {AGENTS[seat]!r}")
    if recipe.get("required_capabilities") != list(REQUIRED_CAPABILITIES[seat]):
        problems.append(
            f"recipe required_capabilities must be exact {list(REQUIRED_CAPABILITIES[seat])!r}"
        )
    profile_bytes, profile_problem = _profile_snapshot(profile, agent)
    if profile_problem:
        problems.append(profile_problem)
    template_problem = _template_problem(recipe)
    if template_problem:
        problems.append(template_problem)
    if recipe.get("bin") != "grok":
        problems.append("recipe binary must be exact grok")
    else:
        candidate = shutil.which("grok")
        if not candidate:
            problems.append("grok executable is not on PATH")
        else:
            binary, binary_identity, binary_version, binary_problem = _binary_snapshot(candidate)
            if binary_problem:
                problems.append(binary_problem)
    auth_bytes, auth_problem = _auth_snapshot()
    if auth_problem:
        problems.append(auth_problem)
    inspect_argv = _render(
        recipe if recipe.get("args_template") == APPROVED_STANDING_TEMPLATE else
        {"bin": "grok", "args_template": APPROVED_STANDING_TEMPLATE},
        cwd=Path(STAGED_CWD_PLACEHOLDER),
        prompt_file=Path(STAGED_PROMPT_PLACEHOLDER),
        agent_profile=Path(STAGED_AGENT_PLACEHOLDER),
        sandbox_profile=STAGED_SANDBOX_PLACEHOLDER,
    )
    if recipe.get("args_template") == APPROVED_STANDING_TEMPLATE:
        inspect_argv = _render(
            recipe,
            cwd=Path(STAGED_CWD_PLACEHOLDER),
            prompt_file=Path(STAGED_PROMPT_PLACEHOLDER),
            agent_profile=Path(STAGED_AGENT_PLACEHOLDER),
            sandbox_profile=STAGED_SANDBOX_PLACEHOLDER,
        )
    if STAGED_SANDBOX_PLACEHOLDER not in inspect_argv:
        problems.append("inspect argv must use the non-executable ephemeral sandbox placeholder")
    if inspect_argv.count(STAGED_SANDBOX_PLACEHOLDER) != 1:
        problems.append("inspect argv sandbox placeholder must appear exactly once")
    if str(cwd) in inspect_argv or (prompt_file is not None and str(prompt_file) in inspect_argv):
        problems.append("inspect argv must not include the source repository or source prompt path")

    return LaunchPlan(
        seat=seat,
        agent=agent,
        recipe=recipe,
        route_id=route_id,
        route_state=route.get("route_state"),
        profile=profile,
        binary=binary,
        binary_version=binary_version,
        binary_identity=binary_identity,
        argv=inspect_argv,
        sandbox_profile=sandbox_profile,
        ready=not problems,
        problems=tuple(problems),
        profile_bytes=profile_bytes,
        prompt_bytes=prompt_bytes,
        auth_bytes=auth_bytes,
        execution_input_binding=execution_input_binding,
    )


def inspect(
    seat: str,
    cwd: Path,
    prompt_file: Path | None,
    agent_dir: Path,
    ctx: LaunchContext | None = None,
) -> dict:
    plan = prepare_launch_plan(
        seat, cwd, prompt_file, agent_dir, ctx or load_launch_context()
    )
    return plan.inspect_result()


def _run_validated_plan(plan: LaunchPlan, *, cwd: Path, prompt_file: Path | None,
                        smoke: bool) -> int:
    if not plan.ready:
        print("PARK: launch plan is not ready", file=sys.stderr)
        return 2
    if not smoke and plan.execution_input_binding is None:
        print("PARK: code-owned role input transport is not implemented", file=sys.stderr)
        return 2
    if (
        plan.profile is None
        or plan.profile_bytes is None
        or plan.binary is None
        or plan.binary_identity is None
        or plan.binary_version is None
        or plan.auth_bytes is None
    ):
        print("PARK: required Grok profile, binary, or private auth snapshot is missing", file=sys.stderr)
        return 2
    if not smoke and (prompt_file is None or plan.prompt_bytes is None):
        print("PARK: required validated prompt snapshot is missing", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(
        prefix="grok-agent-smoke-" if smoke else "grok-agent-"
    ) as stage_dir, tempfile.TemporaryDirectory(prefix="grok-private-runtime-") as runtime_dir:
        staging = Path(stage_dir)
        private_runtime = Path(runtime_dir)
        try:
            _stage_isolated_runtime(private_runtime, plan.auth_bytes)
            frozen_binary = private_runtime / "grok-executable"
            _identity, binary_copy_problem = _copy_attested_binary(
                plan.binary, frozen_binary, plan.binary_identity
            )
            if binary_copy_problem:
                raise ValueError(binary_copy_problem)
            _write_sandbox_profile(staging, plan.sandbox_profile)
            staged_profile = staging / f"{plan.agent}.md"
            staged_profile.write_bytes(plan.profile_bytes)
            os.chmod(staged_profile, 0o600)
            if staged_profile.read_bytes() != plan.profile_bytes:
                raise ValueError("staged Grok agent profile differs from validated snapshot")
            if smoke:
                cmd = _smoke_argv(
                    plan.recipe,
                    staging=staging,
                    agent_profile=staged_profile,
                    sandbox_profile=plan.sandbox_profile,
                )
            else:
                staged_prompt = _stage_workspace(
                    plan.seat, plan.prompt_bytes, prompt_file, staging
                )
                cmd = _executed_argv(
                    plan.recipe,
                    staging=staging,
                    prompt_file=staged_prompt,
                    agent_profile=staged_profile,
                    sandbox_profile=plan.sandbox_profile,
                )
        except (OSError, UnicodeError, ValueError, KeyError) as exc:
            print(f"PARK: cannot stage minimum-necessary Grok workspace: {exc}", file=sys.stderr)
            return 2
        if str(cwd) in cmd or (
            prompt_file is not None and str(prompt_file.resolve()) in cmd
        ):
            print("PARK: source repository or prompt path leaked into executed argv", file=sys.stderr)
            return 2
        child_env = _child_env(private_runtime)
        binary_problem = _frozen_binary_problem(str(frozen_binary), plan.binary_version)
        if binary_problem:
            print(f"PARK: {binary_problem}", file=sys.stderr)
            return 2
        config_problem = _effective_config_problem(str(frozen_binary), staging, child_env)
        inspect_auth_problem = _staged_auth_problem(private_runtime, plan.auth_bytes)
        if inspect_auth_problem:
            print(f"PARK: {inspect_auth_problem}", file=sys.stderr)
            return 2
        if config_problem:
            print(f"PARK: {config_problem}", file=sys.stderr)
            return 2
        binary_problem = _frozen_binary_problem(str(frozen_binary), plan.binary_version)
        if binary_problem:
            print(f"PARK: {binary_problem}", file=sys.stderr)
            return 2
        timeout = SMOKE_TIMEOUT_SEC if smoke else EXECUTE_TIMEOUT_SEC
        completed = _run_provider(
            cmd, executable=str(frozen_binary), cwd=str(staging), timeout=timeout,
            kind="smoke" if smoke else "execute",
            capture_output=True, env=child_env,
        )
        if isinstance(completed, int):
            auth_problem = _staged_auth_problem(private_runtime, plan.auth_bytes)
            if auth_problem:
                print(f"PARK: {auth_problem}", file=sys.stderr)
            return completed
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        auth_problem = _staged_auth_problem(private_runtime, plan.auth_bytes)
        if auth_problem:
            print(f"PARK: {auth_problem}", file=sys.stderr)
            return 2
        sandbox_problem = _sandbox_apply_problem(
            completed.stdout or "", completed.stderr or "", plan.sandbox_profile
        )
        if sandbox_problem:
            print(f"PARK: {sandbox_problem}", file=sys.stderr)
            return 2
        if smoke:
            last_line = (completed.stdout or "").rstrip().splitlines()[-1:]
            if completed.returncode != 0 or last_line != ["cli-agent-path-ok"]:
                print("PARK: Grok CLI smoke did not return exact cli-agent-path-ok", file=sys.stderr)
                return 2
            return 0
        return completed.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed Grok named-agent launcher (no Slack).")
    ap.add_argument("--seat", required=True, choices=SEATS)
    ap.add_argument("--prompt-file", type=Path)
    ap.add_argument("--cwd", type=Path, default=mborch.REPO)
    ap.add_argument("--agent-dir", type=Path, default=Path.home() / ".grok" / "agents")
    ap.add_argument("--integration-session", metavar="FILE|-",
                    help="fresh process-scoped Grok capability attestation")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--smoke", action="store_true",
                    help="prove only CLI/profile/model selection with a fixed no-tool prompt")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    cwd = args.cwd.resolve()
    if args.integration_session:
        try:
            integrations.load_session(args.integration_session)
        except integrations.InventoryError as exc:
            print(f"PARK: invalid integration session: {exc}", file=sys.stderr)
            return 2

    ctx = load_launch_context()
    if args.seat not in ctx.recipes:
        print(json.dumps({"seat": args.seat, "smoke": bool(args.smoke), "ready": False,
                          "problems": ["seat recipe is missing"]}))
        return 2
    plan = prepare_launch_plan(
        args.seat, cwd, args.prompt_file, args.agent_dir, ctx, smoke=bool(args.smoke)
    )
    result = plan.inspect_result()
    if args.smoke:
        result = {
            "seat": plan.seat, "agent": plan.agent, "smoke": True,
            "ready": plan.ready, "problems": list(plan.problems),
        }
        if plan.problems or not args.execute:
            print(json.dumps(result, indent=2 if args.json else None))
            return 0 if not plan.problems else 2
        return _run_validated_plan(plan, cwd=cwd, prompt_file=args.prompt_file, smoke=True)

    if args.json or not args.execute:
        print(json.dumps(result, indent=2))
    if not plan.ready:
        if args.execute and not args.json:
            print("PARK: " + "; ".join(plan.problems), file=sys.stderr)
        return 2
    if not args.execute:
        return 0
    return _run_validated_plan(plan, cwd=cwd, prompt_file=args.prompt_file, smoke=False)


if __name__ == "__main__":
    raise SystemExit(main())
