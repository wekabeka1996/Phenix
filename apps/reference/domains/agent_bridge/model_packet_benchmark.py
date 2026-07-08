"""Bounded model-to-AgentIntent benchmark; no tools and no execution authority."""
from __future__ import annotations
import hashlib, json, os, re, time
from pathlib import Path
from typing import Any, Literal, Optional
import httpx
from pydantic import BaseModel, ConfigDict, Field
from .agent_intent import AgentIntentV0
from .agent_intent_dry_run import AgentIntentDryRunRecordV1, validate_intent_dry_run

SAFE_ACTIONS = {"WAIT","OBSERVE","NO_ACTION","DRY_RUN_OPEN_LONG","DRY_RUN_OPEN_SHORT","DRY_RUN_CLOSE","DRY_RUN_PROTECT"}
SECRET = re.compile(r"(?:AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z_-]{16,}|Bearer\s+\S+|api[_-]?key\s*[=:])", re.I)

class ModelPacketIntentCandidateV0(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["model-packet-intent-candidate/v0"]
    provider: str; model: str; model_call_id: str; created_ts_ms: int; packet_ref: str
    symbol: str; horizon: Literal["micro","scalp"]; action: str; side: Literal["LONG","SHORT","NONE"]
    confidence: float = Field(ge=0, le=1); thesis: str; invalidation: str
    expected_scenarios: list[dict[str, Any]]; evidence_refs: list[str]
    acknowledged_warnings: list[str]; risk_note: str
    non_executable: Literal[True]; no_order_authority: Literal[True]; no_exchange_access: Literal[True]
    requested_agent_intent: dict[str, Any]; raw_output_ref: str

def redact(text: str) -> str:
    return SECRET.sub("[REDACTED]", text)

def bounded_evidence(packet: dict[str, Any], symbol: str, chain: dict[str, Any]) -> dict[str, Any]:
    return {"packet_id":packet.get("packet_id"),"produced_ts_ms":packet.get("produced_ts_ms"),"symbols":packet.get("symbols"),
      "symbol_market":next((x for x in packet.get("symbol_markets",[]) if x.get("symbol")==symbol),None),
      "feature_signal":next((x for x in packet.get("feature_signals",[]) if x.get("symbol")==symbol),None),
      "position_life":packet.get("position_life"),"execution_body":packet.get("execution_body"),
      "scenario_memory":packet.get("action_review_memory"),"archive_chain":{"verdict":chain.get("chain_verdict"),"diagnostics":chain.get("diagnostics",[])[:4]}}

def build_prompt(packet: dict[str, Any], symbol: str, horizon: str, chain: dict[str, Any]) -> tuple[str,str]:
    evidence=bounded_evidence(packet,symbol,chain); packet_ref=f"agent-feed://packet/{packet['packet_id']}"
    instruction=("Return JSON only. Produce one non-executable dry-run intent. You cannot trade, submit orders, ask for exchange access, use tools, or invent symbols, positions, orders or fills. "
      f"Use symbol {symbol}, horizon {horizon}, packet_ref {packet_ref}. Allowed actions: {sorted(SAFE_ACTIONS)}. "
      "Allowed expected scenario_id values: no_clear_scenario, continuation, volatility_expansion. "
      "Set non_executable, no_order_authority, no_exchange_access true. Preserve evidence refs. Schema fields: schema_version='model-packet-intent-candidate/v0', provider, model, model_call_id, created_ts_ms, packet_ref, symbol, horizon, action, side, confidence, thesis, invalidation, expected_scenarios (scenario_id/confidence/thesis), evidence_refs, acknowledged_warnings, risk_note, booleans, requested_agent_intent object, raw_output_ref.")
    return instruction, json.dumps(evidence,separators=(",",":"),ensure_ascii=False)

def parse_candidate(raw: str, *, provider: str, model: str, call_id: str) -> ModelPacketIntentCandidateV0:
    cleaned=raw.strip(); cleaned=re.sub(r"^```(?:json)?\s*|\s*```$","",cleaned)
    data=json.loads(cleaned); data.update(provider=provider,model=model,model_call_id=call_id)
    candidate=ModelPacketIntentCandidateV0.model_validate(data)
    if candidate.action not in SAFE_ACTIONS or candidate.symbol not in {"BTCUSDT","ETHUSDT"}: raise ValueError("hallucinated/out-of-scope action or symbol")
    if candidate.packet_ref not in candidate.evidence_refs: raise ValueError("packet evidence ref missing")
    forbidden=json.dumps(data).lower()
    if any(x in forbidden for x in ('"order_id"','"client_order_id"','"fill_id"','"exchange_order_id"')): raise ValueError("hallucinated order/fill identifier")
    return candidate

def candidate_to_intent(c: ModelPacketIntentCandidateV0, now_ms: int) -> AgentIntentV0:
    ident=hashlib.sha256(f"{c.model_call_id}|{c.packet_ref}".encode()).hexdigest()[:20]
    side=c.side; mechanical=c.action.startswith("DRY_RUN_")
    return AgentIntentV0.model_validate({"intent_id":f"intent_model_{ident}","created_ts_ms":now_ms,"source":"model_packet_benchmark","agent_id":"p24.model-packet-benchmark","model_id":f"{c.provider}/{c.model}","model_call_ref":f"model-benchmark://call/{c.model_call_id}","rank":"unranked_benchmark","mode":"dry_run_no_execution","symbol":c.symbol,"horizon":c.horizon,"action":c.action,"side":side,"confidence":c.confidence,"thesis":c.thesis[:600],"invalidation":c.invalidation[:600],"expected_scenarios":c.expected_scenarios[:3],"used_packet_refs":[c.packet_ref],"used_memory_refs":[x for x in c.evidence_refs if "memory" in x][:8],"acknowledged_warnings":c.acknowledged_warnings[:12],"requested_execution_semantics":{"shape":"REFERENCE_ONLY" if mechanical else "NONE","reduce_only_requested":c.action in {"DRY_RUN_CLOSE","DRY_RUN_PROTECT"},"non_executable":True},"risk_note":c.risk_note[:600],"expiry_ts_ms":now_ms+120000,"trace_id":f"trace_model_{ident}"})

def call_deepseek(*, api_key: str, base_url: str, model: str, system: str, evidence: str, timeout: float=45) -> tuple[str,dict[str,Any]]:
    started=time.perf_counter(); response=httpx.post(base_url.rstrip("/")+"/chat/completions",headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},json={"model":model,"messages":[{"role":"system","content":system},{"role":"user","content":evidence}],"temperature":0,"response_format":{"type":"json_object"}},timeout=timeout,follow_redirects=False)
    latency=(time.perf_counter()-started)*1000; response.raise_for_status(); body=response.json()
    return body["choices"][0]["message"]["content"],{"latency_ms":round(latency,3),"usage":body.get("usage",{}),"provider_call_id":body.get("id")}

class BenchmarkLedger:
    def __init__(self,path:Path): self.path=path
    def append(self,row:dict[str,Any])->bool:
        safe=json.dumps(row,separators=(",",":"),ensure_ascii=False)
        if SECRET.search(safe): raise ValueError("secret leakage rejected")
        self.path.parent.mkdir(parents=True,exist_ok=True); ids=set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines(): ids.add(json.loads(line)["model_call_id"])
        if row["model_call_id"] in ids:return False
        with self.path.open("a",encoding="utf-8") as f: f.write(safe+"\n");f.flush();os.fsync(f.fileno())
        return True

def benchmark_once(packet:dict[str,Any],chain:dict[str,Any],*,api_key:str,base_url:str,model:str,symbol:str,horizon:str,index:int,timeout:float=30)->tuple[dict[str,Any],Optional[AgentIntentDryRunRecordV1]]:
    call_id="mbc_"+hashlib.sha256(f"{packet['packet_id']}|{symbol}|{horizon}|{index}|{time.time_ns()}".encode()).hexdigest()[:24]
    system,evidence=build_prompt(packet,symbol,horizon,chain); started=int(time.time()*1000)
    row={"schema_version":"model-packet-benchmark-ledger/v1","provider":"deepseek","model":model,"model_call_id":call_id,"packet_ref":f"agent-feed://packet/{packet['packet_id']}","prompt_hash":hashlib.sha256((system+evidence).encode()).hexdigest(),"request_token_estimate":(len(system)+len(evidence)+3)//4,"parse_status":"not_attempted","schema_status":"not_attempted","dry_run_validation_status":"not_run","safety":{"non_executable":False,"no_order_authority":False,"no_exchange_access":False},"redaction_proof":True}
    try:
        raw,meta=call_deepseek(api_key=api_key,base_url=base_url,model=model,system=system,evidence=evidence,timeout=timeout); row.update(meta); row["response_token_estimate"]=(len(raw)+3)//4
        candidate=parse_candidate(raw,provider="deepseek",model=model,call_id=call_id); row.update(parse_status="parsed",schema_status="valid",safety={"non_executable":True,"no_order_authority":True,"no_exchange_access":True},sanitized_output=redact(raw)[:12000])
        intent=candidate_to_intent(candidate,int(time.time()*1000)); result=validate_intent_dry_run(intent,packet,now_ms=int(time.time()*1000)); record=AgentIntentDryRunRecordV1(intent=intent,result=result)
        row["dry_run_validation_status"]=result.validation_status;row["dry_run_result_ref"]=f"agent-intent://dry-run/{result.dry_run_id}";return row,record
    except Exception as exc:
        row.update(parse_status="failed",schema_status="rejected",error=redact(str(exc))[:500],latency_ms=round(time.time()*1000-started,3));return row,None
