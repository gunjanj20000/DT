"""Smart, cross-platform installer for DeepTutor frontend dependencies.

Automatically checks Node.js, npm, package.json, package-lock.json, and node_modules.
Installs dependencies with `npm ci --legacy-peer-deps` on first launch or when
the lockfile changes, ensuring a seamless setup without manual web/ folder navigation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

logger = logging.getLogger(__name__)

INSTALL_MARKER_NAME = ".deeptutor_install.json"
NODE_RECOMMENDED_VERSIONS = "Node.js 20 LTS or 22 LTS"
NODEJS_DOWNLOAD_URL = "https://nodejs.org/"


@dataclass(frozen=True)
class FrontendDependencyStatus:
    """Snapshot of the frontend dependency state."""

    web_dir: Path
    node_path: str | None
    npm_path: str | None
    has_package_json: bool
    has_lockfile: bool
    has_node_modules: bool
    needs_install: bool
    reason: str  # "missing_node", "missing_npm", "missing_dependencies", "lockfile_changed", "forced", "up_to_date"
    current_lockfile_hash: str | None


def find_node() -> str | None:
    """Locate the node executable on the host system."""
    return shutil.which("node")


def find_npm() -> str | None:
    """Locate the npm executable on the host system across platforms."""
    npm = shutil.which("npm")
    if npm:
        return npm
    if os.name == "nt" or sys.platform == "win32":
        for candidate in ("npm.cmd", "npm.bat", "npm.exe"):
            found = shutil.which(candidate)
            if found:
                return found
    return None


def verify_web_directory(web_dir: Path) -> bool:
    """Verify that web_dir is a valid directory for frontend operations."""
    if not web_dir or not web_dir.is_dir():
        return False
    try:
        resolved = web_dir.resolve()
        if resolved == Path(resolved.anchor):
            return False
    except Exception:
        return False
    return True


def compute_lockfile_hash(lockfile: Path) -> str | None:
    """Compute the SHA-256 hash of package-lock.json (or package.json if lockfile absent)."""
    target = lockfile if lockfile.is_file() else (lockfile.parent / "package.json")
    if not target.is_file():
        return None
    hasher = hashlib.sha256()
    with target.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_install_marker_path(web_dir: Path) -> Path:
    """Return path to the install marker file inside web/node_modules."""
    return web_dir / "node_modules" / INSTALL_MARKER_NAME


def read_install_marker(web_dir: Path) -> dict[str, Any] | None:
    """Read the installation marker record if present."""
    marker_path = get_install_marker_path(web_dir)
    if not marker_path.is_file():
        return None
    try:
        data = json.loads(marker_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.debug("Failed to read install marker %s: %s", marker_path, exc)
    return None


def write_install_marker(web_dir: Path, lockfile_hash: str) -> None:
    """Store the installation marker with lockfile hash and metadata."""
    marker_path = get_install_marker_path(web_dir)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "lockfile_hash": lockfile_hash,
        "installed_at": time.time(),
        "command": "npm ci --legacy-peer-deps",
        "status": "success",
    }
    marker_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def is_usable_node_modules(web_dir: Path) -> bool:
    """Check if node_modules exists and is a directory."""
    node_modules = web_dir / "node_modules"
    return node_modules.is_dir()


def check_dependencies_status(
    web_dir: Path,
    *,
    force: bool = False,
    npm: str | None = None,
) -> FrontendDependencyStatus:
    """Inspect the frontend directory and determine whether installation is required."""
    node_path = find_node()
    npm_path = npm or find_npm()
    has_package_json = (web_dir / "package.json").is_file()
    lockfile_path = web_dir / "package-lock.json"
    has_lockfile = lockfile_path.is_file()
    has_node_modules = is_usable_node_modules(web_dir)
    current_hash = compute_lockfile_hash(lockfile_path)

    if not node_path:
        return FrontendDependencyStatus(
            web_dir=web_dir,
            node_path=None,
            npm_path=npm_path,
            has_package_json=has_package_json,
            has_lockfile=has_lockfile,
            has_node_modules=has_node_modules,
            needs_install=False,
            reason="missing_node",
            current_lockfile_hash=current_hash,
        )

    if not npm_path:
        return FrontendDependencyStatus(
            web_dir=web_dir,
            node_path=node_path,
            npm_path=None,
            has_package_json=has_package_json,
            has_lockfile=has_lockfile,
            has_node_modules=has_node_modules,
            needs_install=False,
            reason="missing_npm",
            current_lockfile_hash=current_hash,
        )

    if force:
        return FrontendDependencyStatus(
            web_dir=web_dir,
            node_path=node_path,
            npm_path=npm_path,
            has_package_json=has_package_json,
            has_lockfile=has_lockfile,
            has_node_modules=has_node_modules,
            needs_install=True,
            reason="forced",
            current_lockfile_hash=current_hash,
        )

    if not has_node_modules:
        return FrontendDependencyStatus(
            web_dir=web_dir,
            node_path=node_path,
            npm_path=npm_path,
            has_package_json=has_package_json,
            has_lockfile=has_lockfile,
            has_node_modules=False,
            needs_install=True,
            reason="missing_dependencies",
            current_lockfile_hash=current_hash,
        )

    # node_modules exists. Verify if package-lock.json has changed since last installation.
    if has_lockfile and current_hash:
        marker = read_install_marker(web_dir)
        if marker is None:
            # node_modules is already populated from a prior manual install.
            # Initialize the marker so subsequent lockfile changes are detected without re-running npm now.
            write_install_marker(web_dir, current_hash)
            return FrontendDependencyStatus(
                web_dir=web_dir,
                node_path=node_path,
                npm_path=npm_path,
                has_package_json=has_package_json,
                has_lockfile=has_lockfile,
                has_node_modules=True,
                needs_install=False,
                reason="up_to_date",
                current_lockfile_hash=current_hash,
            )
        recorded_hash = marker.get("lockfile_hash")
        if recorded_hash != current_hash:
            return FrontendDependencyStatus(
                web_dir=web_dir,
                node_path=node_path,
                npm_path=npm_path,
                has_package_json=has_package_json,
                has_lockfile=has_lockfile,
                has_node_modules=True,
                needs_install=True,
                reason="lockfile_changed",
                current_lockfile_hash=current_hash,
            )

    return FrontendDependencyStatus(
        web_dir=web_dir,
        node_path=node_path,
        npm_path=npm_path,
        has_package_json=has_package_json,
        has_lockfile=has_lockfile,
        has_node_modules=True,
        needs_install=False,
        reason="up_to_date",
        current_lockfile_hash=current_hash,
    )


def _print_node_missing_error() -> None:
    print("\n" + "─" * 60, file=sys.stderr)
    print("Error: Node.js is required to run the DeepTutor frontend.", file=sys.stderr)
    print("─" * 60, file=sys.stderr)
    print(f"• Recommended versions: {NODE_RECOMMENDED_VERSIONS}.", file=sys.stderr)
    print("• Node.js and npm must be installed and available in your PATH.", file=sys.stderr)
    print(f"• Download Node.js from: {NODEJS_DOWNLOAD_URL}", file=sys.stderr)
    print("─" * 60 + "\n", file=sys.stderr)


def _print_npm_missing_error() -> None:
    print("\n" + "─" * 60, file=sys.stderr)
    print("Error: npm is required to install DeepTutor frontend dependencies.", file=sys.stderr)
    print("─" * 60, file=sys.stderr)
    print("• Node.js was detected, but 'npm' was not found in your PATH.", file=sys.stderr)
    print(f"• Recommended versions: {NODE_RECOMMENDED_VERSIONS}.", file=sys.stderr)
    print(f"• Please install npm or download Node.js from: {NODEJS_DOWNLOAD_URL}", file=sys.stderr)
    print("─" * 60 + "\n", file=sys.stderr)


def _print_install_failed_error(returncode: int, action: str) -> None:
    print("\n" + "─" * 60, file=sys.stderr)
    print(
        f"Error: `npm {action} --legacy-peer-deps` failed (exit code {returncode}).",
        file=sys.stderr,
    )
    print("─" * 60, file=sys.stderr)
    print("Please inspect the npm error messages above for details.\n", file=sys.stderr)
    print("You can manually attempt installation by running:", file=sys.stderr)
    print("  cd web", file=sys.stderr)
    print("  npm ci --legacy-peer-deps", file=sys.stderr)
    print("  cd ..", file=sys.stderr)
    print("  deeptutor start\n", file=sys.stderr)
    print("If issues persist, verify Node.js version (20+ recommended):", file=sys.stderr)
    print("  node --version", file=sys.stderr)
    print("  npm --version", file=sys.stderr)
    print("─" * 60 + "\n", file=sys.stderr)


def _no_window_kwargs() -> dict[str, Any]:
    if os.name != "nt" and sys.platform != "win32":
        return {}
    kwargs: dict[str, Any] = {}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    if creationflags:
        kwargs["creationflags"] = creationflags
    return kwargs


def ensure_frontend_dependencies(
    web_dir: Path,
    *,
    force: bool = False,
    skip: bool = False,
    npm: str | None = None,
) -> bool:
    """Ensure frontend dependencies are installed and up-to-date.

    Parameters:
        web_dir: The directory containing package.json (usually project_root/web).
        force: Force re-running `npm ci --legacy-peer-deps`.
        skip: Skip installation even if dependencies are missing.
        npm: Optional explicit path to npm executable.

    Returns:
        True if dependencies are installed and usable, False if skipped.

    Raises:
        SystemExit: If Node.js/npm is missing or npm installation fails.
    """
    if not verify_web_directory(web_dir):
        logger.warning(
            "Frontend directory %s does not appear to be a valid DeepTutor web directory.",
            web_dir,
        )
        return False

    status = check_dependencies_status(web_dir, force=force, npm=npm)

    if skip:
        if status.needs_install:
            print("Checking frontend environment...", flush=True)
            print(
                "! Frontend dependencies missing or out of date (--skip-frontend-install specified; skipping install)",
                flush=True,
            )
        return False

    if status.reason == "missing_node":
        print("Checking frontend environment...", flush=True)
        print("✗ Node.js not detected", flush=True)
        _print_node_missing_error()
        raise SystemExit(1)

    if status.reason == "missing_npm":
        print("Checking frontend environment...", flush=True)
        print("✓ Node.js detected", flush=True)
        print("✗ npm not detected", flush=True)
        _print_npm_missing_error()
        raise SystemExit(1)

    if not status.needs_install:
        print("Checking frontend environment...", flush=True)
        print("✓ Node.js detected", flush=True)
        print("✓ Frontend dependencies installed", flush=True)
        print("✓ Dependencies up to date", flush=True)
        return True

    # Installation is needed
    action = "ci" if status.has_lockfile else "install"
    print("Checking frontend environment...", flush=True)
    print("✓ Node.js detected", flush=True)
    print("✓ npm detected", flush=True)

    if status.reason == "missing_dependencies":
        print("! Frontend dependencies missing", flush=True)
        print("Installing frontend dependencies...", flush=True)
    elif status.reason == "lockfile_changed":
        print("! package-lock.json has changed since last install", flush=True)
        print("Updating frontend dependencies...", flush=True)
    else:  # forced
        print("! Forced frontend dependency installation requested", flush=True)
        print("Installing frontend dependencies...", flush=True)

    cmd = [status.npm_path or "npm", action, "--legacy-peer-deps"]
    print(f"Running npm {action} --legacy-peer-deps ...", flush=True)

    # On Windows, batch files (.cmd/.bat) require shell=True for CreateProcess
    use_shell = (os.name == "nt" or sys.platform == "win32") and (
        status.npm_path or ""
    ).lower().endswith((".cmd", ".bat"))

    # Faster npm installation: disable audit, funding, and update notifier checks
    env = os.environ.copy()
    env["npm_config_audit"] = "false"
    env["npm_config_fund"] = "false"
    env["npm_config_update_notifier"] = "false"

    kwargs = _no_window_kwargs()
    try:
        result = subprocess.run(
            cmd,
            cwd=web_dir,
            shell=use_shell,
            check=False,
            env=env,
            **kwargs,
        )
    except Exception as exc:
        print(f"\nFailed to execute npm: {exc}", file=sys.stderr)
        _print_install_failed_error(1, action)
        raise SystemExit(1) from exc

    if result.returncode != 0:
        _print_install_failed_error(result.returncode, action)
        raise SystemExit(
            f"`npm {action} --legacy-peer-deps` failed (exit {result.returncode}). "
            "Fix the error above, then retry `deeptutor start`."
        )

    # Success: write installation marker
    if status.current_lockfile_hash:
        write_install_marker(web_dir, status.current_lockfile_hash)
    elif status.has_lockfile:
        new_hash = compute_lockfile_hash(web_dir / "package-lock.json")
        if new_hash:
            write_install_marker(web_dir, new_hash)

    print("✓ Frontend dependencies installed successfully", flush=True)
    return True
