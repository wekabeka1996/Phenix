#!/usr/bin/env python3
"""Phase 4: Freeze recorder extension with manifests."""

import json
from pathlib import Path
import hashlib
import shutil
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)

FROZEN_DIR = Path('logs/frozen/nrr062_fresh_capture_20260507_103909')
WORKSPACE_RECORDER = Path('data/recorder')

# Extension directory name with timestamp
EXTENSION_NAME = f"recorder_extension_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
EXTENSION_PATH = FROZEN_DIR / EXTENSION_NAME
DATA_DIR = EXTENSION_PATH / 'data'


def compute_sha256(file_path):
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def freeze_extension():
    """Freeze workspace recorder files as frozen extension."""

    logging.info("=" * 80)
    logging.info("PHASE 4: FREEZE RECORDER EXTENSION")
    logging.info("=" * 80)

    # Create extension directory
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.info(f"Created {EXTENSION_PATH}")

    # Load case requirements for symbols needed
    req_file = FROZEN_DIR / 'case_time_requirements_PROMPT11.json'
    with open(req_file) as f:
        case_reqs = json.load(f)['case_time_requirements']

    symbols = case_reqs['symbols']

    # Copy May 6 and May 7 recorder files (needed for full coverage)
    manifest_entries = []
    total_size = 0
    files_copied = 0

    for date in ['2026-05-06', '2026-05-07']:
        date_src = WORKSPACE_RECORDER / date
        if not date_src.exists():
            logging.warning(f"Source date directory not found: {date_src}")
            continue

        date_dst = DATA_DIR / date
        date_dst.mkdir(parents=True, exist_ok=True)

        logging.info(f"\nCopying {date} files...")

        # Copy only needed symbols and timeframes
        for symbol in symbols:
            for tf in [180, 300, 900]:
                src_file = date_src / f"{symbol}_{tf}.csv"
                if not src_file.exists():
                    continue

                dst_file = date_dst / f"{symbol}_{tf}.csv"
                shutil.copy2(src_file, dst_file)

                # Compute manifest entry
                size_bytes = dst_file.stat().st_size
                mtime = dst_file.stat().st_mtime
                sha256 = compute_sha256(dst_file)

                manifest_entries.append({
                    'source_path': str(src_file),
                    'destination_path': str(dst_file.relative_to(EXTENSION_PATH)),
                    'symbol': symbol,
                    'timeframe_sec': tf,
                    'size_bytes': size_bytes,
                    'mtime_epoch': mtime,
                    'sha256': sha256,
                    'file_exists': True,
                    'copied_successfully': True,
                    'evidence_role': 'recorder_market_data_extension',
                    'notes': f'{symbol} {tf}s timeframe for {date}',
                })

                total_size += size_bytes
                files_copied += 1
                logging.info(f"  ✓ {src_file.name} ({size_bytes:,} bytes)")

    # Write manifest
    manifest = {
        'extension_name': EXTENSION_NAME,
        'frozen_root': str(FROZEN_DIR),
        'created_utc': datetime.utcnow().isoformat(),
        'source': 'workspace_current_recorder',
        'purpose': 'Extend frozen recorder coverage to include May 7 data for horizon replay',
        'case_requirements': case_reqs,
        'files_copied': files_copied,
        'total_size_bytes': total_size,
        'symbols': symbols,
        'dates_included': ['2026-05-06', '2026-05-07'],
        'timeframes_included': [180, 300, 900],
        'entries': manifest_entries,
        'manifest_version': '1.0',
    }

    manifest_path = EXTENSION_PATH / 'MANIFEST_RECORDER_EXTENSION.json'
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    logging.info("\n" + "=" * 80)
    logging.info("EXTENSION FROZEN")
    logging.info("=" * 80)
    logging.info(f"Extension path: {EXTENSION_PATH}")
    logging.info(f"Files copied: {files_copied}")
    logging.info(f"Total size: {total_size:,} bytes")
    logging.info(f"Manifest: {manifest_path}")

    return EXTENSION_PATH, manifest_path, manifest


if __name__ == '__main__':
    ext_path, man_path, man = freeze_extension()
