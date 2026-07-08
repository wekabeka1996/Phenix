from __future__ import annotations
import argparse,json,os
from pathlib import Path
from apps.reference.domains.agent_bridge.model_packet_benchmark import BenchmarkLedger,benchmark_once
from apps.reference.domains.agent_bridge.agent_intent_dry_run import AgentIntentDryRunLedger

def env(path:Path)->dict[str,str]:
    out={}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            k,v=line.split("=",1);out[k.strip()]=v.strip().strip('"')
    return out
def packet(path:Path)->dict:
    raw=json.loads(path.read_text(encoding="utf-8-sig").splitlines()[-1]);return raw.get("packet",raw)
def write_jsonl(path:Path,items:list[dict]):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text("".join(json.dumps(x,separators=(",",":"))+"\n" for x in items),encoding="utf-8")
def main():
    p=argparse.ArgumentParser();p.add_argument("--env-file",required=True);p.add_argument("--packet-sample",required=True);p.add_argument("--project-root",default=".");p.add_argument("--output-dir",required=True);p.add_argument("--calls",type=int,default=10);a=p.parse_args()
    cfg=env(Path(a.env_file)); key=cfg.get("DEEPSEEK_API_KEY","");
    if not key: raise SystemExit("provider_not_configured")
    pkt=packet(Path(a.packet_sample));root=Path(a.project_root).resolve();out=Path(a.output_dir);chain=json.loads(__import__('urllib.request').request.urlopen("http://127.0.0.1:18080/agent-intent/v0/manifest-chain",timeout=5).read())
    bench=BenchmarkLedger(root/"ops/agent_bridge/model_benchmarks/model_packet_benchmark_ledger_v1.jsonl");dry=AgentIntentDryRunLedger(root/"ops/agent_bridge/agent_intents")
    rows=[];intents=[];results=[]
    for i in range(a.calls):
        symbol=("BTCUSDT","ETHUSDT")[i%2];horizon=("micro","scalp")[(i//2)%2]
        row,record=benchmark_once(pkt,chain,api_key=key,base_url=cfg.get("DEEPSEEK_BASE_URL","https://api.deepseek.com"),model=cfg.get("DEEPSEEK_CENTRAL_MODEL_ID","deepseek-chat"),symbol=symbol,horizon=horizon,index=i)
        bench.append(row);rows.append(row)
        if record: dry.append(record);intents.append(record.intent.model_dump(mode="json"));results.append(record.result.model_dump(mode="json"))
        print(json.dumps({"call":i+1,"status":row["schema_status"],"dry_run":row["dry_run_validation_status"]}),flush=True)
    prompts=[{"model_call_id":r["model_call_id"],"packet_ref":r["packet_ref"],"prompt_hash":r["prompt_hash"],"request_token_estimate":r["request_token_estimate"],"redacted":True} for r in rows]
    out.mkdir(parents=True,exist_ok=True);(out/"model_packet_prompts_p24_redacted.json").write_text(json.dumps({"schema_version":"p24-redacted-prompts/v0","items":prompts},indent=2),encoding="utf-8")
    write_jsonl(out/"model_packet_outputs_p24_sanitized.jsonl",[{k:v for k,v in r.items() if k in {"model_call_id","provider","model","parse_status","schema_status","sanitized_output","error","safety"}} for r in rows]);write_jsonl(out/"model_packet_benchmark_ledger_p24.jsonl",rows);write_jsonl(out/"agent_intent_from_model_p24.jsonl",intents);write_jsonl(out/"dry_run_results_from_model_p24.jsonl",results)
if __name__=="__main__":main()
