# SPDX-License-Identifier: MIT
"""
LLA Run Manifest Writer
Creates run_manifest.json with file hashes, effective config, and optional GPG signing.
"""

import hashlib
import json
import os
import platform
import socket
from pathlib import Path
from typing import Dict, List, Any
import subprocess
from datetime import datetime, timezone


def _sha256(file_path: str) -> str:
    """Calculate SHA256 hash of file with streaming read."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _effective_config_hash(cfg_paths: List[str]) -> str:
    """Calculate SHA256 of concatenated config file contents."""
    sha256 = hashlib.sha256()
    for path in sorted(cfg_paths):
        if os.path.exists(path):
            with open(path, 'rb') as f:
                sha256.update(f.read())
    return sha256.hexdigest()


def _try_gpg_sign(manifest_path: str, gpg_key: str = None) -> bool:
    """Attempt to GPG sign the manifest file. Returns True if successful."""
    if not gpg_key:
        gpg_key = os.environ.get('GPG_KEY')

    if not gpg_key:
        return False

    sig_path = f"{manifest_path}.sig"
    try:
        result = subprocess.run([
            'gpg', '--detach-sign', '--armor',
            '--local-user', gpg_key,
            '--output', sig_path,
            manifest_path
        ], capture_output=True, text=True, timeout=30)

        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False


def write_manifest(run_dir: str, cfg_paths: List[str]) -> Dict[str, Any]:
    """
    Write run_manifest.json with file hashes, effective config, and metadata.

    Args:
        run_dir: Path to run directory (e.g., 'runs/abc123')
        cfg_paths: List of config file paths to include in manifest

    Returns:
        Dict containing the manifest data
    """
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)

    manifest_path = run_path / "run_manifest.json"

    # Collect file information
    files_info = []
    for cfg_path in cfg_paths:
        if os.path.exists(cfg_path):
            files_info.append({
                "path": cfg_path,
                "sha256": _sha256(cfg_path)
            })

    # Build manifest
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "python_version": platform.python_version(),
        "files": files_info,
        "effective_config_hash": _effective_config_hash(cfg_paths)
    }

    # Write manifest
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Try GPG signing
    _try_gpg_sign(str(manifest_path))

    return manifest