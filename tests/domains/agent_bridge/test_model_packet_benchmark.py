import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from apps.reference.domains.agent_bridge.model_packet_benchmark import ModelPacketIntentCandidateV0,BenchmarkLedger,build_prompt,parse_candidate,candidate_to_intent,redact

def candidate():
 return {"schema_version":"model-packet-intent-candidate/v0","provider":"deepseek","model":"m","model_call_id":"c","created_ts_ms":1,"packet_ref":"agent-feed://packet/afp_x","symbol":"BTCUSDT","horizon":"micro","action":"OBSERVE","side":"NONE","confidence":.5,"thesis":"Observe bounded evidence.","invalidation":"Packet expires.","expected_scenarios":[{"scenario_id":"no_clear_scenario","confidence":1,"thesis":"No clear scenario."}],"evidence_refs":["agent-feed://packet/afp_x","aurora-publication://scenario-memory/index/v0"],"acknowledged_warnings":["no execution"],"risk_note":"Cannot trade.","non_executable":True,"no_order_authority":True,"no_exchange_access":True,"requested_agent_intent":{},"raw_output_ref":"model-benchmark://raw/c"}
def test_schema_and_conversion():
 c=ModelPacketIntentCandidateV0.model_validate(candidate());i=candidate_to_intent(c,100)
 assert i.source=="model_packet_benchmark" and i.model_id=="deepseek/m" and i.requested_execution_semantics.non_executable
def test_safety_flags_fail_closed():
 d=candidate();d["non_executable"]=False
 with pytest.raises(ValidationError):ModelPacketIntentCandidateV0.model_validate(d)
def test_parser_rejects_symbol_and_missing_ref():
 d=candidate();d["symbol"]="DOGEUSDT"
 with pytest.raises(ValueError):parse_candidate(json.dumps(d),provider="deepseek",model="m",call_id="c")
 d=candidate();d["evidence_refs"]=[]
 with pytest.raises(ValueError):parse_candidate(json.dumps(d),provider="deepseek",model="m",call_id="c")
def test_redaction_and_prompt_boundary():
 assert "sk-secret" not in redact("token sk-secretsecretsecretsecret")
 packet={"packet_id":"afp_x","symbols":["BTCUSDT"],"symbol_markets":[],"feature_signals":[],"position_life":{},"execution_body":{},"action_review_memory":{}}
 system,evidence=build_prompt(packet,"BTCUSDT","micro",{"chain_verdict":"chain_valid"});assert "JSON only" in system and "afp_x" in evidence
def test_ledger_idempotent_and_secret_reject(tmp_path:Path):
 l=BenchmarkLedger(tmp_path/"x.jsonl");row={"model_call_id":"x","safe":"ok"};assert l.append(row);assert not l.append(row)
 with pytest.raises(ValueError):l.append({"model_call_id":"y","value":"sk-secretsecretsecretsecret"})
