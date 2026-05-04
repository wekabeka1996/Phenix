from apps.reference.config_loader import ConfigLoader


def test_no_legacy_notional_first_sizing_keys_in_effective_config():
    cfg = ConfigLoader().load_config()
    flat = ConfigLoader._flatten_leaf_paths(cfg.model_dump())

    forbidden_substrings = (
        "percent_equity",
        "fixed_notional_usd",
        "fixed_qty",
        "risk_contract_v1",
        "sizing.mode",
    )
    hits = [k for k in flat.keys() if any(s in k for s in forbidden_substrings)]
    assert hits == []


def test_instruments_have_margin_first_ssot_fields():
    cfg = ConfigLoader().load_config()
    # active symbols are derived from strategies_registry.assignments
    active = list(cfg.strategies_registry.assignments.keys()) if cfg.strategies_registry else list(cfg.instruments.keys())
    for sym in active:
        inst = cfg.instruments[sym]
        assert inst.execution.margin_mode == "isolated"
        assert inst.execution.target_leverage >= 1
        assert 0.0 < float(inst.sizing.margin_pct) <= 1.0

