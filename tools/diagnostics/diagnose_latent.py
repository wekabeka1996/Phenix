#!/usr/bin/env python3
"""
Latent-space forensic analysis for Neocortex VAE.

Pipeline:
1) Load config, checkpoint_latest.pt, and normalizer_state.npz.
2) Parse tail lines from logs/features/*.log.
3) Build normalized feature vectors -> VAE encoder mu (z).
4) Build realized labels with RegimeLabeler using horizon_bars.
5) Compute centroid/radius statistics and pairwise centroid distances.
6) Visualize PCA (required if deps available) and optional t-SNE.
7) Write markdown report.
"""

from __future__ import annotations

import argparse
import inspect
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

# Ensure repo root is importable when running as `python tools/diagnose_latent.py`.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.reference.domains.neocortex.config_models import load_config  # noqa: E402
from apps.reference.domains.neocortex.logic.brain.vae import VariationalAutoencoder  # noqa: E402
from apps.reference.domains.neocortex.logic.ingest.normalizer import (  # noqa: E402
    WelfordNormalizer,
    sanitize_symbol,
)
from apps.reference.domains.neocortex.logic.ingest.parser import FeatureParser  # noqa: E402
from apps.reference.domains.neocortex.logic.ingest.parsers.feature_parser import (  # noqa: E402
    parse_feature_log_line,
)
from apps.reference.domains.neocortex.logic.reward.regime_labeler import (  # noqa: E402
    REGIME_NAMES,
    RegimeLabeler,
)


REGIME_IDS = [0, 1, 2, 3, 4]
REGIME_LABELS = {k: v.replace("PREDICT_", "") for k, v in REGIME_NAMES.items()}


def _require_or_exit(mod_name: str, pip_name: Optional[str] = None):
    try:
        return __import__(mod_name)
    except ModuleNotFoundError:
        pkg = pip_name or mod_name
        print(
            f"[ERROR] Missing dependency: {mod_name}. "
            f"Install with: pip install {pkg}",
            file=sys.stderr,
        )
        raise SystemExit(2)


torch = _require_or_exit("torch")
pd = _require_or_exit("pandas")


def _optional_viz_imports():
    missing: List[str] = []
    plt = None
    pca_cls = None
    tsne_cls = None

    try:
        import matplotlib  # type: ignore

        matplotlib.use("Agg")
        import matplotlib.pyplot as _plt  # type: ignore

        plt = _plt
    except ModuleNotFoundError:
        missing.append("matplotlib")

    try:
        from sklearn.decomposition import PCA  # type: ignore
        from sklearn.manifold import TSNE  # type: ignore

        pca_cls = PCA
        tsne_cls = TSNE
    except ModuleNotFoundError:
        missing.append("scikit-learn")

    return plt, pca_cls, tsne_cls, missing


@dataclass
class SampleRecord:
    symbol: str
    raw_features: Dict[str, float]
    model_vec: np.ndarray
    norm_vec: np.ndarray
    z: Optional[np.ndarray] = None


@dataclass
class NormalizerContext:
    scope: str
    global_normalizer: Optional[WelfordNormalizer]
    per_symbol_normalizers: Dict[str, WelfordNormalizer]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose Neocortex latent space separability by realized regime."
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=REPO_ROOT / "apps/reference/domains/neocortex/config",
        help="Directory with neocortex config YAML files.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Path to checkpoint_latest.pt (default from system.checkpoint_dir).",
    )
    parser.add_argument(
        "--normalizer-state",
        type=Path,
        default=None,
        help=(
            "Path to global normalizer_state.npz or directory with "
            "normalizer_states/normalizer_<SYMBOL>.npz."
        ),
    )
    parser.add_argument(
        "--features-dir",
        type=Path,
        default=REPO_ROOT / "logs/features",
        help="Directory containing per-symbol feature logs.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=50000,
        help="Total approximate tail lines to parse across all feature logs.",
    )
    parser.add_argument(
        "--horizon-bars",
        type=int,
        default=None,
        help="Override horizon bars. Default uses oracle config horizon_bars.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2048,
        help="Batch size for VAE encoding.",
    )
    parser.add_argument(
        "--output-dataset",
        type=Path,
        default=REPO_ROOT / "docs/latent_dataset.csv",
        help="Output CSV path for [z_*, regime_label].",
    )
    parser.add_argument(
        "--output-pca",
        type=Path,
        default=REPO_ROOT / "docs/latent_space_pca.png",
        help="Output PNG path for PCA plot.",
    )
    parser.add_argument(
        "--output-tsne",
        type=Path,
        default=REPO_ROOT / "docs/latent_space_tsne.png",
        help="Output PNG path for t-SNE plot.",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=REPO_ROOT / "docs/LATENT_VISION_REPORT.md",
        help="Output markdown report path.",
    )
    parser.add_argument(
        "--max-plot-points",
        type=int,
        default=20000,
        help="Maximum points to plot for PCA scatter.",
    )
    parser.add_argument(
        "--max-tsne-points",
        type=int,
        default=5000,
        help="Maximum points to use for t-SNE.",
    )
    parser.add_argument(
        "--disable-tsne",
        action="store_true",
        help="Skip t-SNE even when sklearn/matplotlib are installed.",
    )
    return parser.parse_args()


def tail_lines(path: Path, n_lines: int, encoding: str = "utf-8") -> List[str]:
    """
    Read the last n_lines from a text file efficiently by scanning backward.
    """
    if n_lines <= 0:
        return []
    if not path.exists():
        return []

    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        end_pos = f.tell()
        block_size = 1024 * 64
        data = b""
        lines: List[bytes] = []

        while end_pos > 0 and len(lines) <= n_lines:
            read_size = min(block_size, end_pos)
            end_pos -= read_size
            f.seek(end_pos)
            data = f.read(read_size) + data
            lines = data.splitlines()

    tail = lines[-n_lines:]
    return [ln.decode(encoding, errors="replace") for ln in tail]


def resolve_checkpoint_path(config, override: Optional[Path]) -> Path:
    if override is not None:
        ckpt = override.resolve()
        if ckpt.exists():
            return ckpt
        raise FileNotFoundError(f"Checkpoint not found: {ckpt}")

    candidate = config.system.checkpoint_dir / "checkpoint_latest.pt"
    if candidate.exists():
        return candidate.resolve()

    # Fallback scan under data/checkpoints.
    fallback = (REPO_ROOT / "data/checkpoints/checkpoint_latest.pt").resolve()
    if fallback.exists():
        return fallback

    if candidate.resolve() == fallback.resolve():
        tried = f"{candidate.resolve()}"
    else:
        tried = f"{candidate.resolve()} and {fallback.resolve()}"

    raise FileNotFoundError(
        "checkpoint_latest.pt not found. "
        f"Tried: {tried}"
    )


def _load_global_normalizer(path: Path, dim: int) -> WelfordNormalizer:
    normalizer = WelfordNormalizer(dim=dim, eps=1e-8)
    loaded = normalizer.load_state(path)
    if not loaded:
        raise FileNotFoundError(f"Global normalizer not found: {path}")
    return normalizer


def _load_per_symbol_normalizers(states_dir: Path, dim: int) -> Dict[str, WelfordNormalizer]:
    per_symbol: Dict[str, WelfordNormalizer] = {}
    for state_path in sorted(states_dir.glob("normalizer_*.npz")):
        key = sanitize_symbol(state_path.stem.replace("normalizer_", "", 1))
        normalizer = WelfordNormalizer(dim=dim, eps=1e-8)
        if normalizer.load_state(state_path):
            per_symbol[key] = normalizer
    return per_symbol


def resolve_normalizer_context(config, override: Optional[Path]) -> NormalizerContext:
    configured_scope = str(
        getattr(config.ingest, "normalization_scope", "global")).lower()
    dim = len(config.ingest.feature_list)

    legacy_global = (config.system.data_dir / "normalizer_state.npz").resolve()
    per_symbol_dir = (config.system.data_dir / "normalizer_states").resolve()

    if override is not None:
        target = override.resolve()
        if not target.exists():
            raise FileNotFoundError(f"Normalizer state not found: {target}")
        if target.is_file():
            global_normalizer = _load_global_normalizer(target, dim=dim)
            return NormalizerContext(
                scope="global",
                global_normalizer=global_normalizer,
                per_symbol_normalizers={},
            )
        per_symbol = _load_per_symbol_normalizers(target, dim=dim)
        if not per_symbol:
            raise FileNotFoundError(
                f"No per-symbol normalizer states found in directory: {target}"
            )
        return NormalizerContext(
            scope="per_symbol",
            global_normalizer=None,
            per_symbol_normalizers=per_symbol,
        )

    if configured_scope == "per_symbol":
        per_symbol = _load_per_symbol_normalizers(per_symbol_dir, dim=dim)
        if per_symbol:
            return NormalizerContext(
                scope="per_symbol",
                global_normalizer=None,
                per_symbol_normalizers=per_symbol,
            )
        if legacy_global.exists():
            print(
                "[WARN] normalization_scope=per_symbol but no symbol states found. "
                "Falling back to legacy global normalizer_state.npz.",
                flush=True,
            )
            global_normalizer = _load_global_normalizer(legacy_global, dim=dim)
            return NormalizerContext(
                scope="global",
                global_normalizer=global_normalizer,
                per_symbol_normalizers={},
            )
        raise FileNotFoundError(
            "No normalizer state found. "
            f"Tried per-symbol dir: {per_symbol_dir} and legacy global: {legacy_global}"
        )

    if legacy_global.exists():
        global_normalizer = _load_global_normalizer(legacy_global, dim=dim)
        return NormalizerContext(
            scope="global",
            global_normalizer=global_normalizer,
            per_symbol_normalizers={},
        )

    per_symbol = _load_per_symbol_normalizers(per_symbol_dir, dim=dim)
    if per_symbol:
        print(
            "[WARN] normalization_scope=global but global state is missing. "
            "Using available per-symbol normalizer states.",
            flush=True,
        )
        return NormalizerContext(
            scope="per_symbol",
            global_normalizer=None,
            per_symbol_normalizers=per_symbol,
        )

    raise FileNotFoundError(
        "No normalizer state found. "
        f"Tried global: {legacy_global} and per-symbol dir: {per_symbol_dir}"
    )


def allocate_tail_budgets(files: Sequence[Path], max_lines: int, horizon: int) -> Dict[Path, int]:
    if not files:
        return {}
    base = max_lines // len(files)
    rem = max_lines % len(files)
    budgets: Dict[Path, int] = {}
    for idx, path in enumerate(files):
        budgets[path] = base + (1 if idx < rem else 0) + horizon
    return budgets


def _normalize_sample_vector(
    symbol: str,
    model_vec: np.ndarray,
    normalizers: NormalizerContext,
    warned_missing_symbols: set[str],
) -> Optional[np.ndarray]:
    vec = np.asarray(model_vec, dtype=np.float32).reshape(-1)
    if normalizers.scope == "per_symbol":
        key = sanitize_symbol(symbol)
        symbol_normalizer = normalizers.per_symbol_normalizers.get(key)
        if symbol_normalizer is None:
            if key not in warned_missing_symbols:
                warned_missing_symbols.add(key)
                print(
                    f"[WARN] Missing per-symbol normalizer state for {key}; "
                    "skipping samples for this symbol.",
                    flush=True,
                )
            return None
        return symbol_normalizer.normalize(vec)
    if normalizers.global_normalizer is None:
        return vec
    return normalizers.global_normalizer.normalize(vec)


def build_symbol_samples(
    feature_files: Sequence[Path],
    budgets: Dict[Path, int],
    parser: FeatureParser,
    normalizers: NormalizerContext,
) -> Dict[str, List[SampleRecord]]:
    symbol_samples: Dict[str, List[SampleRecord]] = {}
    total_lines = 0
    total_parsed = 0
    warned_missing_symbols: set[str] = set()

    for fp in feature_files:
        symbol = fp.stem.upper()
        lines = tail_lines(fp, budgets[fp])
        total_lines += len(lines)
        records: List[SampleRecord] = []

        for ln in lines:
            entry = parse_feature_log_line(ln, symbol=symbol)
            if entry is None:
                continue

            # Apply the same parser transforms used by online ingest:
            # delta_price pct, price mode, finite/clip sanitation.
            try:
                obs = parser.parse(
                    {
                        "timestamp": float(entry.timestamp),
                        "symbol": symbol,
                        "features": entry.features,
                    }
                )
            except Exception:
                continue

            model_vec = obs.features_vector.astype(np.float32, copy=False)
            norm_vec = _normalize_sample_vector(
                symbol=symbol,
                model_vec=model_vec,
                normalizers=normalizers,
                warned_missing_symbols=warned_missing_symbols,
            )
            if norm_vec is None:
                continue

            records.append(
                SampleRecord(
                    symbol=symbol,
                    raw_features=entry.features,
                    model_vec=model_vec,
                    norm_vec=norm_vec,
                )
            )
        total_parsed += len(records)
        symbol_samples[symbol] = records
        print(
            f"[INFO] {symbol}: tail_lines={len(lines):,} parsed={len(records):,}",
            flush=True,
        )

    print(
        f"[INFO] Parsed feature lines: {total_parsed:,} "
        f"from tailed lines: {total_lines:,}",
        flush=True,
    )
    return symbol_samples


def encode_symbol_samples(
    symbol_samples: Dict[str, List[SampleRecord]],
    vae: VariationalAutoencoder,
    device: str,
    batch_size: int,
) -> int:
    total = 0
    vae.eval()
    with torch.no_grad():
        for symbol, records in symbol_samples.items():
            if not records:
                continue
            arr = np.stack([r.norm_vec for r in records]
                           ).astype(np.float32, copy=False)
            all_mu = []
            for i in range(0, arr.shape[0], batch_size):
                batch = torch.from_numpy(
                    arr[i: i + batch_size]).to(device=device)
                mu, _ = vae.encode(batch)
                all_mu.append(mu.detach().cpu().numpy())
            mu_all = np.concatenate(all_mu, axis=0)
            for idx, rec in enumerate(records):
                rec.z = mu_all[idx].astype(np.float32, copy=False)
            total += len(records)
            print(
                f"[INFO] Encoded {symbol}: {len(records):,} vectors", flush=True)
    return total


def settle_with_horizon(
    symbol_samples: Dict[str, List[SampleRecord]],
    labeler: RegimeLabeler,
    horizon: int,
) -> "pd.DataFrame":
    rows: List[Dict[str, object]] = []
    latent_dim = None

    for symbol, records in symbol_samples.items():
        if len(records) <= horizon:
            continue
        for idx in range(len(records) - horizon):
            cur = records[idx]
            fut = records[idx + horizon]
            if cur.z is None:
                continue

            regime_id = int(
                labeler.compute_realized_regime(
                    cur.raw_features, fut.raw_features)
            )
            regime_name = REGIME_LABELS.get(regime_id, f"UNK_{regime_id}")
            z = cur.z
            if latent_dim is None:
                latent_dim = int(z.shape[0])

            row = {
                "symbol": symbol,
                "row_index": idx,
                "regime_id": regime_id,
                "regime_label": regime_name,
            }
            for j in range(z.shape[0]):
                row[f"z_{j}"] = float(z[j])
            rows.append(row)

    if not rows:
        raise RuntimeError(
            "No settled samples produced. "
            "Increase --max-lines or check horizon/features logs."
        )
    df = pd.DataFrame(rows)
    return df


def compute_centroid_stats(
    df: "pd.DataFrame",
    latent_cols: Sequence[str],
) -> Tuple[Dict[int, np.ndarray], Dict[int, Dict[str, float]], np.ndarray]:
    centroids: Dict[int, np.ndarray] = {}
    cluster_stats: Dict[int, Dict[str, float]] = {}
    dist_matrix = np.full((len(REGIME_IDS), len(
        REGIME_IDS)), np.nan, dtype=np.float64)

    for rid in REGIME_IDS:
        subset = df[df["regime_id"] == rid]
        if subset.empty:
            continue
        arr = subset.loc[:, latent_cols].to_numpy(dtype=np.float32, copy=True)
        centroid = arr.mean(axis=0)
        radii = np.linalg.norm(arr - centroid[None, :], axis=1)
        centroids[rid] = centroid
        cluster_stats[rid] = {
            "count": float(arr.shape[0]),
            "mean_radius": float(np.mean(radii)),
            "std_radius": float(np.std(radii)),
            "rms_radius": float(np.sqrt(np.mean(np.square(radii)))),
        }

    for i in REGIME_IDS:
        for j in REGIME_IDS:
            if i not in centroids or j not in centroids:
                continue
            dist_matrix[i, j] = float(
                np.linalg.norm(centroids[i] - centroids[j]))

    return centroids, cluster_stats, dist_matrix


def regime_counts(df: "pd.DataFrame") -> Dict[int, int]:
    counts = df["regime_id"].value_counts().to_dict()
    return {rid: int(counts.get(rid, 0)) for rid in REGIME_IDS}


def sample_indices(n: int, max_points: int, seed: int = 42) -> np.ndarray:
    if n <= max_points:
        return np.arange(n, dtype=np.int64)
    rng = np.random.default_rng(seed)
    idx = rng.choice(n, size=max_points, replace=False)
    idx.sort()
    return idx.astype(np.int64, copy=False)


def _regime_color(rid: int) -> str:
    palette = {
        0: "#1f77b4",  # blue
        1: "#d62728",  # red
        2: "#2ca02c",  # green
        3: "#ff7f0e",  # orange
        4: "#9467bd",  # violet
    }
    return palette.get(rid, "#7f7f7f")


def save_scatter(
    plt,
    coords: np.ndarray,
    labels: np.ndarray,
    out_path: Path,
    title: str,
    centroids_2d: Optional[Dict[int, np.ndarray]] = None,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(11, 8))
    for rid in REGIME_IDS:
        mask = labels == rid
        if not np.any(mask):
            continue
        name = REGIME_LABELS.get(rid, f"UNK_{rid}")
        plt.scatter(
            coords[mask, 0],
            coords[mask, 1],
            s=8,
            alpha=0.35,
            c=_regime_color(rid),
            label=f"{name} (n={int(mask.sum())})",
            edgecolors="none",
        )

    if centroids_2d:
        for rid, c2 in centroids_2d.items():
            plt.scatter(
                [c2[0]],
                [c2[1]],
                c="black",
                s=180,
                marker="X",
                linewidths=0.7,
            )

    plt.title(title)
    plt.xlabel("Component 1")
    plt.ylabel("Component 2")
    plt.grid(True, alpha=0.25)
    plt.legend(loc="best", fontsize=8, framealpha=0.85)
    plt.tight_layout()
    plt.savefig(out_path, dpi=180)
    plt.close()


def distance_matrix_markdown(dist_matrix: np.ndarray) -> str:
    header = "| Regime | " + \
        " | ".join(REGIME_LABELS[r] for r in REGIME_IDS) + " |"
    sep = "|" + "---|" * (len(REGIME_IDS) + 1)
    lines = [header, sep]
    for i in REGIME_IDS:
        row = [REGIME_LABELS[i]]
        for j in REGIME_IDS:
            v = dist_matrix[i, j]
            row.append("NA" if not np.isfinite(v) else f"{v:.4f}")
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def cluster_stats_markdown(cluster_stats: Dict[int, Dict[str, float]]) -> str:
    lines = [
        "| Regime | Count | Mean Radius | Std Radius | RMS Radius |",
        "|---|---:|---:|---:|---:|",
    ]
    for rid in REGIME_IDS:
        stats = cluster_stats.get(rid)
        if stats is None:
            lines.append(f"| {REGIME_LABELS[rid]} | 0 | NA | NA | NA |")
            continue
        lines.append(
            f"| {REGIME_LABELS[rid]} | {int(stats['count'])} | "
            f"{stats['mean_radius']:.4f} | {stats['std_radius']:.4f} | {stats['rms_radius']:.4f} |"
        )
    return "\n".join(lines)


def counts_markdown(counts: Dict[int, int], total: int) -> str:
    lines = ["| Regime | Count | Share |", "|---|---:|---:|"]
    for rid in REGIME_IDS:
        cnt = counts[rid]
        share = (100.0 * cnt / total) if total else 0.0
        lines.append(f"| {REGIME_LABELS[rid]} | {cnt:,} | {share:.2f}% |")
    return "\n".join(lines)


def decide_verdict(
    counts: Dict[int, int],
    mr_hv_distance: float,
    mr_rms_radius: float,
) -> Tuple[str, str, float]:
    present = sum(1 for rid in REGIME_IDS if counts.get(rid, 0) > 0)
    ratio = mr_hv_distance / max(mr_rms_radius, 1e-12)
    if present < 4:
        verdict = "VAE is blind (insufficient regime coverage in settled samples)."
        confidence = "high"
    elif ratio >= 2.0:
        verdict = "VAE can see regimes (MR vs HIGH_VOL separation is clear)."
        confidence = "high"
    elif ratio >= 1.2:
        verdict = "VAE partially sees regimes (moderate separation, overlap remains)."
        confidence = "medium"
    else:
        verdict = "VAE is likely blind (MR vs HIGH_VOL overlap is too high)."
        confidence = "high"
    return verdict, confidence, ratio


def write_report(
    out_path: Path,
    dataset_path: Path,
    pca_path: Optional[Path],
    tsne_path: Optional[Path],
    normalization_scope: str,
    price_feature_mode: str,
    delta_price_mode: str,
    lines_requested: int,
    horizon: int,
    total_rows: int,
    counts: Dict[int, int],
    cluster_stats: Dict[int, Dict[str, float]],
    dist_matrix: np.ndarray,
    mr_hv_distance: float,
    mr_rms_radius: float,
    verdict: str,
    confidence: str,
    ratio: float,
    viz_missing: Sequence[str],
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mr_overlap = "YES" if mr_hv_distance <= mr_rms_radius else "NO"

    lines: List[str] = []
    lines.append("# Latent Vision Report")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- Verdict: **{verdict}**")
    lines.append(f"- Confidence: **{confidence}**")
    lines.append(
        f"- Crucial check (MR vs HIGH_VOL): distance={mr_hv_distance:.4f}, "
        f"MR RMS radius={mr_rms_radius:.4f}, ratio={ratio:.3f}, overlap_risk={mr_overlap}"
    )
    lines.append("")
    lines.append("## Data Scope")
    lines.append("")
    lines.append(
        f"- Requested tail lines across `logs/features/*.log`: **{lines_requested:,}**")
    lines.append(f"- Labeling horizon (`horizon_bars`): **{horizon}**")
    lines.append(
        f"- Normalization scope used for encoding: **{normalization_scope}**")
    lines.append(f"- Price feature mode: **{price_feature_mode}**")
    lines.append(f"- Delta price mode: **{delta_price_mode}**")
    lines.append(f"- Settled latent samples: **{total_rows:,}**")
    lines.append(f"- Dataset CSV: `{dataset_path.as_posix()}`")
    lines.append("")
    lines.append("### Regime Distribution")
    lines.append("")
    lines.append(counts_markdown(counts, total_rows))
    lines.append("")
    lines.append("## Cluster Radius Stats")
    lines.append("")
    lines.append(cluster_stats_markdown(cluster_stats))
    lines.append("")
    lines.append("## Centroid Distance Matrix (Euclidean)")
    lines.append("")
    lines.append(distance_matrix_markdown(dist_matrix))
    lines.append("")
    lines.append("## Crucial Distance Test")
    lines.append("")
    lines.append(
        "- Question: Is `distance(centroid(MR), centroid(HIGH_VOLATILITY))` "
        "significantly larger than within-MR cluster variance?"
    )
    lines.append(
        f"- Computed: `distance={mr_hv_distance:.4f}`, "
        f"`mr_rms_radius={mr_rms_radius:.4f}`, `distance/radius={ratio:.3f}`"
    )
    lines.append(
        f"- Result: **{'PASS (separated)' if ratio >= 1.2 else 'FAIL (overlap too high)'}**"
    )
    lines.append("")
    lines.append("## Visual Diagnostics")
    lines.append("")
    if pca_path and pca_path.exists():
        lines.append(f"![Latent PCA]({pca_path.as_posix()})")
    else:
        lines.append("- PCA image not generated.")
    lines.append("")
    if tsne_path and tsne_path.exists():
        lines.append(f"![Latent t-SNE]({tsne_path.as_posix()})")
    else:
        lines.append("- t-SNE image not generated.")
    lines.append("")
    if viz_missing:
        lines.append("## Missing Visualization Dependencies")
        lines.append("")
        lines.append(
            "- Missing packages: `" + "`, `".join(viz_missing) + "`"
        )
        lines.append(
            "- Install command: `pip install scikit-learn matplotlib`")
        lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    print("[INFO] Starting latent-space diagnosis...", flush=True)

    config = load_config(args.config_dir.resolve())
    if config.oracle is None:
        print(
            "[ERROR] Oracle config is missing. "
            "Expected config/regime_oracle_reward.yaml with horizon + thresholds.",
            file=sys.stderr,
        )
        return 2

    horizon = int(
        args.horizon_bars if args.horizon_bars is not None else config.oracle.horizon_bars)
    if horizon < 1:
        print(f"[ERROR] Invalid horizon_bars={horizon}", file=sys.stderr)
        return 2

    try:
        checkpoint_path = resolve_checkpoint_path(config, args.checkpoint)
        normalizers = resolve_normalizer_context(config, args.normalizer_state)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        print(
            "[HINT] Ensure checkpoint and normalizer states exist. "
            "If needed, pass --checkpoint and --normalizer-state explicitly.",
            file=sys.stderr,
        )
        return 2

    print(f"[INFO] Checkpoint: {checkpoint_path}", flush=True)
    if normalizers.scope == "per_symbol":
        loaded_symbols = sorted(normalizers.per_symbol_normalizers.keys())
        print(
            f"[INFO] Normalizer scope: per_symbol ({len(loaded_symbols)} states loaded)",
            flush=True,
        )
        if loaded_symbols:
            print(
                "[INFO] Loaded symbol states: " + ", ".join(loaded_symbols),
                flush=True,
            )
    else:
        count = normalizers.global_normalizer.count if normalizers.global_normalizer else 0
        print(f"[INFO] Normalizer scope: global (count={count})", flush=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    vae = VariationalAutoencoder(config.neuro.vae).to(device)
    checkpoint = torch.load(checkpoint_path, map_location=device)
    if "vae_state" not in checkpoint:
        print("[ERROR] Checkpoint missing key 'vae_state'.", file=sys.stderr)
        return 2
    vae.load_state_dict(checkpoint["vae_state"], strict=True)
    vae.eval()
    print(f"[INFO] Loaded VAE on device={device}", flush=True)

    feature_files = sorted(args.features_dir.resolve().glob("*.log"))
    if not feature_files:
        print(
            f"[ERROR] No feature logs found in {args.features_dir}", file=sys.stderr)
        return 2
    budgets = allocate_tail_budgets(
        feature_files, int(args.max_lines), horizon)
    print(
        "[INFO] Feature files: "
        + ", ".join(f"{p.stem}:{budgets[p]:,}" for p in feature_files),
        flush=True,
    )

    ingest_parser = FeatureParser(config.ingest)
    symbol_samples = build_symbol_samples(
        feature_files=feature_files,
        budgets=budgets,
        parser=ingest_parser,
        normalizers=normalizers,
    )

    encoded_total = encode_symbol_samples(
        symbol_samples=symbol_samples,
        vae=vae,
        device=device,
        batch_size=int(args.batch_size),
    )
    print(f"[INFO] Total encoded vectors: {encoded_total:,}", flush=True)

    labeler = RegimeLabeler.from_config(config.oracle)
    df = settle_with_horizon(
        symbol_samples=symbol_samples, labeler=labeler, horizon=horizon)

    latent_cols = [c for c in df.columns if c.startswith("z_")]
    if not latent_cols:
        print("[ERROR] No latent columns produced.", file=sys.stderr)
        return 2

    args.output_dataset.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output_dataset, index=False)
    print(
        f"[INFO] Saved latent dataset: {args.output_dataset} ({len(df):,} rows)", flush=True)

    counts = regime_counts(df)
    centroids, cluster_stats, dist_matrix = compute_centroid_stats(
        df, latent_cols=latent_cols)
    mr_hv_distance = float(dist_matrix[2, 3]) if np.isfinite(
        dist_matrix[2, 3]) else float("nan")
    mr_rms_radius = float(cluster_stats.get(
        2, {}).get("rms_radius", float("nan")))
    verdict, confidence, ratio = decide_verdict(
        counts=counts,
        mr_hv_distance=mr_hv_distance if np.isfinite(mr_hv_distance) else 0.0,
        mr_rms_radius=mr_rms_radius if np.isfinite(mr_rms_radius) else 0.0,
    )

    print("[INFO] Regime counts:")
    for rid in REGIME_IDS:
        total = len(df)
        pct = 100.0 * counts[rid] / total if total else 0.0
        print(f"  - {REGIME_LABELS[rid]}: {counts[rid]:,} ({pct:.2f}%)")

    print(
        "[INFO] Crucial test: "
        f"distance(MR,HIGH_VOL)={mr_hv_distance:.4f} "
        f"vs MR_rms_radius={mr_rms_radius:.4f} "
        f"(ratio={ratio:.3f})"
    )
    print(f"[INFO] Verdict: {verdict} (confidence={confidence})")

    # Visualization (graceful fallback if deps missing)
    plt, pca_cls, tsne_cls, viz_missing = _optional_viz_imports()
    pca_written = False
    tsne_written = False

    z_all = df.loc[:, latent_cols].to_numpy(dtype=np.float32, copy=True)
    y_all = df["regime_id"].to_numpy(dtype=np.int32, copy=True)

    if plt is not None and pca_cls is not None:
        pca = pca_cls(n_components=2, random_state=42)
        coords = pca.fit_transform(z_all)
        idx = sample_indices(coords.shape[0], int(
            args.max_plot_points), seed=42)

        centroids_2d: Dict[int, np.ndarray] = {}
        for rid, c in centroids.items():
            centroids_2d[rid] = pca.transform(c.reshape(1, -1))[0]

        save_scatter(
            plt=plt,
            coords=coords[idx],
            labels=y_all[idx],
            out_path=args.output_pca.resolve(),
            title=(
                "Neocortex Latent Space (PCA)"
                f" | explained={100.0*np.sum(pca.explained_variance_ratio_):.2f}%"
            ),
            centroids_2d=centroids_2d,
        )
        pca_written = True
        print(f"[INFO] PCA plot saved: {args.output_pca}", flush=True)

        if not args.disable_tsne and tsne_cls is not None:
            idx_tsne = sample_indices(
                z_all.shape[0], int(args.max_tsne_points), seed=123)
            z_tsne = z_all[idx_tsne]
            y_tsne = y_all[idx_tsne]
            if z_tsne.shape[0] >= 50:
                perplexity = min(30.0, max(5.0, (z_tsne.shape[0] - 1) / 3.0))
                tsne_kwargs = {
                    "n_components": 2,
                    "random_state": 42,
                    "init": "random",
                    "learning_rate": "auto",
                    "perplexity": perplexity,
                }
                # sklearn compatibility: older versions use n_iter, newer use max_iter.
                tsne_sig = inspect.signature(tsne_cls.__init__)
                if "max_iter" in tsne_sig.parameters:
                    tsne_kwargs["max_iter"] = 1000
                else:
                    tsne_kwargs["n_iter"] = 1000

                tsne = tsne_cls(**tsne_kwargs)
                coords_tsne = tsne.fit_transform(z_tsne)

                centroids_tsne: Dict[int, np.ndarray] = {}
                for rid in REGIME_IDS:
                    mask = y_tsne == rid
                    if np.any(mask):
                        centroids_tsne[rid] = coords_tsne[mask].mean(axis=0)

                save_scatter(
                    plt=plt,
                    coords=coords_tsne,
                    labels=y_tsne,
                    out_path=args.output_tsne.resolve(),
                    title="Neocortex Latent Space (t-SNE)",
                    centroids_2d=centroids_tsne,
                )
                tsne_written = True
                print(
                    f"[INFO] t-SNE plot saved: {args.output_tsne}", flush=True)
            else:
                print(
                    "[WARN] t-SNE skipped: not enough samples after subsampling.", flush=True)
    else:
        print(
            "[WARN] Visualization skipped due to missing dependencies. "
            "Install with: pip install scikit-learn matplotlib",
            flush=True,
        )

    write_report(
        out_path=args.output_report.resolve(),
        dataset_path=args.output_dataset.resolve(),
        pca_path=args.output_pca.resolve() if pca_written else None,
        tsne_path=args.output_tsne.resolve() if tsne_written else None,
        normalization_scope=normalizers.scope,
        price_feature_mode=str(
            getattr(config.ingest, "price_feature_mode", "raw")),
        delta_price_mode=str(
            getattr(config.ingest, "delta_price_mode", "raw")),
        lines_requested=int(args.max_lines),
        horizon=horizon,
        total_rows=int(len(df)),
        counts=counts,
        cluster_stats=cluster_stats,
        dist_matrix=dist_matrix,
        mr_hv_distance=mr_hv_distance if np.isfinite(mr_hv_distance) else 0.0,
        mr_rms_radius=mr_rms_radius if np.isfinite(mr_rms_radius) else 0.0,
        verdict=verdict,
        confidence=confidence,
        ratio=ratio,
        viz_missing=viz_missing,
    )
    print(f"[INFO] Report saved: {args.output_report}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
