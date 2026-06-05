from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION as poc03


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH = REPO_ROOT / "SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json"
DEFAULT_SAF_PATH = REPO_ROOT / "aurora_real_logs_v02.saf.jsonl"
DEFAULT_POC03_REPORT_PATH = REPO_ROOT / "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md"
DEFAULT_POC02_REPORT_PATH = REPO_ROOT / "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md"
DEFAULT_REPORT_PATH = REPO_ROOT / "SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION_REPORT.md"

CONSERVATIVE_OPPORTUNITY_FILL_FACTOR = 0.50
CONSERVATIVE_RISK_FILL_FACTOR = 1.00
CONSERVATIVE_EXECUTION_HAIRCUT_BPS = 2.0
DEFAULT_FEE_SLIPPAGE_BUFFER_BPS = 10.0


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


@dataclass(slots=True)
class SimulatedAtom:
    atom_id: str
    canonical_outcome_code: str
    original_outcome_code: str
    event_ts_ms: int
    post_move_bps: float | None
    future_price: float | None
    reference_price: float | None
    opportunity_bps: float
    loss_risk_bps: float


@dataclass(slots=True)
class SimulationResult:
    context_id: str
    verdict: str
    validation_atom_count: int
    policy_too_strict_count: int
    policy_protected_count: int
    opportunity_gain_raw_bps: float
    added_loss_risk_raw_bps: float
    fee_slippage_buffer_bps: float
    conservative_opportunity_gain_bps: float
    conservative_added_loss_risk_bps: float
    conservative_net_impact_bps: float
    fill_uncertainty: str
    execution_uncertainty: str
    simulated_atoms: list[SimulatedAtom]
    sensitivity_bands: dict[str, dict[str, float]]
    residual_risks: list[str]


def load_manifest(path: Path) -> dict[str, list[dict[str, Any]]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _context_key_tuple(context_id: str) -> tuple[str, str, str, str, str]:
    parts = context_id.split("|")
    if len(parts) != 5:
        raise ValueError(f"Invalid context_id: {context_id}")
    return tuple(parts)  # type: ignore[return-value]


def _load_validation_atoms_by_context(saf_path: Path) -> dict[tuple[str, str, str, str, str], list[poc03.ValidationAtom]]:
    atoms = poc03.load_atoms(saf_path)
    splits = poc03.split_atoms_by_context(atoms)
    return {split.context_key: list(split.validation_atoms) for split in splits}


def _raw_contract_for_atom(saf_path: Path, atom_id: str) -> dict[str, Any] | None:
    with saf_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if payload.get("atom_id") == atom_id:
                return payload
    return None


def _extract_post_move(atom_payload: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    outcome_snapshot = atom_payload.get("outcome_snapshot") or {}
    raw_contract = atom_payload.get("raw_contract") or {}
    post_move_bps = _safe_float(outcome_snapshot.get("post_move_bps"))
    t30 = outcome_snapshot.get("post_move_horizons", {}).get("T+30m", {})
    future_price = _safe_float(t30.get("future_price"))
    reference_price = _safe_float(raw_contract.get("reference_price")) or _safe_float(raw_contract.get("entry_price"))
    return post_move_bps, future_price, reference_price


def simulate_policy_too_strict_candidate(
    *,
    context_record: dict[str, Any],
    validation_atoms: Sequence[poc03.ValidationAtom],
    saf_path: Path,
    fee_slippage_buffer_bps: float = DEFAULT_FEE_SLIPPAGE_BUFFER_BPS,
) -> SimulationResult | None:
    simulated_atoms: list[SimulatedAtom] = []
    missing_price_rows = 0
    for atom in validation_atoms:
        payload = _raw_contract_for_atom(saf_path, atom.atom_id)
        if payload is None:
            missing_price_rows += 1
            continue
        post_move_bps, future_price, reference_price = _extract_post_move(payload)
        if post_move_bps is None or reference_price is None:
            missing_price_rows += 1
            continue
        opportunity_bps = max(post_move_bps, 0.0) if atom.canonical_outcome_code == "POLICY_TOO_STRICT" else 0.0
        loss_risk_bps = abs(min(post_move_bps, 0.0)) if atom.canonical_outcome_code == "POLICY_PROTECTED" else 0.0
        simulated_atoms.append(
            SimulatedAtom(
                atom_id=atom.atom_id,
                canonical_outcome_code=atom.canonical_outcome_code,
                original_outcome_code=atom.original_outcome_code,
                event_ts_ms=atom.event_ts_ms,
                post_move_bps=post_move_bps,
                future_price=future_price,
                reference_price=reference_price,
                opportunity_bps=opportunity_bps,
                loss_risk_bps=loss_risk_bps,
            )
        )

    if not simulated_atoms:
        return None

    opportunity_gain_raw_bps = sum(item.opportunity_bps for item in simulated_atoms)
    added_loss_risk_raw_bps = sum(item.loss_risk_bps for item in simulated_atoms)
    attempted_signals = len(simulated_atoms)
    conservative_opportunity_gain_bps = opportunity_gain_raw_bps * CONSERVATIVE_OPPORTUNITY_FILL_FACTOR
    conservative_added_loss_risk_bps = added_loss_risk_raw_bps * CONSERVATIVE_RISK_FILL_FACTOR
    total_fee_slippage_buffer_bps = attempted_signals * fee_slippage_buffer_bps
    execution_haircut_total_bps = attempted_signals * CONSERVATIVE_EXECUTION_HAIRCUT_BPS
    conservative_net_impact_bps = (
        conservative_opportunity_gain_bps
        - conservative_added_loss_risk_bps
        - total_fee_slippage_buffer_bps
        - execution_haircut_total_bps
    )

    def _band(op_fill: float, risk_fill: float, execution_haircut_bps: float) -> dict[str, float]:
        opp = opportunity_gain_raw_bps * op_fill
        risk = added_loss_risk_raw_bps * risk_fill
        haircut = attempted_signals * execution_haircut_bps
        net = opp - risk - total_fee_slippage_buffer_bps - haircut
        return {
            "opportunity_gain_bps": round(opp, 6),
            "added_loss_risk_bps": round(risk, 6),
            "fee_slippage_buffer_bps": round(total_fee_slippage_buffer_bps, 6),
            "execution_haircut_bps": round(haircut, 6),
            "net_impact_bps": round(net, 6),
        }

    sensitivity_bands = {
        "pessimistic": _band(0.25, 1.00, 3.0),
        "conservative": _band(CONSERVATIVE_OPPORTUNITY_FILL_FACTOR, CONSERVATIVE_RISK_FILL_FACTOR, CONSERVATIVE_EXECUTION_HAIRCUT_BPS),
        "optimistic": _band(0.75, 0.75, 1.0),
    }
    residual_risks = [
        "Rejected intents are not guaranteed to have filled if policy had been relaxed.",
        "Recorder forward moves do not prove exchange fill quality or queue position.",
        "Counterfactual scoring uses post-move bps as a proxy for realized economics, not a full execution replay.",
    ]
    if missing_price_rows > 0:
        residual_risks.append(f"{missing_price_rows} validation atoms lacked sufficient counterfactual price fields and were excluded.")

    return SimulationResult(
        context_id=context_record["context_id"],
        verdict=context_record["verdict"],
        validation_atom_count=len(simulated_atoms),
        policy_too_strict_count=sum(1 for item in simulated_atoms if item.canonical_outcome_code == "POLICY_TOO_STRICT"),
        policy_protected_count=sum(1 for item in simulated_atoms if item.canonical_outcome_code == "POLICY_PROTECTED"),
        opportunity_gain_raw_bps=round(opportunity_gain_raw_bps, 6),
        added_loss_risk_raw_bps=round(added_loss_risk_raw_bps, 6),
        fee_slippage_buffer_bps=round(total_fee_slippage_buffer_bps, 6),
        conservative_opportunity_gain_bps=round(conservative_opportunity_gain_bps, 6),
        conservative_added_loss_risk_bps=round(conservative_added_loss_risk_bps, 6),
        conservative_net_impact_bps=round(conservative_net_impact_bps, 6),
        fill_uncertainty="Conservative opportunity fill factor fixed at 0.50; losses assumed fully realizable at 1.00.",
        execution_uncertainty="Additional execution haircut of 2.0 bps per hypothetical trade applied beyond fee/slippage buffer.",
        simulated_atoms=simulated_atoms,
        sensitivity_bands=sensitivity_bands,
        residual_risks=residual_risks,
    )


def determine_verdict(results: Sequence[SimulationResult], blocked_missing_price_data: bool, partial_only: bool) -> str:
    if blocked_missing_price_data and not results:
        return "BLOCKED_BY_MISSING_COUNTERFACTUAL_PRICE_DATA"
    if partial_only and not results:
        return "PARTIAL_SIMULATION_ONLY"
    if not results:
        return "COUNTERFACTUAL_INCONCLUSIVE"
    aggregate_net = sum(item.conservative_net_impact_bps for item in results)
    low_power = any(item.validation_atom_count < 20 for item in results)
    if aggregate_net > 0:
        return "COUNTERFACTUAL_POSITIVE_BUT_LOW_POWER" if low_power else "COUNTERFACTUAL_INCONCLUSIVE"
    if aggregate_net < 0:
        return "COUNTERFACTUAL_NEGATIVE"
    return "COUNTERFACTUAL_INCONCLUSIVE"


def build_report(
    *,
    manifest_path: Path,
    saf_path: Path,
    poc03_report_path: Path,
    poc02_report_path: Path,
    manifest: dict[str, list[dict[str, Any]]],
    simulated_results: Sequence[SimulationResult],
    skipped_contexts: Sequence[dict[str, Any]],
    verdict: str,
) -> str:
    aggregate_opportunity = sum(item.conservative_opportunity_gain_bps for item in simulated_results)
    aggregate_risk = sum(item.conservative_added_loss_risk_bps for item in simulated_results)
    aggregate_buffer = sum(item.fee_slippage_buffer_bps for item in simulated_results)
    aggregate_net = sum(item.conservative_net_impact_bps for item in simulated_results)
    lines = [
        "# SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION_REPORT",
        "",
        "## Verdict",
        verdict,
        "",
        "## Scope",
        "- Read-only counterfactual policy-impact simulation over POC_03B-admitted contexts only.",
        "- No live logic, YAML policy, gates, enforcement, or Aurora runtime journal writes.",
        "",
        "## Inputs Read",
        f"- {manifest_path}",
        f"- {saf_path}",
        f"- {poc03_report_path}",
        f"- {poc02_report_path}",
        "",
        "## Candidate Manifest Summary",
        f"- READY_FOR_COUNTERFACTUAL_SIM count: {len(manifest.get('READY_FOR_COUNTERFACTUAL_SIM', []))}",
        f"- PROMISING_LOW_SUPPORT count: {len(manifest.get('PROMISING_LOW_SUPPORT', []))}",
        f"- REJECTED_FALSE_POSITIVE count: {len(manifest.get('REJECTED_FALSE_POSITIVE', []))}",
        f"- INCONCLUSIVE_LOW_POWER count: {len(manifest.get('INCONCLUSIVE_LOW_POWER', []))}",
        f"- CONFIRMED_BUT_UNSTABLE count: {len(manifest.get('CONFIRMED_BUT_UNSTABLE', []))}",
        f"- UNKNOWN count: {len(manifest.get('UNKNOWN', []))}",
        "",
        "## Simulated Contexts",
    ]
    if simulated_results:
        for result in simulated_results:
            lines.extend(
                [
                    f"- {result.context_id}",
                    f"  verdict={result.verdict} validation_atom_count={result.validation_atom_count}",
                    f"  policy_too_strict_count={result.policy_too_strict_count} policy_protected_count={result.policy_protected_count}",
                    f"  conservative_net_impact_bps={result.conservative_net_impact_bps}",
                ]
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Skipped Contexts"])
    if skipped_contexts:
        for ctx in skipped_contexts:
            lines.append(f"- {ctx['context_id']} bucket_excluded_from_simulation")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Counterfactual Method",
            "- Reconstruct validation-window atoms per context by replaying the same chronological split logic used in POC_03.",
            "- For `POLICY_TOO_STRICT_CANDIDATE`, treat `POLICY_TOO_STRICT` rows as opportunity candidates and `POLICY_PROTECTED` rows as avoided-loss candidates.",
            "- Use `outcome_snapshot.post_move_bps` at T+30m as the counterfactual move proxy.",
            "- Apply conservative asymmetry: opportunity gains are discounted by a 0.50 fill factor; added loss risk is kept at 1.00.",
            "- Subtract a 10.0 bps fee/slippage buffer and a 2.0 bps execution haircut per hypothetical trade.",
            "",
            "## Opportunity Gain Estimate",
            f"- aggregate conservative opportunity_gain_bps: {round(aggregate_opportunity, 6)}",
        ]
    )
    for result in simulated_results:
        lines.append(f"- {result.context_id}: raw={result.opportunity_gain_raw_bps} conservative={result.conservative_opportunity_gain_bps}")

    lines.extend(
        [
            "",
            "## Added Loss Risk Estimate",
            f"- aggregate conservative added_loss_risk_bps: {round(aggregate_risk, 6)}",
        ]
    )
    for result in simulated_results:
        lines.append(f"- {result.context_id}: raw={result.added_loss_risk_raw_bps} conservative={result.conservative_added_loss_risk_bps}")

    lines.extend(
        [
            "",
            "## Fee/Slippage Assumptions",
            f"- default fee_slippage_buffer_bps_per_trade: {DEFAULT_FEE_SLIPPAGE_BUFFER_BPS}",
            f"- aggregate fee_slippage_buffer_bps: {round(aggregate_buffer, 6)}",
            f"- conservative opportunity fill factor: {CONSERVATIVE_OPPORTUNITY_FILL_FACTOR}",
            f"- conservative risk fill factor: {CONSERVATIVE_RISK_FILL_FACTOR}",
            f"- execution haircut bps per trade: {CONSERVATIVE_EXECUTION_HAIRCUT_BPS}",
            "",
            "## Conservative Net Impact",
            f"- aggregate conservative net impact bps: {round(aggregate_net, 6)}",
        ]
    )
    for result in simulated_results:
        lines.append(f"- {result.context_id}: {result.conservative_net_impact_bps}")

    lines.extend(["", "## Sensitivity Bands"])
    if simulated_results:
        for result in simulated_results:
            lines.append(f"- {result.context_id}")
            for band_name, band in result.sensitivity_bands.items():
                lines.append(
                    f"  {band_name}: opportunity_gain_bps={band['opportunity_gain_bps']} "
                    f"added_loss_risk_bps={band['added_loss_risk_bps']} "
                    f"fee_slippage_buffer_bps={band['fee_slippage_buffer_bps']} "
                    f"execution_haircut_bps={band['execution_haircut_bps']} "
                    f"net_impact_bps={band['net_impact_bps']}"
                )
    else:
        lines.append("- none")

    lines.extend(["", "## Residual Risks"])
    for result in simulated_results:
        for risk in result.residual_risks:
            lines.append(f"- {result.context_id}: {risk}")
    if not simulated_results:
        lines.append("- No candidate contexts could be simulated from the admitted manifest bucket.")

    lines.extend(
        [
            "",
            "## Recommendation",
        ]
    )
    if verdict == "COUNTERFACTUAL_POSITIVE_BUT_LOW_POWER":
        lines.append("- Proceed only to a later shadow `WOULD_RELAX / WOULD_BLOCK` package for this context; do not recommend live policy change.")
    elif verdict == "COUNTERFACTUAL_NEGATIVE":
        lines.append("- Do not advance this context to a relaxation shadow package without new evidence.")
    elif verdict == "PARTIAL_SIMULATION_ONLY":
        lines.append("- Collect more counterfactual price coverage before any shadow relaxation package.")
    elif verdict == "BLOCKED_BY_MISSING_COUNTERFACTUAL_PRICE_DATA":
        lines.append("- Counterfactual simulation is blocked until price/reference fields are available for admitted validation atoms.")
    else:
        lines.append("- Treat the result as non-actionable for live policy; only revisit after additional shadow-grade evidence.")
    lines.append("")
    return "\n".join(lines) + "\n"


def run(
    *,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    saf_path: Path = DEFAULT_SAF_PATH,
    poc03_report_path: Path = DEFAULT_POC03_REPORT_PATH,
    poc02_report_path: Path = DEFAULT_POC02_REPORT_PATH,
    output_report_path: Path = DEFAULT_REPORT_PATH,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    validation_by_context = _load_validation_atoms_by_context(saf_path)
    ready_contexts = manifest.get("READY_FOR_COUNTERFACTUAL_SIM", [])
    skipped_contexts = []
    for bucket, items in manifest.items():
        if bucket == "READY_FOR_COUNTERFACTUAL_SIM":
            continue
        skipped_contexts.extend(items)

    simulated_results: list[SimulationResult] = []
    partial_only = False
    blocked_missing_price_data = False
    for ctx in ready_contexts:
        context_key = _context_key_tuple(ctx["context_id"])
        validation_atoms = validation_by_context.get(context_key, [])
        if not validation_atoms:
            blocked_missing_price_data = True
            continue
        if ctx.get("verdict") == "POLICY_TOO_STRICT_CANDIDATE":
            result = simulate_policy_too_strict_candidate(
                context_record=ctx,
                validation_atoms=validation_atoms,
                saf_path=saf_path,
            )
            if result is None:
                partial_only = True
                continue
            simulated_results.append(result)
        else:
            partial_only = True

    verdict = determine_verdict(simulated_results, blocked_missing_price_data, partial_only)
    report_text = build_report(
        manifest_path=manifest_path,
        saf_path=saf_path,
        poc03_report_path=poc03_report_path,
        poc02_report_path=poc02_report_path,
        manifest=manifest,
        simulated_results=simulated_results,
        skipped_contexts=skipped_contexts,
        verdict=verdict,
    )
    output_report_path.write_text(report_text, encoding="utf-8")
    return {
        "verdict": verdict,
        "simulated_results": [asdict(item) for item in simulated_results],
        "output_report_path": output_report_path,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only POC_04 counterfactual policy impact simulation.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--saf", type=Path, default=DEFAULT_SAF_PATH)
    parser.add_argument("--poc03-report", type=Path, default=DEFAULT_POC03_REPORT_PATH)
    parser.add_argument("--poc02-report", type=Path, default=DEFAULT_POC02_REPORT_PATH)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run(
        manifest_path=args.manifest,
        saf_path=args.saf,
        poc03_report_path=args.poc03_report,
        poc02_report_path=args.poc02_report,
        output_report_path=args.output_report,
    )
    print(f"verdict={result['verdict']}")
    print(f"report={result['output_report_path']}")
    print(f"simulated_contexts={len(result['simulated_results'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
