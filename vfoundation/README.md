# vFoundation (FSM-LLM Federated Modular Architecture)

Production-ready skeleton implementing FSM core, Meta-FSM, routing hot/warm/cold, DR (WAL+snapshots+replay),
XAI (why/why_explain_ref), Observability, Security (ed25519), CLI, 3-domain reference app, tests, and CI.

## Quickstart
```bash
python -m venv .venv && . .venv/bin/activate
pip install -U pip
pip install -e .[redis]
make dev
uvicorn apps.reference.api.main:app --reload --port 8000
# In another terminal:
python -m cli.vfound simulate flow examples/flow.yaml
```

## CLI
```bash
python -m cli.vfound --help
```

## DR/Replay Demo
1. Run API.
2. Trigger sample flow.
3. Call `GET /replay/{rid}` to dry-run reconstruction.

See `docs/` and `tests/` for details.
