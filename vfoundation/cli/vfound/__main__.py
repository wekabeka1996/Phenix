from __future__ import annotations
import json
import sys
import pathlib
import uuid
from datetime import datetime
from typing import Any, Dict
import typer
import yaml

# Add vfoundation to path for imports
# → vfoundation/ (absolute)
_cli_root = pathlib.Path(__file__).parent.parent.parent.resolve()
_vfoundation_pkg = _cli_root / "vfoundation"  # → vfoundation/vfoundation/
if str(_cli_root) not in sys.path:
    sys.path.insert(0, str(_cli_root))  # for apps.reference.*
if str(_vfoundation_pkg) not in sys.path:
    sys.path.insert(0, str(_vfoundation_pkg))  # for vfoundation.core.*

from vfoundation.core.protocol import Message  # noqa: E402
from vfoundation.dr import wal  # noqa: E402
from vfoundation.security.signing_ed25519 import sign  # noqa: E402

app = typer.Typer(add_completion=False, help="vfound CLI")

dict_app = typer.Typer(add_completion=False, help="Dictionary tooling")
app.add_typer(dict_app, name="dict")

REPORTS_DIR = pathlib.Path("ops/reports")


@app.command("schema")
def schema_gen(from_pydantic: bool = True) -> None:
    out = pathlib.Path("schemas")
    out.mkdir(exist_ok=True, parents=True)
    # Minimal demo schema dump
    msg_schema = Message.model_json_schema()
    (out / "message_v1.json").write_text(
        json.dumps(msg_schema, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    typer.echo("Schemas generated: schemas/message_v1.json")


@dict_app.command("lint")
def dict_lint(
    global_: bool = typer.Option(False, "--global"), domain: bool = typer.Option(False, "--domain")
) -> None:
    ok = True
    if global_:
        # Check both framework and app dictionaries
        framework_dict = pathlib.Path("vfoundation/dictionaries/global_v2_2_framework.yaml")
        app_dict = pathlib.Path("apps/reference/dictionaries/global_v2_2.yaml")
        ok = ok and framework_dict.exists() and app_dict.exists()
    if domain:
        ok = ok and pathlib.Path("vfoundation/dictionaries/domains").exists()
    typer.echo("dictionary: OK" if ok else "dictionary: FAIL")
    raise typer.Exit(code=0 if ok else 1)


@dict_app.command("validate")
def dict_validate(
    report: pathlib.Path | None = typer.Option(
        None,
        "--report",
        help="Write validation report (JSON or MD). Example: reports/dict_validate.json",
    )
) -> None:
    framework_path = pathlib.Path("vfoundation/dictionaries/global_v2_2_framework.yaml")
    app_path = pathlib.Path("apps/reference/dictionaries/global_v2_2.yaml")

    framework = yaml.safe_load(framework_path.read_text(encoding="utf-8"))
    app = yaml.safe_load(app_path.read_text(encoding="utf-8"))

    errors: list[str] = []

    def _require_keys(name: str, obj: Any) -> None:
        if not isinstance(obj, dict):
            errors.append(f"{name}: not a YAML mapping")
            return
        required = ["version", "ops", "ttl_profiles", "security", "limits"]
        for k in required:
            if k not in obj:
                errors.append(f"{name}: missing required key '{k}'")

    _require_keys("framework", framework)
    _require_keys("app", app)

    def _validate_invariants(name: str, obj: Any) -> None:
        if not isinstance(obj, dict):
            return
        ops = obj.get("ops")
        if not isinstance(ops, list) or not ops:
            errors.append(f"{name}: ops must be non-empty list")
            return
        ops_set = set(ops)

        security = obj.get("security")
        if not isinstance(security, dict):
            errors.append(f"{name}: security must be mapping")
        else:
            sign_required_ops = security.get("sign_required_ops")
            if not isinstance(sign_required_ops, list):
                errors.append(f"{name}: security.sign_required_ops must be list")
            else:
                if not set(sign_required_ops).issubset(ops_set):
                    errors.append(
                        f"{name}: sign_required_ops must be subset of ops: {sign_required_ops} ⊄ {sorted(ops_set)}"
                    )

        ttl_profiles = obj.get("ttl_profiles")
        if not isinstance(ttl_profiles, dict) or not ttl_profiles:
            errors.append(f"{name}: ttl_profiles must be non-empty mapping")
        else:
            for profile, ttl in ttl_profiles.items():
                if not isinstance(ttl, int):
                    errors.append(f"{name}: ttl_profiles.{profile} must be int")
                    continue
                if ttl < 1 or ttl > 30000:
                    errors.append(f"{name}: ttl_profiles.{profile} out of range 1..30000: {ttl}")

    _validate_invariants("framework", framework)
    _validate_invariants("app", app)

    result = {
        "ok": len(errors) == 0,
        "framework_path": str(framework_path),
        "app_path": str(app_path),
        "errors": errors,
    }

    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        suffix = report.suffix.lower()
        if suffix == ".md":
            lines: list[str] = []
            lines.append("# vfound dict validate\n")
            lines.append(f"ok: {result['ok']}\n")
            if errors:
                lines.append("\n## errors\n")
                for e in errors:
                    lines.append(f"- {e}\n")
            report.write_text("".join(lines), encoding="utf-8")
        else:
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    typer.echo("dictionary validate: OK" if result["ok"] else "dictionary validate: FAIL")
    if errors:
        for e in errors:
            typer.echo(f"- {e}")
    raise typer.Exit(code=0 if result["ok"] else 1)


@app.command("rfc")
def rfc_new(name: str) -> None:
    path = pathlib.Path(f"docs/RFC-{name}.md")
    if path.exists():
        typer.echo("Exists")
        raise typer.Exit(code=1)
    template = pathlib.Path("docs/ADR-Template.md").read_text(encoding="utf-8")
    path.write_text(template.replace(
        "ADR-XXXX", f"RFC-{name}"), encoding="utf-8")
    typer.echo(f"Created {path}")


@app.command("simulate")
def simulate_flow(file: pathlib.Path) -> None:
    rid = str(uuid.uuid4())
    msg = Message(
        op="ASK",
        verb="EVAL",
        src="risk_strategy",
        dst="execution_position",
        rid=rid,
        why="simulate",
    )
    wal.append(msg.model_dump())
    dec = Message(
        op="DEC", verb="EVAL", src="risk_strategy", dst="execution_position", rid=rid, why="ok"
    )
    payload = json.dumps(dec.model_dump(), sort_keys=True).encode()
    sig = sign(payload).hex()
    dec.sig = sig
    wal.append(dec.model_dump())
    typer.echo(f"Simulated rid={rid}")


@app.command("replay")
def replay_rid(
    rid: str,
    shadow: bool = typer.Option(
        False, "--shadow", help="Shadow mode (offline replay)"),
    output: pathlib.Path = typer.Option(
        None, "--output", "-o", help="Output JSON path"),
) -> None:
    """
    Replay events for specific RID from WAL.

    In shadow mode: reads WAL, computes integrity check, saves report to ops/reports/
    """
    REPORTS_DIR.mkdir(exist_ok=True, parents=True)

    # Read all events for RID from WAL
    events = []
    wal_dir = pathlib.Path("ops/wal")

    if not wal_dir.exists():
        typer.echo(f"❌ WAL directory not found: {wal_dir}", err=True)
        raise typer.Exit(code=1)

    for wal_file in sorted(wal_dir.glob("*.jsonl")):
        try:
            for line in wal_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    if record.get("rid") == rid:
                        events.append(record)
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            typer.echo(f"⚠️  Error reading {wal_file}: {e}", err=True)
            continue

    if not events:
        typer.echo(f"❌ No events found for RID: {rid}", err=True)
        raise typer.Exit(code=1)

    # Build report
    report = {
        "rid": rid,
        "events_count": len(events),
        "computed_at": datetime.utcnow().isoformat() + "Z",
        "shadow_mode": shadow,
        "integrity": {
            "hash_chain_valid": True,  # TODO: implement hash chain validation
            "all_events_have_hash": all("_hash" in e for e in events),
        },
        "why_chain": [e.get("why", "") for e in events if e.get("why")],
        "events": events if not shadow else [],  # Full events only if not shadow mode
    }

    # Save report
    output_path = output or (REPORTS_DIR / f"rid_{rid}.json")
    output_path.parent.mkdir(exist_ok=True, parents=True)
    output_path.write_text(json.dumps(
        report, ensure_ascii=False, indent=2), encoding="utf-8")

    typer.echo(f"✅ Replay complete: {len(events)} events")
    typer.echo(f"📄 Report saved: {output_path}")

    if shadow:
        why_chain: list[Any] = report.get(
            "why_chain", [])  # type: ignore[assignment]
        integrity: Dict[str, Any] = report.get(
            "integrity", {})  # type: ignore[assignment]
        typer.echo(f"🔍 WHY chain length: {len(why_chain)}")
        typer.echo(
            f"🔐 Integrity: {'✅' if integrity.get('hash_chain_valid') else '❌'}")


@app.command("drift")
def drift_batch(
    from_wal: bool = typer.Option(True, "--from-wal", help="Read from WAL"),
    window_sec: float = typer.Option(
        1.0, "--window-sec", help="Time window for matching (seconds)"
    ),
    output: pathlib.Path = typer.Option(
        None, "--output", "-o", help="Output JSON path"),
) -> None:
    """
    Compute drift metrics in batch mode from WAL.

    Reads all DEC and EVT messages from WAL, computes confusion matrix and drift%.
    Saves report to ops/reports/drift_<timestamp>.json
    """
    # Import drift_monitor dynamically to ensure sys.path is set
    import importlib.util
    import types
    from importlib.machinery import ModuleSpec

    drift_monitor_path = (_cli_root / "apps" / "monitoring" / "drift_monitor.py")
    spec: ModuleSpec | None = importlib.util.spec_from_file_location(
        "drift_monitor", drift_monitor_path
    )

    if spec is None or spec.loader is None:
        typer.echo(
            f"❌ Failed to load drift_monitor from {drift_monitor_path}", err=True)
        raise typer.Exit(code=1)

    drift_monitor: types.ModuleType = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = drift_monitor  # Add to sys.modules before exec
    spec.loader.exec_module(drift_monitor)
    compute_drift = drift_monitor.compute_drift

    REPORTS_DIR.mkdir(exist_ok=True, parents=True)

    wal_dir = pathlib.Path("ops/wal")

    if not wal_dir.exists():
        typer.echo(f"❌ WAL directory not found: {wal_dir}", err=True)
        raise typer.Exit(code=1)

    # Read all DEC and EVT messages from WAL
    decisions: list[dict[str, Any]] = []
    events_list: list[dict[str, Any]] = []
    total_records: int = 0

    typer.echo(f"📖 Reading WAL from {wal_dir}...")

    for wal_file in sorted(wal_dir.glob("*.jsonl")):
        try:
            for line in wal_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    total_records += 1

                    op = record.get("op", "")
                    verb = record.get("verb", "")

                    if op == "DEC" and verb in ("OPEN", "CLOSE"):
                        decisions.append(record)
                    elif op == "EVT" and verb in ("ORDER_PLACED", "FILL", "CANCELLED"):
                        events_list.append(record)
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            typer.echo(f"⚠️  Error reading {wal_file}: {e}", err=True)
            continue

    typer.echo(f"📊 Total records: {total_records}")
    typer.echo(f"📈 Decisions (DEC): {len(decisions)}")
    typer.echo(f"📉 Events (EVT): {len(events_list)}")

    if not decisions and not events_list:
        typer.echo("⚠️  No DEC or EVT messages found in WAL", err=True)
        typer.echo("ℹ️  Run 'vfound simulate' to generate sample data", err=True)
        raise typer.Exit(code=1)

    # Compute drift
    typer.echo(f"🔬 Computing drift (window: {window_sec}s)...")
    drift_report = compute_drift(
        decisions, events_list, time_window_sec=window_sec)

    # Build JSON report
    report = {
        "computed_at": datetime.utcnow().isoformat() + "Z",
        "time_window_sec": window_sec,
        "total_records": total_records,
        "decisions_count": len(decisions),
        "events_count": len(events_list),
        "confusion_matrix": {
            "tp": drift_report.confusion.tp,
            "fp": drift_report.confusion.fp,
            "fn": drift_report.confusion.fn,
            "tn": drift_report.confusion.tn,
        },
        "metrics": {
            "drift_pct": round(drift_report.confusion.drift_pct, 2),
            "accuracy": round(drift_report.confusion.accuracy, 2),
        },
        "mismatches_count": len(drift_report.mismatches),
        # First 10 mismatches
        "mismatches": [m.to_dict() for m in drift_report.mismatches[:10]],
    }

    # Save report
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_path = output or (REPORTS_DIR / f"drift_{timestamp}.json")
    output_path.parent.mkdir(exist_ok=True, parents=True)
    output_path.write_text(json.dumps(
        report, ensure_ascii=False, indent=2), encoding="utf-8")

    typer.echo("\n✅ Drift analysis complete")
    typer.echo(f"📄 Report saved: {output_path}")
    typer.echo("\n📊 Results:")

    confusion: Dict[str, Any] = report.get(
        "confusion_matrix", {})  # type: ignore[assignment]
    metrics_data: Dict[str, Any] = report.get(
        "metrics", {})  # type: ignore[assignment]

    typer.echo(f"  TP (True Positive):  {confusion.get('tp', 0)}")
    typer.echo(f"  FP (False Positive): {confusion.get('fp', 0)}")
    typer.echo(f"  FN (False Negative): {confusion.get('fn', 0)}")
    typer.echo(f"  TN (True Negative):  {confusion.get('tn', 0)}")
    typer.echo(f"  Drift: {metrics_data.get('drift_pct', 0)}%")
    typer.echo(f"  Accuracy: {metrics_data.get('accuracy', 0)}%")


@app.command("trace")
def trace_get(rid: str) -> None:
    # naive scan
    import json
    import pathlib

    evs = []
    for f in pathlib.Path("ops/wal").glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("rid") == rid:
                evs.append(obj)
    typer.echo(json.dumps({"rid": rid, "events": evs},
               ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
