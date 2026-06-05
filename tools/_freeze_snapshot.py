#!/usr/bin/env python3
"""Stage A+B: Create frozen snapshot and record identity metadata."""
import time
import json
import os
import shutil
import hashlib
from pathlib import Path
from datetime import datetime

# Use proper Windows paths
LIVE_FILE = Path(r'c:\Users\user\Music\Phenix\logs\trade_lifecycle.jsonl')
BASE_DIR = Path(r'c:\Users\user\Music\Phenix\logs')

# Record live file metadata BEFORE copy
before_size = LIVE_FILE.stat().st_size
before_mtime = datetime.fromtimestamp(LIVE_FILE.stat().st_mtime)
before_lines = sum(1 for _ in LIVE_FILE.open(
    'r', encoding='utf-8', errors='replace'))

print("=== STAGE A: FREEZE ===")
print(f"Live file path: {LIVE_FILE.absolute()}")
print(
    f"Before copy - size: {before_size} bytes, mtime: {before_mtime}, lines: {before_lines}")

# Create frozen copy with timestamp
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
frozen_path = BASE_DIR / f'trade_lifecycle.snapshot.{timestamp}.jsonl'
print(f"\nCopying to: {frozen_path}")

shutil.copy2(LIVE_FILE, frozen_path)
print("Copy completed")

# Record frozen file metadata
frozen_size = frozen_path.stat().st_size
frozen_mtime = datetime.fromtimestamp(frozen_path.stat().st_mtime)
frozen_lines = sum(1 for _ in frozen_path.open(
    'r', encoding='utf-8', errors='replace'))

print(
    f"\nFrozen file - size: {frozen_size} bytes, mtime: {frozen_mtime}, lines: {frozen_lines}")

# Verify copy integrity
if frozen_size == before_size and frozen_lines == before_lines:
    print("✓ Copy integrity verified: size and line count match")
else:
    print(
        f"✗ Copy integrity FAILED: size mismatch ({before_size} vs {frozen_size}) or lines ({before_lines} vs {frozen_lines})")

# Compute SHA256 for frozen copy


def sha256_file(fpath):
    sha = hashlib.sha256()
    with open(fpath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha.update(chunk)
    return sha.hexdigest()


frozen_sha256 = sha256_file(frozen_path)
print(f"Frozen file SHA256: {frozen_sha256}")

# Check if live file changed after copy
time.sleep(1)
after_size = LIVE_FILE.stat().st_size
after_mtime = datetime.fromtimestamp(LIVE_FILE.stat().st_mtime)
after_lines = sum(1 for _ in LIVE_FILE.open(
    'r', encoding='utf-8', errors='replace'))

print(
    f"\nLive file after copy - size: {after_size} bytes, mtime: {after_mtime}, lines: {after_lines}")
if after_size == before_size and after_mtime == before_mtime:
    grew = "no"
    print("✓ Live file unchanged")
else:
    grew = "yes"
    print(
        f"✗ Live file CHANGED: size +{after_size - before_size}, lines +{after_lines - before_lines}")

# Output identity tables
print("\n=== STAGE B: IDENTITY TABLES ===")
print("\n### Table A — Live source identity")
print(f"| absolute_path | {LIVE_FILE.absolute()} |")
print(f"| size_bytes_before_copy | {before_size} |")
print(f"| modified_time_before_copy | {before_mtime} |")
print(f"| line_count_before_copy | {before_lines} |")
print(f"| size_bytes_after_copy | {after_size} |")
print(f"| modified_time_after_copy | {after_mtime} |")
print(f"| line_count_after_copy | {after_lines} |")
print(f"| grew_during_copy | {grew} |")

print("\n### Table B — Frozen snapshot identity")
print(f"| absolute_path | {frozen_path.absolute()} |")
print(f"| size_bytes | {frozen_size} |")
print(f"| modified_time | {frozen_mtime} |")
print(f"| line_count | {frozen_lines} |")
print(f"| sha256 | {frozen_sha256} |")
print(f"| copy_completed | yes |")

print(f"\n>>> FROZEN_SNAPSHOT_PATH={frozen_path}")
