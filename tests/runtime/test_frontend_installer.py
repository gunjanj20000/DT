"""Tests for deeptutor.runtime.frontend_installer.

Covers the 10 smart frontend installer scenarios:
1. First installation when node_modules is missing.
2. Skip installation when dependencies are already valid.
3. Detect changed lockfile and reinstall.
4. Node.js missing (friendly error, no crash).
5. npm missing (friendly error, no crash).
6. npm installation failure (helpful message, fallback instructions).
7. --skip-frontend-install.
8. --install-frontend.
9. Windows compatibility (npm.cmd and subprocess kwargs).
10. Existing startup behavior remains unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest

from deeptutor.runtime import frontend_installer
from deeptutor.runtime.frontend_installer import (
    compute_lockfile_hash,
    ensure_frontend_dependencies,
    read_install_marker,
    write_install_marker,
)
import deeptutor.runtime.launcher as launcher


class _CompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def mock_node_and_npm(monkeypatch: pytest.MonkeyPatch):
    """Ensure find_node and find_npm return standard dummy paths by default."""
    monkeypatch.setattr(frontend_installer, "find_node", lambda: "/usr/bin/node")
    monkeypatch.setattr(frontend_installer, "find_npm", lambda: "/usr/bin/npm")


def _setup_web_dir(tmp_path: Path, *, with_lockfile: bool = True) -> Path:
    web = tmp_path / "web"
    web.mkdir(parents=True, exist_ok=True)
    (web / "package.json").write_text(
        json.dumps({"name": "deeptutor-web", "version": "1.0.0"}), encoding="utf-8"
    )
    if with_lockfile:
        (web / "package-lock.json").write_text(
            json.dumps({"name": "deeptutor-web", "lockfileVersion": 3}), encoding="utf-8"
        )
    return web


# 1. First installation when node_modules is missing
def test_1_first_installation_when_node_modules_missing(
    tmp_path: Path,
    mock_node_and_npm,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_dir = _setup_web_dir(tmp_path)
    assert not (web_dir / "node_modules").exists()

    executed_cmds: list[tuple[list[str], Path]] = []

    def fake_run(cmd, cwd=None, **kwargs):
        executed_cmds.append((list(cmd), Path(cwd)))
        # Simulate npm creating node_modules
        (web_dir / "node_modules").mkdir(parents=True, exist_ok=True)
        return _CompletedProcess(0)

    monkeypatch.setattr(frontend_installer.subprocess, "run", fake_run)

    result = ensure_frontend_dependencies(web_dir)
    assert result is True
    assert len(executed_cmds) == 1
    assert executed_cmds[0] == (["/usr/bin/npm", "ci", "--legacy-peer-deps"], web_dir)

    # Check marker file created
    marker = read_install_marker(web_dir)
    assert marker is not None
    assert marker.get("lockfile_hash") == compute_lockfile_hash(web_dir / "package-lock.json")


# 2. Skip installation when dependencies are already valid
def test_2_skip_installation_when_dependencies_valid(
    tmp_path: Path,
    mock_node_and_npm,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_dir = _setup_web_dir(tmp_path)
    (web_dir / "node_modules").mkdir(parents=True, exist_ok=True)
    lock_hash = compute_lockfile_hash(web_dir / "package-lock.json")
    write_install_marker(web_dir, lock_hash)

    def fake_run(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called when dependencies are valid")

    monkeypatch.setattr(frontend_installer.subprocess, "run", fake_run)

    result = ensure_frontend_dependencies(web_dir)
    assert result is True


# 3. Detect changed lockfile and reinstall
def test_3_detect_changed_lockfile_and_reinstall(
    tmp_path: Path,
    mock_node_and_npm,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_dir = _setup_web_dir(tmp_path)
    (web_dir / "node_modules").mkdir(parents=True, exist_ok=True)
    # Write marker with old hash
    write_install_marker(web_dir, "old_stale_hash_12345")

    executed_cmds: list[list[str]] = []

    def fake_run(cmd, cwd=None, **kwargs):
        executed_cmds.append(list(cmd))
        return _CompletedProcess(0)

    monkeypatch.setattr(frontend_installer.subprocess, "run", fake_run)

    result = ensure_frontend_dependencies(web_dir)
    assert result is True
    assert len(executed_cmds) == 1
    assert executed_cmds[0] == ["/usr/bin/npm", "ci", "--legacy-peer-deps"]

    # Verify marker updated with new hash
    marker = read_install_marker(web_dir)
    assert marker is not None
    assert marker.get("lockfile_hash") == compute_lockfile_hash(web_dir / "package-lock.json")
    assert marker.get("lockfile_hash") != "old_stale_hash_12345"


# 4. Node.js missing
def test_4_nodejs_missing_exits_cleanly_with_friendly_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    web_dir = _setup_web_dir(tmp_path)
    monkeypatch.setattr(frontend_installer, "find_node", lambda: None)
    monkeypatch.setattr(frontend_installer, "find_npm", lambda: "/usr/bin/npm")

    with pytest.raises(SystemExit) as exc_info:
        ensure_frontend_dependencies(web_dir)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Node.js is required" in captured.err
    assert "https://nodejs.org/" in captured.err


# 5. npm missing
def test_5_npm_missing_exits_cleanly_with_friendly_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    web_dir = _setup_web_dir(tmp_path)
    monkeypatch.setattr(frontend_installer, "find_node", lambda: "/usr/bin/node")
    monkeypatch.setattr(frontend_installer, "find_npm", lambda: None)

    with pytest.raises(SystemExit) as exc_info:
        ensure_frontend_dependencies(web_dir)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "npm is required" in captured.err
    assert "https://nodejs.org/" in captured.err


# 6. npm installation failure
def test_6_npm_installation_failure_shows_fallback_instructions(
    tmp_path: Path,
    mock_node_and_npm,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    web_dir = _setup_web_dir(tmp_path)

    monkeypatch.setattr(
        frontend_installer.subprocess,
        "run",
        lambda *args, **kwargs: _CompletedProcess(returncode=1),
    )

    with pytest.raises(SystemExit) as exc_info:
        ensure_frontend_dependencies(web_dir)

    assert "npm ci --legacy-peer-deps" in str(exc_info.value)
    captured = capsys.readouterr()
    assert "failed" in captured.err
    assert "npm ci --legacy-peer-deps" in captured.err
    assert "cd web" in captured.err
    assert "npm ci --legacy-peer-deps" in captured.err


# 7. --skip-frontend-install
def test_7_skip_frontend_install_flag(
    tmp_path: Path,
    mock_node_and_npm,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_dir = _setup_web_dir(tmp_path)
    assert not (web_dir / "node_modules").exists()

    def fake_run(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called when skip=True")

    monkeypatch.setattr(frontend_installer.subprocess, "run", fake_run)

    result = ensure_frontend_dependencies(web_dir, skip=True)
    assert result is False


# 8. --install-frontend
def test_8_force_install_frontend_flag(
    tmp_path: Path,
    mock_node_and_npm,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_dir = _setup_web_dir(tmp_path)
    (web_dir / "node_modules").mkdir(parents=True, exist_ok=True)
    lock_hash = compute_lockfile_hash(web_dir / "package-lock.json")
    write_install_marker(web_dir, lock_hash)

    executed: list[list[str]] = []

    def fake_run(cmd, cwd=None, **kwargs):
        executed.append(list(cmd))
        return _CompletedProcess(0)

    monkeypatch.setattr(frontend_installer.subprocess, "run", fake_run)

    result = ensure_frontend_dependencies(web_dir, force=True)
    assert result is True
    assert len(executed) == 1
    assert executed[0] == ["/usr/bin/npm", "ci", "--legacy-peer-deps"]


# 9. Windows compatibility
def test_9_windows_compatibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_dir = _setup_web_dir(tmp_path)
    windows_npm = "C:\\Program Files\\nodejs\\npm.cmd"

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(frontend_installer, "find_node", lambda: "C:\\Program Files\\nodejs\\node.exe")
    monkeypatch.setattr(frontend_installer, "find_npm", lambda: windows_npm)

    captured_kwargs: dict[str, Any] = {}

    def fake_run(cmd, cwd=None, **kwargs):
        captured_kwargs.update(kwargs)
        (web_dir / "node_modules").mkdir(parents=True, exist_ok=True)
        return _CompletedProcess(0)

    monkeypatch.setattr(frontend_installer.subprocess, "run", fake_run)

    result = ensure_frontend_dependencies(web_dir)
    assert result is True
    assert captured_kwargs.get("shell") is True
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        assert "creationflags" in captured_kwargs


# 10. Existing startup behavior remains unchanged
def test_10_launcher_integration_and_backward_compatibility(
    tmp_path: Path,
    mock_node_and_npm,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_dir = _setup_web_dir(tmp_path)

    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None, **kwargs):
        calls.append(list(cmd))
        (web_dir / "node_modules").mkdir(parents=True, exist_ok=True)
        return _CompletedProcess(0)

    monkeypatch.setattr(frontend_installer.subprocess, "run", fake_run)

    # Calling launcher._ensure_web_dependencies delegates properly
    launcher._ensure_web_dependencies(web_dir, npm="npm")
    assert len(calls) == 1
    assert calls[0] == ["npm", "ci", "--legacy-peer-deps"]

    # Calling it a second time is a no-op because node_modules now exists
    launcher._ensure_web_dependencies(web_dir, npm="npm")
    assert len(calls) == 1
