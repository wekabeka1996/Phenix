from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from apps.reference.domains.neocortex.logic.evidence_collection.contracts import (
    EvidenceCollectionBundle,
)
from apps.reference.domains.neocortex.logic.evidence_collection.summary import (
    render_evidence_collection_markdown,
)


@dataclass(frozen=True)
class EvidenceCollectionBundlePaths:
    json_path: Path
    markdown_path: Path


def write_evidence_collection_bundle(
    bundle: EvidenceCollectionBundle,
    output_dir: Path,
    *,
    stem: str = "neocortex_phase8a_1_evidence_collection",
) -> EvidenceCollectionBundlePaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"

    json_text = json.dumps(
        bundle.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    markdown_text = render_evidence_collection_markdown(bundle)

    json_path.write_text(json_text + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_text, encoding="utf-8")

    return EvidenceCollectionBundlePaths(
        json_path=json_path,
        markdown_path=markdown_path,
    )
