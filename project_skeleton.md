# Структура проекту

```text
Phenix/
├── apps
│   ├── reference
│   │   ├── adapters
│   │   │   ├── __init__.py
│   │   │   ├── binance_adapter.py
│   │   │   ├── binance_ws_client.py
│   │   │   ├── contract.py
│   │   │   ├── execution_adapter.py
│   │   │   └── simulated_adapter.py
│   │   ├── api
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   └── metrics.py
│   │   ├── backtest
│   │   │   ├── __init__.py
│   │   │   └── symbol_filter.py
│   │   ├── bootstrap
│   │   │   ├── schemas
│   │   │   │   └── startup_seed_status_v1.json
│   │   │   ├── async_runtime.py
│   │   │   ├── domain_builder.py
│   │   │   ├── preflight.py
│   │   │   ├── runtime_analytics_restore.py
│   │   │   ├── startup_basis_hydrator.py
│   │   │   ├── startup_hydration_planner.py
│   │   │   └── startup_warmup.py
│   │   ├── config
│   │   │   ├── domains
│   │   │   │   ├── __init__.py
│   │   │   │   ├── _aggregator.py
│   │   │   │   ├── decision_making.py
│   │   │   │   ├── execution_position.py
│   │   │   │   ├── feature_engineering.py
│   │   │   │   ├── objective_engine.py
│   │   │   │   ├── position_tracking.py
│   │   │   │   ├── risk_management.py
│   │   │   │   ├── shadow_telemetry.py
│   │   │   │   └── ta_features.py
│   │   │   ├── shared
│   │   │   │   ├── __init__.py
│   │   │   │   ├── atoms.py
│   │   │   │   ├── decimal_utils.py
│   │   │   │   ├── enums.py
│   │   │   │   └── instruments.py
│   │   │   ├── strategies
│   │   │   │   ├── __init__.py
│   │   │   │   ├── aurora.py
│   │   │   │   ├── common.py
│   │   │   │   ├── llm_microstructure.py
│   │   │   │   ├── md_amr.py
│   │   │   │   └── mean_reversion.py
│   │   │   ├── system
│   │   │   │   ├── __init__.py
│   │   │   │   ├── market_data.py
│   │   │   │   ├── observability.py
│   │   │   │   └── ops.py
│   │   │   └── __init__.py
│   │   ├── contracts
│   │   │   ├── quadratic_rollout.py
│   │   │   ├── reject_reasons.py
│   │   │   ├── runtime_analytics_restore.py
│   │   │   ├── runtime_bar_identity.py
│   │   │   ├── runtime_gap_policy.py
│   │   │   ├── runtime_readiness.py
│   │   │   ├── runtime_regime_layers.py
│   │   │   ├── strategy_compatibility_matrix.py
│   │   │   └── trade_intent_envelope.py
│   │   ├── core
│   │   │   ├── time
│   │   │   │   ├── __init__.py
│   │   │   │   └── clock.py
│   │   │   ├── types
│   │   │   │   └── regime_types.py
│   │   │   └── __init__.py
│   │   ├── dictionaries
│   │   │   ├── global_v2_2.yaml
│   │   │   └── verb_registry_v1.yaml
│   │   ├── domains
│   │   │   ├── account_balance
│   │   │   │   ├── __init__.py
│   │   │   │   └── account_connector.py
│   │   │   ├── alpha_search
│   │   │   │   ├── judge
│   │   │   │   │   ├── chamber
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── admissibility.py
│   │   │   │   │   │   └── chamber_aggregator.py
│   │   │   │   │   ├── envelope
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   └── envelope_assembler.py
│   │   │   │   │   ├── experts
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── expert_output_bridge.py
│   │   │   │   │   │   ├── feature_neutrals_expert.py
│   │   │   │   │   │   └── signal_weights_expert.py
│   │   │   │   │   ├── policy_cortex
│   │   │   │   │   │   ├── schemas
│   │   │   │   │   │   │   └── policy_cortex_annotation_v1.json
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── cortex_evaluator.py
│   │   │   │   │   │   ├── evidence_models.py
│   │   │   │   │   │   ├── policy_classifier.py
│   │   │   │   │   │   ├── surface_evidence_v1.json
│   │   │   │   │   │   ├── surface_key_builder.py
│   │   │   │   │   │   └── surface_registry.py
│   │   │   │   │   ├── review
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── cli.py
│   │   │   │   │   │   ├── config_models.py
│   │   │   │   │   │   ├── config_schema_validator.py
│   │   │   │   │   │   ├── engine.py
│   │   │   │   │   │   ├── loaders.py
│   │   │   │   │   │   └── report_writer.py
│   │   │   │   │   ├── schemas
│   │   │   │   │   │   ├── chamber_aggregate_v1.json
│   │   │   │   │   │   ├── expert_output_v1.json
│   │   │   │   │   │   ├── judge_evidence_envelope_v1.json
│   │   │   │   │   │   ├── judge_verdict_v1.json
│   │   │   │   │   │   └── shadow_entry_plan_v1.json
│   │   │   │   │   ├── simulator
│   │   │   │   │   │   ├── schemas
│   │   │   │   │   │   │   ├── calibration_dataset_v1.json
│   │   │   │   │   │   │   ├── outcome_input_v1.json
│   │   │   │   │   │   │   └── summary_report_v1.json
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── calibration_dataset_writer.py
│   │   │   │   │   │   ├── cli.py
│   │   │   │   │   │   ├── config_models.py
│   │   │   │   │   │   ├── config_schema_validator.py
│   │   │   │   │   │   ├── disagreement_analyzer.py
│   │   │   │   │   │   ├── expert_accuracy_reporter.py
│   │   │   │   │   │   ├── fee_slippage_calculator.py
│   │   │   │   │   │   ├── simulator_engine.py
│   │   │   │   │   │   └── summary_report_writer.py
│   │   │   │   │   ├── verdict
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   └── verdict_synthesizer.py
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── config_models.py
│   │   │   │   │   ├── contracts.py
│   │   │   │   │   ├── identity.py
│   │   │   │   │   ├── shadow_entry_plan.py
│   │   │   │   │   ├── shadow_simulator.py
│   │   │   │   │   └── simulation_models.py
│   │   │   │   ├── models
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── aurora_adapter.py
│   │   │   │   │   ├── mean_reversion.py
│   │   │   │   │   ├── momentum.py
│   │   │   │   │   └── volatility.py
│   │   │   │   ├── runtime
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── backpressure.py
│   │   │   │   │   ├── config_resolver.py
│   │   │   │   │   ├── contracts.py
│   │   │   │   │   ├── executor.py
│   │   │   │   │   ├── feature_mirror_writer.py
│   │   │   │   │   ├── health.py
│   │   │   │   │   ├── hot_reload.py
│   │   │   │   │   ├── ingest.py
│   │   │   │   │   ├── launcher.py
│   │   │   │   │   ├── logger_factory.py
│   │   │   │   │   ├── override_allowlist.py
│   │   │   │   │   ├── reporting.py
│   │   │   │   │   ├── runbook.py
│   │   │   │   │   ├── scenario_manager.py
│   │   │   │   │   ├── scenario_worker.py
│   │   │   │   │   └── shadow_book.py
│   │   │   │   ├── schemas
│   │   │   │   │   └── alpha_score_calculated_v1.json
│   │   │   │   ├── __init__.py
│   │   │   │   ├── alpha_model.py
│   │   │   │   ├── backtest_plugin.py
│   │   │   │   ├── config_models.py
│   │   │   │   ├── domain_dict.json
│   │   │   │   └── ensemble.py
│   │   │   ├── data_recorder
│   │   │   │   ├── __init__.py
│   │   │   │   └── recorder.py
│   │   │   ├── decision_making
│   │   │   │   ├── contracts
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── boundary_mappers.py
│   │   │   │   │   ├── boundary_models.py
│   │   │   │   │   ├── core_models.py
│   │   │   │   │   ├── domain_dict.json
│   │   │   │   │   ├── normalized_reject_reasons.py
│   │   │   │   │   ├── schemas.py
│   │   │   │   │   ├── schemas_decision_blocked.py
│   │   │   │   │   └── why_codes.py
│   │   │   │   ├── core
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── config_resolver.py
│   │   │   │   │   ├── config_spec.py
│   │   │   │   │   ├── context.py
│   │   │   │   │   ├── event_handlers.py
│   │   │   │   │   ├── facade.py
│   │   │   │   │   ├── runtime_readiness.py
│   │   │   │   │   └── state.py
│   │   │   │   ├── gates
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── arbitration_gate.py
│   │   │   │   │   ├── execution_gate.py
│   │   │   │   │   ├── exposure_gate.py
│   │   │   │   │   ├── flip_gate.py
│   │   │   │   │   ├── inception_filter.py
│   │   │   │   │   ├── low_vol_cost_floor.py
│   │   │   │   │   ├── objective_gate_evaluator.py
│   │   │   │   │   ├── qos_gate.py
│   │   │   │   │   ├── qos_rate_control.py
│   │   │   │   │   ├── readiness_gates.py
│   │   │   │   │   ├── regime_loss_embargo.py
│   │   │   │   │   ├── regime_smoother.py
│   │   │   │   │   ├── risk_gate.py
│   │   │   │   │   ├── risk_skew_gate.py
│   │   │   │   │   ├── safety_gate.py
│   │   │   │   │   ├── safety_gates.py
│   │   │   │   │   ├── ttl_gate.py
│   │   │   │   │   └── warmup_gate.py
│   │   │   │   ├── gateway
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── chain.py
│   │   │   │   │   ├── protocol.py
│   │   │   │   │   └── strategy_gateway.py
│   │   │   │   ├── intent
│   │   │   │   │   ├── schemas
│   │   │   │   │   │   ├── alpha_scores_aggregated_v1.json
│   │   │   │   │   │   ├── decision_blocked_v1.json
│   │   │   │   │   │   ├── gate_chain_trace_v1.json
│   │   │   │   │   │   ├── quadratic_decision_trace_v1.json
│   │   │   │   │   │   ├── regime_shift_suspected_v1.json
│   │   │   │   │   │   ├── str_decision_blocked_v1.json
│   │   │   │   │   │   └── trade_intent_v1.json
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── builder.py
│   │   │   │   │   ├── builder_policy.py
│   │   │   │   │   ├── builder_validators.py
│   │   │   │   │   ├── emitter.py
│   │   │   │   │   ├── flip.py
│   │   │   │   │   ├── payload_assembler.py
│   │   │   │   │   ├── reject_wal.py
│   │   │   │   │   └── truth_artifacts.py
│   │   │   │   ├── observability
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── dashboard.py
│   │   │   │   │   └── log_adapter.py
│   │   │   │   ├── primitives
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── operational_mode.py
│   │   │   │   │   └── position_queries.py
│   │   │   │   ├── schemas
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   └── control_decision.py
│   │   │   │   ├── __init__.py
│   │   │   │   ├── aurora_handler.py
│   │   │   │   ├── authority_bridge.py
│   │   │   │   ├── decision_making.py
│   │   │   │   ├── dm_log_adapter.py
│   │   │   │   ├── entry_plan.py
│   │   │   │   ├── md_amr_handler.py
│   │   │   │   ├── mean_reversion_handler.py
│   │   │   │   ├── normalized_reject_reasons.py
│   │   │   │   ├── quadratic_scoring_kernel.py
│   │   │   │   ├── readiness_gates.py
│   │   │   │   └── why_codes.py
│   │   │   ├── exchange_filters
│   │   │   │   ├── __init__.py
│   │   │   │   ├── contracts.py
│   │   │   │   └── validator.py
│   │   │   ├── execution_position
│   │   │   │   ├── adapters
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── adapter_init.py
│   │   │   │   │   ├── async_scheduling.py
│   │   │   │   │   ├── config_resolver.py
│   │   │   │   │   └── watchdog.py
│   │   │   │   ├── bootstrapping
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   └── leverage_bootstrapper.py
│   │   │   │   ├── contract_layer
│   │   │   │   │   ├── schemas
│   │   │   │   │   │   └── common
│   │   │   │   │   │       ├── base_order_identity_v1.json
│   │   │   │   │   │       └── peak_giveback_snapshot_v1.json
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── emitted_surface_audit.py
│   │   │   │   │   ├── event_names.py
│   │   │   │   │   ├── numeric.py
│   │   │   │   │   ├── reasons.py
│   │   │   │   │   ├── terminal_order_contracts.py
│   │   │   │   │   ├── trade_executed_contracts.py
│   │   │   │   │   ├── trade_intent_reject_contracts.py
│   │   │   │   │   └── typed_results.py
│   │   │   │   ├── docs
│   │   │   │   │   ├── compatibility_stub_ledger.json
│   │   │   │   │   ├── compatibility_stub_rewire_audit.json
│   │   │   │   │   └── dead_code_inventory.json
│   │   │   │   ├── flows
│   │   │   │   │   ├── close
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── close_executor.py
│   │   │   │   │   │   ├── close_producer_bridge.py
│   │   │   │   │   │   ├── close_replay_determinism.py
│   │   │   │   │   │   ├── close_replay_from_order_log.py
│   │   │   │   │   │   ├── close_restart_state_separation.py
│   │   │   │   │   │   ├── close_submission_adapter.py
│   │   │   │   │   │   ├── fsm_close.py
│   │   │   │   │   │   ├── reconcile_close_cancel_bridge.py
│   │   │   │   │   │   └── tracked_close_teardown_cancel_bridge.py
│   │   │   │   │   ├── manage
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── bracket_health.py
│   │   │   │   │   │   ├── bracket_manager.py
│   │   │   │   │   │   ├── bracket_math.py
│   │   │   │   │   │   ├── bracket_ownership.py
│   │   │   │   │   │   ├── fsm_manage.py
│   │   │   │   │   │   ├── manage_max_hold_close_bridge.py
│   │   │   │   │   │   └── pending_brackets_wal.py
│   │   │   │   │   ├── open
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── entry_manager.py
│   │   │   │   │   │   ├── fsm_open.py
│   │   │   │   │   │   ├── intent_router.py
│   │   │   │   │   │   ├── open_dispatch_adapter.py
│   │   │   │   │   │   ├── open_executor.py
│   │   │   │   │   │   ├── open_submission_adapter.py
│   │   │   │   │   │   └── trade_intent_open_intake.py
│   │   │   │   │   └── __init__.py
│   │   │   │   ├── guardian
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── cancel_bridge_utils.py
│   │   │   │   │   ├── cancel_submission_adapter.py
│   │   │   │   │   ├── guardian_background_orphan_cancel_bridge.py
│   │   │   │   │   ├── guardian_old_bracket_cleanup_bridge.py
│   │   │   │   │   ├── guardian_pre_close_cleanup_bridge.py
│   │   │   │   │   ├── guardian_reconcile_cancel_bridge.py
│   │   │   │   │   ├── idempotent_cancel.py
│   │   │   │   │   └── order_guardian.py
│   │   │   │   ├── guards
│   │   │   │   │   ├── bootstrapping
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   └── leverage_bootstrapper.py
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── exposure_guard.py
│   │   │   │   │   ├── exposure_manager.py
│   │   │   │   │   ├── leverage_config.py
│   │   │   │   │   ├── leverage_service.py
│   │   │   │   │   ├── qty_normalizer.py
│   │   │   │   │   └── soft_clip.py
│   │   │   │   ├── infra
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── ledger_store_adapter.py
│   │   │   │   │   └── order_ledger.py
│   │   │   │   ├── orchestration
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── event_handlers.py
│   │   │   │   │   └── fill_ingress_coordinator.py
│   │   │   │   ├── schemas
│   │   │   │   │   ├── bracket_placement_failed_v1.json
│   │   │   │   │   ├── cmd_external_open_request_v1.json
│   │   │   │   │   ├── cmd_open_v1.json
│   │   │   │   │   ├── cmd_position_policy_sidecar_close_request_v1.json
│   │   │   │   │   ├── dec_open_v1.json
│   │   │   │   │   ├── execution_close_reconciled_v1.json
│   │   │   │   │   ├── execution_divergence_detected_v1.json
│   │   │   │   │   ├── execution_guard_blocked_v1.json
│   │   │   │   │   ├── execution_tidy_performed_v1.json
│   │   │   │   │   ├── exit_match_attempted_v1.json
│   │   │   │   │   ├── exit_match_failed_v1.json
│   │   │   │   │   ├── exposure_summary_updated_v1.json
│   │   │   │   │   ├── order_fill_v1.json
│   │   │   │   │   ├── order_placed_v1.json
│   │   │   │   │   ├── order_rejected_v1.json
│   │   │   │   │   ├── order_state_changed_v1.json
│   │   │   │   │   ├── pending_brackets_cleared_v1.json
│   │   │   │   │   ├── pending_brackets_stored_v1.json
│   │   │   │   │   ├── position_closed_v1.json
│   │   │   │   │   ├── position_policy_sidecar_action_skipped_v1.json
│   │   │   │   │   ├── position_policy_sidecar_close_request_state_v1.json
│   │   │   │   │   ├── position_policy_sidecar_evaluated_v1.json
│   │   │   │   │   ├── position_policy_sidecar_fee_aware_shadow_arm_state_v1.json
│   │   │   │   │   ├── position_policy_sidecar_mode_active_v1.json
│   │   │   │   │   ├── position_policy_sidecar_recommended_v1.json
│   │   │   │   │   ├── position_policy_sidecar_scores_v1.json
│   │   │   │   │   ├── position_policy_sidecar_suppressed_v1.json
│   │   │   │   │   └── symbol_tidy_v1.json
│   │   │   │   ├── sidecar
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── position_policy_mediator.py
│   │   │   │   │   └── position_policy_sidecar.py
│   │   │   │   ├── state
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── authoritative_restore_apply.py
│   │   │   │   │   ├── ledger_store_adapter.py
│   │   │   │   │   ├── order_index.py
│   │   │   │   │   ├── order_ledger.py
│   │   │   │   │   ├── restore_artifact.py
│   │   │   │   │   ├── startup_reconstruction.py
│   │   │   │   │   ├── startup_truth_orchestrator.py
│   │   │   │   │   └── truth_hardening.py
│   │   │   │   ├── support
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── stopprice_validation.py
│   │   │   │   │   └── utils_event_bus.py
│   │   │   │   ├── telemetry
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── aurora_log_adapter.py
│   │   │   │   │   ├── close_shadow_comparison.py
│   │   │   │   │   ├── drift_monitor.py
│   │   │   │   │   ├── health_metrics.py
│   │   │   │   │   ├── intent_boundary_audit.py
│   │   │   │   │   ├── metrics_aggregator.py
│   │   │   │   │   └── metrics_collector.py
│   │   │   │   ├── __init__.py
│   │   │   │   ├── adapter_init.py
│   │   │   │   ├── async_scheduling.py
│   │   │   │   ├── aurora_log_adapter.py
│   │   │   │   ├── authoritative_restore_apply.py
│   │   │   │   ├── bracket_health.py
│   │   │   │   ├── bracket_manager.py
│   │   │   │   ├── bracket_math.py
│   │   │   │   ├── bracket_ownership.py
│   │   │   │   ├── cancel_bridge_utils.py
│   │   │   │   ├── cancel_submission_adapter.py
│   │   │   │   ├── close_executor.py
│   │   │   │   ├── close_producer_bridge.py
│   │   │   │   ├── close_submission_adapter.py
│   │   │   │   ├── config_resolver.py
│   │   │   │   ├── contracts.py
│   │   │   │   ├── domain_dict.json
│   │   │   │   ├── drift_monitor.py
│   │   │   │   ├── entry_manager.py
│   │   │   │   ├── event_handlers.py
│   │   │   │   ├── exposure_guard.py
│   │   │   │   ├── exposure_manager.py
│   │   │   │   ├── fill_ingress_coordinator.py
│   │   │   │   ├── fsm.py
│   │   │   │   ├── fsm_close.py
│   │   │   │   ├── fsm_manage.py
│   │   │   │   ├── fsm_open.py
│   │   │   │   ├── guardian_background_orphan_cancel_bridge.py
│   │   │   │   ├── guardian_old_bracket_cleanup_bridge.py
│   │   │   │   ├── guardian_pre_close_cleanup_bridge.py
│   │   │   │   ├── guardian_reconcile_cancel_bridge.py
│   │   │   │   ├── health_metrics.py
│   │   │   │   ├── idempotent_cancel.py
│   │   │   │   ├── intent_boundary_audit.py
│   │   │   │   ├── intent_router.py
│   │   │   │   ├── ledger_store_adapter.py
│   │   │   │   ├── leverage_config.py
│   │   │   │   ├── leverage_service.py
│   │   │   │   ├── manage_max_hold_close_bridge.py
│   │   │   │   ├── metrics_aggregator.py
│   │   │   │   ├── metrics_collector.py
│   │   │   │   ├── open_dispatch_adapter.py
│   │   │   │   ├── open_executor.py
│   │   │   │   ├── open_submission_adapter.py
│   │   │   │   ├── order_guardian.py
│   │   │   │   ├── order_index.py
│   │   │   │   ├── order_ledger.py
│   │   │   │   ├── pending_brackets_wal.py
│   │   │   │   ├── position_policy_mediator.py
│   │   │   │   ├── position_policy_sidecar.py
│   │   │   │   ├── qty_normalizer.py
│   │   │   │   ├── reasons.py
│   │   │   │   ├── reconcile_close_cancel_bridge.py
│   │   │   │   ├── restore_artifact.py
│   │   │   │   ├── soft_clip.py
│   │   │   │   ├── startup_reconstruction.py
│   │   │   │   ├── startup_truth_orchestrator.py
│   │   │   │   ├── stopprice_validation.py
│   │   │   │   ├── terminal_order_contracts.py
│   │   │   │   ├── tracked_close_teardown_cancel_bridge.py
│   │   │   │   ├── trade_executed_contracts.py
│   │   │   │   ├── trade_intent_open_intake.py
│   │   │   │   ├── trade_intent_reject_contracts.py
│   │   │   │   ├── truth_hardening.py
│   │   │   │   ├── utils.py
│   │   │   │   ├── utils_event_bus.py
│   │   │   │   └── watchdog.py
│   │   │   ├── feature_engineering
│   │   │   │   ├── schemas
│   │   │   │   │   ├── cmd_process_strategy_v1.json
│   │   │   │   │   ├── features_calculated_v1.json
│   │   │   │   │   ├── process_strategy_blocked_v1.json
│   │   │   │   │   └── tick_features_calculated_v1.json
│   │   │   │   ├── __init__.py
│   │   │   │   ├── bar_resampler.py
│   │   │   │   ├── calculation_engine.py
│   │   │   │   ├── contracts.py
│   │   │   │   ├── domain_dict.json
│   │   │   │   ├── feature_engineering.py
│   │   │   │   ├── indicators.py
│   │   │   │   ├── large_trade_imbalance.py
│   │   │   │   ├── macro_sync_resampler.py
│   │   │   │   ├── md_amr_strategy.py
│   │   │   │   ├── mean_reversion_strategy.py
│   │   │   │   ├── pillar_backfill.py
│   │   │   │   ├── pillar_indicators.py
│   │   │   │   ├── price_motion.py
│   │   │   │   ├── regime_mapping.py
│   │   │   │   ├── types.py
│   │   │   │   └── utils.py
│   │   │   ├── inflight_reconcile
│   │   │   │   ├── __init__.py
│   │   │   │   ├── config.py
│   │   │   │   └── reconciler.py
│   │   │   ├── market_data
│   │   │   │   ├── __init__.py
│   │   │   │   ├── bar_aggregator.py
│   │   │   │   ├── domain_dict.json
│   │   │   │   ├── market_data_connector.py
│   │   │   │   ├── proxy.py
│   │   │   │   ├── websocket_aggregator.py
│   │   │   │   └── worker.py
│   │   │   ├── neocortex
│   │   │   │   ├── config
│   │   │   │   │   ├── ingest.yaml
│   │   │   │   │   ├── neuro.yaml
│   │   │   │   │   ├── regime_oracle_reward.yaml
│   │   │   │   │   ├── replay.yaml
│   │   │   │   │   └── system.yaml
│   │   │   │   ├── contracts
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── causal_time.py
│   │   │   │   │   ├── control_decision.py
│   │   │   │   │   ├── decision_outcome_ledger.py
│   │   │   │   │   ├── failure_taxonomy.py
│   │   │   │   │   └── observation_envelope.py
│   │   │   │   ├── experiments
│   │   │   │   │   ├── 00_oracle_pnl_analysis.py
│   │   │   │   │   ├── 01_state_reconstruction.py
│   │   │   │   │   ├── 02_action_decoder_simulation.py
│   │   │   │   │   ├── 03_reward_decomposition_sim.py
│   │   │   │   │   ├── 04_async_checkpoint_reload.py
│   │   │   │   │   ├── 05_lstm_memory_isolation_sim.py
│   │   │   │   │   ├── 06_aurora_sim_env.py
│   │   │   │   │   ├── 07_vae_latent_space_sim.py
│   │   │   │   │   ├── 08_decision_ledger_dataset_prep.py
│   │   │   │   │   ├── 09_dumb_baseline_eval.py
│   │   │   │   │   └── _decision_ledger_baseline.py
│   │   │   │   ├── logic
│   │   │   │   │   ├── amygdala
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   └── valuation.py
│   │   │   │   │   ├── brain
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── baseline_inference.py
│   │   │   │   │   │   ├── bridge.py
│   │   │   │   │   │   ├── core.py
│   │   │   │   │   │   ├── vae.py
│   │   │   │   │   │   ├── worker.py
│   │   │   │   │   │   └── world_model.py
│   │   │   │   │   ├── datasets
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── contracts.py
│   │   │   │   │   │   ├── cutover.py
│   │   │   │   │   │   ├── hygiene.py
│   │   │   │   │   │   └── time_provenance.py
│   │   │   │   │   ├── evaluation
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── contracts.py
│   │   │   │   │   │   └── evaluator.py
│   │   │   │   │   ├── evidence_collection
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── collector.py
│   │   │   │   │   │   ├── contracts.py
│   │   │   │   │   │   ├── summary.py
│   │   │   │   │   │   └── writer.py
│   │   │   │   │   ├── gates
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   └── shadow.py
│   │   │   │   │   ├── ingest
│   │   │   │   │   │   ├── parsers
│   │   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   │   ├── core_parser.py
│   │   │   │   │   │   │   ├── feature_parser.py
│   │   │   │   │   │   │   └── order_parser.py
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── multi_tailer.py
│   │   │   │   │   │   ├── normalizer.py
│   │   │   │   │   │   ├── observation.py
│   │   │   │   │   │   ├── parser.py
│   │   │   │   │   │   ├── state_aggregator_v2.py
│   │   │   │   │   │   ├── tailer.py
│   │   │   │   │   │   └── wal_replayer.py
│   │   │   │   │   ├── ledger
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   └── decision_outcome_ledger.py
│   │   │   │   │   ├── memory
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── buffer.py
│   │   │   │   │   │   └── graph.py
│   │   │   │   │   ├── reward
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── feature_buffer.py
│   │   │   │   │   │   ├── regime_labeler.py
│   │   │   │   │   │   └── reward_calculator.py
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── dreamer.py
│   │   │   │   │   ├── failure_ledger.py
│   │   │   │   │   └── telemetry.py
│   │   │   │   ├── PPO
│   │   │   │   │   └── ppo_library_v2
│   │   │   │   │       ├── examples
│   │   │   │   │       │   ├── 01_train_cartpole_single.py
│   │   │   │   │       │   └── 02_train_cartpole_vectorized.py
│   │   │   │   │       └── ppo_system
│   │   │   │   │           ├── core
│   │   │   │   │           │   └── dataclasses.py
│   │   │   │   │           ├── learning
│   │   │   │   │           │   ├── __init__.py
│   │   │   │   │           │   ├── buffer.py
│   │   │   │   │           │   ├── controllers.py
│   │   │   │   │           │   └── updater.py
│   │   │   │   │           ├── models
│   │   │   │   │           │   ├── __init__.py
│   │   │   │   │           │   ├── actor_critic_lstm.py
│   │   │   │   │           │   └── base_model.py
│   │   │   │   │           ├── utils
│   │   │   │   │           │   ├── __init__.py
│   │   │   │   │           │   ├── logging.py
│   │   │   │   │           │   ├── safety.py
│   │   │   │   │           │   └── seed.py
│   │   │   │   │           ├── __init__.py
│   │   │   │   │           ├── agent.py
│   │   │   │   │           └── training_loop.py
│   │   │   │   ├── schemas
│   │   │   │   │   └── neocortex_decision_logged_v1.json
│   │   │   │   ├── transport
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── adapter.py
│   │   │   │   │   └── authority_bridge.py
│   │   │   │   ├── __init__.py
│   │   │   │   ├── config_models.py
│   │   │   │   ├── domain.yaml
│   │   │   │   └── main.py
│   │   │   ├── new_domain_test
│   │   │   │   ├── __init__.py
│   │   │   │   └── new_domain_test.py
│   │   │   ├── objective_engine
│   │   │   │   ├── components
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── _common.py
│   │   │   │   │   ├── behavior.py
│   │   │   │   │   ├── cost.py
│   │   │   │   │   ├── edge.py
│   │   │   │   │   ├── execution.py
│   │   │   │   │   ├── information.py
│   │   │   │   │   └── risk.py
│   │   │   │   ├── schemas
│   │   │   │   │   └── objective_realized_v1.json
│   │   │   │   ├── __init__.py
│   │   │   │   ├── adapters.py
│   │   │   │   ├── components.py
│   │   │   │   ├── engine.py
│   │   │   │   ├── normalizers.py
│   │   │   │   ├── posttrade_evaluator.py
│   │   │   │   ├── pretrade_kernel.py
│   │   │   │   ├── realized_types.py
│   │   │   │   ├── runtime.py
│   │   │   │   ├── snapshot_registry.py
│   │   │   │   └── types.py
│   │   │   ├── position_tracking
│   │   │   │   ├── schemas
│   │   │   │   │   ├── portfolio_state_v1.json
│   │   │   │   │   └── trade_executed_v1.json
│   │   │   │   ├── __init__.py
│   │   │   │   ├── domain_dict.json
│   │   │   │   └── position_tracking.py
│   │   │   ├── regime_allowlist
│   │   │   │   ├── __init__.py
│   │   │   │   └── contract.py
│   │   │   ├── regime_detector
│   │   │   │   ├── schemas
│   │   │   │   │   └── regime_detected_v1.json
│   │   │   │   ├── __init__.py
│   │   │   │   ├── domain_dict.json
│   │   │   │   └── regime_detector.py
│   │   │   ├── risk_management
│   │   │   │   ├── schemas
│   │   │   │   │   └── risk_assessment_v1.json
│   │   │   │   ├── __init__.py
│   │   │   │   ├── daily_gate.py
│   │   │   │   ├── domain_dict.json
│   │   │   │   └── risk_management.py
│   │   │   ├── shadow_telemetry
│   │   │   │   ├── schemas
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   └── decision_ledger_row.py
│   │   │   │   ├── __init__.py
│   │   │   │   ├── contracts.py
│   │   │   │   ├── ipc.py
│   │   │   │   ├── ledger_writer.py
│   │   │   │   ├── main.py
│   │   │   │   ├── main_bridge.py
│   │   │   │   └── snapshot_store.py
│   │   │   ├── snapshot_scheduler
│   │   │   │   ├── __init__.py
│   │   │   │   └── snapshot_scheduler.py
│   │   │   ├── strategies
│   │   │   │   ├── plugins
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── aurora_builtin.py
│   │   │   │   │   ├── llm_microstructure.py
│   │   │   │   │   ├── md_amr.py
│   │   │   │   │   └── mean_reversion.py
│   │   │   │   ├── runtimes
│   │   │   │   │   ├── aurora
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── config_loader.py
│   │   │   │   │   │   ├── decision.py
│   │   │   │   │   │   ├── handler.py
│   │   │   │   │   │   ├── holding_period.py
│   │   │   │   │   │   ├── scoring_helpers.py
│   │   │   │   │   │   └── tpsl.py
│   │   │   │   │   ├── md_amr
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── entry_anchor_artifact.py
│   │   │   │   │   │   └── handler.py
│   │   │   │   │   ├── mean_reversion
│   │   │   │   │   │   ├── __init__.py
│   │   │   │   │   │   ├── handler.py
│   │   │   │   │   │   └── logger.py
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   └── bridge.py
│   │   │   │   ├── __init__.py
│   │   │   │   └── registry.py
│   │   │   ├── system_stress
│   │   │   │   ├── __init__.py
│   │   │   │   └── system_stress_overlay.py
│   │   │   ├── ta_features
│   │   │   │   ├── schemas
│   │   │   │   │   └── ta_features_calculated_v1.json
│   │   │   │   ├── __init__.py
│   │   │   │   ├── bar_buffer.py
│   │   │   │   ├── calculators.py
│   │   │   │   ├── contracts.py
│   │   │   │   ├── domain_dict.json
│   │   │   │   └── ta_features.py
│   │   │   └── __init__.py
│   │   ├── orchestrator
│   │   │   ├── __init__.py
│   │   │   └── utils_event_bus.py
│   │   ├── schemas
│   │   │   ├── order_ack_v1.json
│   │   │   └── order_logger_v1.json
│   │   ├── shared
│   │   │   ├── decision_primitives
│   │   │   │   ├── shields
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── base.py
│   │   │   │   │   ├── context_shield.py
│   │   │   │   │   ├── danger_zone.py
│   │   │   │   │   ├── memory_shield.py
│   │   │   │   │   └── null_shield.py
│   │   │   │   ├── __init__.py
│   │   │   │   ├── aurora_confidence.py
│   │   │   │   ├── aurora_math.py
│   │   │   │   ├── aurora_policy.py
│   │   │   │   ├── entry_plan.py
│   │   │   │   ├── exit_manager.py
│   │   │   │   ├── instrument_quantizer.py
│   │   │   │   ├── scoring_kernel.py
│   │   │   │   ├── sizing_margin_first.py
│   │   │   │   └── tpsl_owner.py
│   │   │   ├── __init__.py
│   │   │   └── types.py
│   │   ├── telemetry
│   │   │   ├── alerts.py
│   │   │   ├── audit_logger.py
│   │   │   ├── metrics.py
│   │   │   ├── order_logger.py
│   │   │   ├── regime_confidence_audit.py
│   │   │   ├── shadow_journal.py
│   │   │   └── trade_lifecycle_logger.py
│   │   ├── utils
│   │   │   ├── __init__.py
│   │   │   ├── accessors.py
│   │   │   └── trading_modes.py
│   │   ├── __init__.py
│   │   ├── config_contract.py
│   │   ├── config_loader.py
│   │   ├── config_models.py
│   │   ├── config_symbols.py
│   │   ├── domain_config.py
│   │   ├── dr_loader.py
│   │   ├── logging_setup.py
│   │   ├── main.py
│   │   ├── numeric_context.py
│   │   ├── retry_scheduler.py
│   │   └── shutdown_coordinator.py
│   └── __init__.py
├── calibrators
│   ├── datasets
│   │   ├── builders
│   │   │   ├── __init__.py
│   │   │   ├── common.py
│   │   │   ├── low_vol_gate_builder.py
│   │   │   ├── objective_stack_builder.py
│   │   │   ├── realized_outcome_builder.py
│   │   │   ├── source_snapshot.py
│   │   │   └── walkforward_manifest_builder.py
│   │   ├── join_key_coverage
│   │   │   ├── audit_summary.json
│   │   │   ├── join_coverage_matrix.json
│   │   │   ├── join_key_census.json
│   │   │   ├── source_inventory.json
│   │   │   └── time_window_alignment.json
│   │   ├── realized_outcome_authority
│   │   │   ├── realized_outcome_source_matrix.json
│   │   │   └── source_authority_decision.json
│   │   ├── runtime_close_coverage
│   │   │   ├── lifecycle_bridge_audit.json
│   │   │   ├── order_log_event_taxonomy.json
│   │   │   ├── unmatched_classification.json
│   │   │   └── unmatched_decision_ledger.json
│   │   ├── runtime_close_coverage_03j
│   │   │   ├── lifecycle_bridge_audit.json
│   │   │   ├── order_log_event_taxonomy.json
│   │   │   ├── unmatched_classification.json
│   │   │   └── unmatched_decision_ledger.json
│   │   ├── __init__.py
│   │   ├── audit_join_key_coverage.py
│   │   ├── audit_realized_outcome_authority.py
│   │   ├── audit_runtime_close_coverage.py
│   │   ├── build_realized_outcome_dataset.py
│   │   ├── build_walkforward_manifest.py
│   │   ├── dataset_surface_inventory.json
│   │   ├── schema_examples.py
│   │   ├── schema_registry.py
│   │   └── schemas.py
│   ├── lifecycle
│   │   └── __init__.py
│   ├── policy_gates
│   │   ├── __init__.py
│   │   ├── build_low_vol_gate_dataset.py
│   │   ├── calibrate_low_vol_cost_floor.py
│   │   ├── calibrate_nrr062_historical.py
│   │   └── calibrate_system_stress_weights.py
│   ├── regimes
│   │   ├── __init__.py
│   │   └── calibrate_aurora_regime_params.py
│   ├── shared
│   │   └── __init__.py
│   ├── strategies
│   │   ├── __init__.py
│   │   ├── build_objective_stack_dataset.py
│   │   ├── calibrate_aurora_signal_weights.py
│   │   ├── calibrate_aurora_thresholds.py
│   │   ├── calibrate_md_amr_weights.py
│   │   ├── calibrate_mean_reversion_params.py
│   │   ├── calibrate_objective_stack.py
│   │   └── run_md_amr_phase2b_aggression_grid.py
│   ├── __init__.py
│   ├── inventory.json
│   ├── smoke_run_03b.py
│   └── validate_smoke_run_03b.py
├── config
│   ├── _schemas
│   │   ├── frozen
│   │   │   └── aurora_trading_20251030.json
│   │   ├── aurora_system.schema.json
│   │   ├── aurora_trading.schema.json
│   │   ├── obs_jobs.schema.json
│   │   ├── ops_dr.schema.json
│   │   ├── ops_monitoring.schema.json
│   │   ├── ops_orchestration.schema.json
│   │   ├── ops_security.schema.json
│   │   ├── ops_testing.schema.json
│   │   ├── portfolio.schema.json
│   │   ├── scalp_system.schema.json
│   │   └── scalp_trading.schema.json
│   ├── alpha_search
│   │   ├── scenario_matrix.yaml
│   │   └── scenario_matrix_v2_backup_20260224.yaml
│   ├── aurora
│   │   ├── archive
│   │   │   └── aurora_phase3_production.yaml
│   │   ├── strategies
│   │   │   ├── aurora.yaml
│   │   │   ├── llm_microstructure.yaml
│   │   │   ├── md_amr.yaml
│   │   │   └── mean_reversion.yaml
│   │   ├── domains.yaml
│   │   ├── instruments.yaml
│   │   ├── observability.yaml
│   │   ├── regime.yaml
│   │   ├── strategies.yaml
│   │   ├── system.yaml
│   │   └── trading.yaml
│   ├── alpha_search.yaml
│   ├── alpha_search_system.yaml
│   ├── judge_review.yaml
│   └── judge_simulator.yaml
├── nacl
│   ├── __init__.py
│   └── signing.py
├── schemas
│   ├── account_update_received_v1.json
│   ├── anchor_updated_v1.json
│   ├── balance_update_received_v1.json
│   ├── bar_closed_v1.json
│   ├── bracket_error_v1.json
│   ├── bracket_order_v1.json
│   ├── decision_trace_emitted_v1.json
│   ├── external_open_request_rejected_v1.json
│   ├── features_price_motion_v1.json
│   ├── htf_bars_imported_v1.json
│   ├── intent_deferred_v1.json
│   ├── market_tick_received_v1.json
│   ├── message_v1.json
│   ├── order_clipped_event_v1.json
│   ├── order_rejected_event_v1.json
│   ├── portfolio_state_v1.json
│   ├── strategy_signal_produced_v1.json
│   ├── system_stress_state_updated_v1.json
│   └── trade_intent_rejected_v1.json
├── scripts
│   ├── analysis
│   │   ├── analyze_alpha_search_log_pnl.py
│   │   ├── analyze_reject_forensics_72h.py
│   │   └── analyze_testnet_transactions_md.py
│   ├── benchmarks
│   │   ├── analyze_alpha_performance.py
│   │   ├── btcusdt_benchmark.py
│   │   ├── multi_day_benchmark.py
│   │   └── real_market_benchmark.py
│   ├── calibration
│   │   └── calibrate_low_vol_cost_floor.py
│   ├── diagnostics
│   │   ├── config_forensics.py
│   │   ├── diagnose_binance_api.py
│   │   ├── fetch_binance_testnet_transactions_md.py
│   │   └── mr_restore_002_probe.py
│   ├── docs_gen
│   │   └── synthesize_ssot_docs.py
│   ├── forensics
│   │   ├── analyze_live_wal_trades.py
│   │   ├── analyze_pnl.py
│   │   ├── analyze_shadow_ladder.py
│   │   ├── aurora_forensic_report.py
│   │   ├── aurora_regime_direction_confidence_ablation_replay_v1.py
│   │   ├── aurora_regime_direction_confidence_replay_audit_v1.py
│   │   ├── aurora_trend_confidence_max_cap_deep_forensic_v1.py
│   │   ├── aurora_trend_down_bar_anatomy_forensic_v1.py
│   │   ├── aurora_trend_down_bd1_eth_stateful_recheck_v1.py
│   │   ├── aurora_trend_down_behavior_search_v2.py
│   │   ├── aurora_trend_down_full_research_sequence_v1.py
│   │   ├── aurora_trend_down_segment_level_entry_search_v1.py
│   │   ├── aurora_trend_failure_localization_forensic_v1.py
│   │   ├── aurora_trend_filter_vs_trend_disabled_replay_v1.py
│   │   ├── aurora_trend_filter_vs_trend_disabled_replay_v1_timeout_diagnostic.py
│   │   ├── aurora_trend_min_activation_forward_replay_v1.py
│   │   ├── aurora_trend_tp_timeout_policy_replay_v1.py
│   │   ├── aurora_trend_up_conf_040_045_shadow_replay_v1.py
│   │   ├── aurora_trend_up_microband_tpsl_timeout_grid_v1.py
│   │   ├── aurora_trend_up_p1_good_bad_entry_separator_v1.py
│   │   ├── binance_testnet_window_audit.py
│   │   ├── btc_eth_clean_trend_regime_edge_replay_v1.py
│   │   ├── build_counterfactuals.py
│   │   ├── build_order_flow_master.py
│   │   ├── explain_lack_of_trades.py
│   │   ├── frozen_boundary_audit.py
│   │   ├── frozen_census_audit.py
│   │   ├── frozen_overclaim_audit.py
│   │   ├── generate_business_report.py
│   │   ├── nrr027_forensic_baseline.py
│   │   ├── nrr027_per_regime_calibrator.py
│   │   ├── nrr027_phase4_replay.py
│   │   ├── nrr062_score_audit.py
│   │   ├── nrr063_trend_up_canary_replay.py
│   │   ├── p0_before_after_validation.py
│   │   ├── post_restart_audit.py
│   │   ├── post_restart_runtime_audit_2026_05_02.py
│   │   ├── replay_rejected_orders.py
│   │   ├── run_replay_experiment_j6s6.py
│   │   ├── run_shadow_simulator.py
│   │   ├── strategist_polarity_lock_validation.py
│   │   └── trend_up_400_410_best_candidate_metric_recheck_v1.py
│   ├── maintenance
│   │   ├── migrate_config_get_calls.py
│   │   ├── remove_failed_tests.py
│   │   └── rename_mean_reversion_1m_to_mean_reversion.py
│   ├── optimization
│   │   └── run_research_optuna.py
│   ├── runners
│   │   └── run_alpha_search_domain.py
│   ├── simulation
│   │   └── neocortex_shadow_simulator.py
│   ├── tmp
│   │   ├── analyze_order_gate_counterfactual_20260428_29.py
│   │   ├── tmp_alpha_search_fee_adjusted_pnl.py
│   │   └── tmp_neocortex_runtime_report.py
│   ├── _compat.py
│   ├── generate_project_dump.py
│   ├── generate_project_skeleton.py
│   ├── phase0_add_quarantine_markers.py
│   └── r7p_shadow_percent_arm_analysis.py
├── Sema_Atom
│   ├── SEMA_ATOM_FC_01A_REPORT_RECONCILIATION.py
│   ├── SEMA_ATOM_FORWARD_COLLECTION_INDEX.json
│   ├── SEMA_ATOM_FORWARD_COLLECTOR.py
│   ├── SEMA_ATOM_POC_02_REAL_LOG_ADAPTER.py
│   ├── SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION.py
│   ├── SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json
│   ├── SEMA_ATOM_POC_03B_STABILITY_FILTER_FULL.py
│   └── SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION.py
├── tools
│   ├── alpha_search
│   │   ├── alpha_search_report.py
│   │   ├── alpha_search_runtime_summary.py
│   │   ├── build_alpha_input.py
│   │   ├── j6_s17_a_policy_cortex_preflight.py
│   │   ├── j6_s17_b_forward_outcome_join.py
│   │   ├── j6_s17_b_readiness_analysis.py
│   │   ├── j6_s17_c1_augment_outcomes.py
│   │   ├── j6_s17_c1_run_shadow_simulator.py
│   │   ├── j6_s17_c1_shadow_outcomes.py
│   │   ├── j6_s17_c2_classifier_hit_miss.py
│   │   └── j6_s17_e_low_tier_diagnostic.py
│   ├── analysis
│   │   ├── analyze_features.py
│   │   ├── analyze_health.py
│   │   ├── analyze_test_results.py
│   │   ├── async_ast_analyzer.py
│   │   ├── bars_regime_analysis.py
│   │   ├── capture_nrr062_fresh_cohort.py
│   │   ├── generate_async_report.py
│   │   ├── md_amr_d1_cohort_analysis.py
│   │   ├── md_amr_integrated_validation.py
│   │   ├── nrr062_frozen_counterfactual_replay_PROMPT9.py
│   │   ├── nrr062_frozen_replay_simple_PROMPT9.py
│   │   ├── nrr062_phase1_case_timestamp_audit_PROMPT11.py
│   │   ├── nrr062_phase2_recorder_coverage_audit_PROMPT11.py
│   │   ├── nrr062_phase4_freeze_recorder_extension_PROMPT11.py
│   │   ├── nrr062_phase5_true_recorder_path_replay_PROMPT11.py
│   │   ├── nrr062_phase_all_corrected_analysis_PROMPT12.py
│   │   ├── nrr062_prompt13_forensics.py
│   │   ├── nrr062_recorder_path_replay_PROMPT10.py
│   │   ├── plot_dataset.py
│   │   └── sl_fill_sensitivity.py
│   ├── backtest
│   │   ├── backtest_diagnostics.py
│   │   └── backtest_summarize.py
│   ├── calibration
│   │   ├── calibrate_aurora_regime_params.py
│   │   ├── calibrate_aurora_signal_weights.py
│   │   ├── calibrate_aurora_thresholds.py
│   │   ├── calibrate_md_amr_weights.py
│   │   ├── calibrate_mean_reversion_params.py
│   │   ├── calibrate_nrr062_historical.py
│   │   ├── calibrate_objective_stack.py
│   │   ├── calibrate_system_stress_weights.py
│   │   └── run_md_amr_phase2b_aggression_grid.py
│   ├── ci_cd
│   │   ├── audit_yaml_loading.py
│   │   ├── compare_run_config_snapshot.py
│   │   ├── inventory_config_defaults.py
│   │   └── validate_configs.py
│   ├── cli
│   │   └── auroractl.py
│   ├── deepseek-terminal-agent
│   │   ├── config
│   │   │   ├── agent.yaml
│   │   │   ├── playbooks.yaml
│   │   │   ├── project_capsule.yaml
│   │   │   └── tool_registry.yaml
│   │   ├── src
│   │   │   └── deepseek_terminal_agent
│   │   │       ├── dashboard
│   │   │       │   ├── __init__.py
│   │   │       │   ├── app.py
│   │   │       │   └── runner.py
│   │   │       ├── sessions
│   │   │       │   ├── __init__.py
│   │   │       │   ├── approval_queue.py
│   │   │       │   ├── artifacts.py
│   │   │       │   ├── chat_runtime.py
│   │   │       │   ├── compressor.py
│   │   │       │   ├── context_builder.py
│   │   │       │   ├── context_codec.py
│   │   │       │   ├── context_conflicts.py
│   │   │       │   ├── context_inspector.py
│   │   │       │   ├── context_loss.py
│   │   │       │   ├── context_units.py
│   │   │       │   ├── decision_ledger.py
│   │   │       │   ├── evidence_bundle.py
│   │   │       │   ├── memory_atoms.py
│   │   │       │   ├── memory_patch.py
│   │   │       │   ├── model_registry.py
│   │   │       │   ├── models.py
│   │   │       │   ├── persistence.py
│   │   │       │   ├── playbooks.py
│   │   │       │   ├── project_capsule.py
│   │   │       │   ├── report_center.py
│   │   │       │   ├── store.py
│   │   │       │   ├── subagents.py
│   │   │       │   ├── task_router.py
│   │   │       │   ├── token_budget.py
│   │   │       │   ├── tool_policy.py
│   │   │       │   └── tool_registry.py
│   │   │       ├── __init__.py
│   │   │       ├── agent_loop.py
│   │   │       ├── cli.py
│   │   │       ├── config.py
│   │   │       ├── deepseek_client.py
│   │   │       ├── logging_utils.py
│   │   │       ├── safety.py
│   │   │       └── terminal_tool.py
│   │   ├── docker-compose.yml
│   │   ├── fix_tests.py
│   │   ├── refactor.py
│   │   ├── refactor_chat_js.py
│   │   ├── refactor_js.py
│   │   ├── run_tests.py
│   │   └── write_test.py
│   ├── dev
│   │   └── snapshot_config_models_public_surface.py
│   ├── diagnostics
│   │   ├── check_orders.py
│   │   ├── check_positions.py
│   │   ├── diagnose_execution.py
│   │   ├── diagnose_latent.py
│   │   ├── execution_vs_upstream_trace_01.py
│   │   ├── feature_integrity_replay_check.py
│   │   ├── log_audit.py
│   │   ├── measure_api_latency.py
│   │   ├── smoke_tidy_gate.py
│   │   ├── validate_testnet.py
│   │   ├── verify_config.py
│   │   └── verify_flip_config.py
│   ├── docs_gen
│   │   ├── build_project_atlas.py
│   │   ├── config_default_path_map.yaml
│   │   ├── generate_config_default_path_map.py
│   │   ├── generate_config_map.py
│   │   └── generate_trading_config_audit.py
│   ├── forensics
│   │   ├── aurora_runtime_forensic_report.py
│   │   ├── aurora_sensitivity_microgrid_study.py
│   │   ├── aurora_threshold_asymmetry_study.py
│   │   ├── aurora_trend_up_multiplier_study.py
│   │   ├── aurora_trend_up_overlay_study.py
│   │   ├── aurora_trend_up_side_remap_study.py
│   │   ├── aurora_trend_up_strategist_semantics_study.py
│   │   ├── aurora_trend_up_strategist_sweep_study.py
│   │   ├── aurora_two_factor_grid_study.py
│   │   ├── bracket_coverage_report.py
│   │   ├── confidence_calibration.py
│   │   ├── deep_wal_forensics.py
│   │   ├── doge_aurora_180s_study.py
│   │   ├── doge_aurora_300s_study.py
│   │   ├── doge_aurora_900s_study.py
│   │   ├── doge_full_period_study.py
│   │   ├── entry_execution_report.py
│   │   ├── entry_fill_audit.py
│   │   ├── extract_last_trades.py
│   │   ├── forensic_analysis.py
│   │   ├── forensic_analysis_v2.py
│   │   ├── full_surface_calibration.py
│   │   ├── gate_effect_report.py
│   │   ├── gate_fairness_audit.py
│   │   ├── log_forensics_cancel_audit.py
│   │   ├── mr_calibration_from_logs.py
│   │   ├── mr_recorder_regime_alignment_rebuild.py
│   │   ├── mr_signal_surface_audit.py
│   │   ├── pending_entry_counterfactuals.py
│   │   ├── phase6_package1_open_intake_proof_harness.py
│   │   ├── pipeline_counts_report.py
│   │   ├── position_policy_sidecar_validation.py
│   │   ├── post_cancel_price_drift.py
│   │   ├── r1_confidence_latency_audit.py
│   │   ├── r2_flip_gate_unknown_audit.py
│   │   ├── r3_min_regime_confidence_ablation.py
│   │   ├── r4_hold_quality_audit.py
│   │   ├── r5_shadow_hold_protect_study.py
│   │   ├── r6_peak_giveback_cap_study.py
│   │   ├── regime_confidence_near_threshold_audit.py
│   │   ├── rid_duplicates_report.py
│   │   ├── shadow_regime_aurora_calibration.py
│   │   ├── validate_aurora_decision_geometry.py
│   │   └── wal_intent_summary.py
│   ├── maintenance
│   │   ├── ascii_sanitize_repo.py
│   │   ├── autofill_config_defaults_into_yaml.py
│   │   ├── batch_replace_tests.py
│   │   ├── rescue_brain.py
│   │   ├── reset_ppo.py
│   │   ├── rewire_config_models_remove_defaults.py
│   │   ├── sanitize_configs.py
│   │   └── sanitize_repo_bytes.py
│   ├── migrations
│   │   └── dm_split
│   │       ├── 01_collect_inventory.py
│   │       ├── 02_build_rename_plan.py
│   │       ├── 03_audit_dynamic_imports.py
│   │       ├── 04_rewrite_imports.py
│   │       ├── 05_move_files.py
│   │       ├── 06_write_shims.py
│   │       ├── 07_update_yaml_json.py
│   │       ├── 08_verify.py
│   │       ├── audit_imports.py
│   │       └── dm_split_lib.py
│   ├── monitoring
│   │   ├── analyze_wal.py
│   │   ├── extract_equity_free_usdt.py
│   │   ├── live_observability_summary.py
│   │   ├── metrics_summary.py
│   │   ├── obs02_ctx_log_inventory.py
│   │   └── parse_aurora_logs.py
│   ├── objective_calibration
│   │   ├── __init__.py
│   │   ├── dataset.py
│   │   ├── extract_ledger.py
│   │   ├── extract_recorder.py
│   │   ├── extract_wal.py
│   │   ├── features.py
│   │   ├── metrics.py
│   │   ├── overlay.py
│   │   ├── report.py
│   │   └── search.py
│   ├── parquet_contract
│   │   ├── __init__.py
│   │   └── data_contract.py
│   ├── parquet_pipeline
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── actuator_rules.py
│   │   ├── aggregation.py
│   │   ├── audit.py
│   │   ├── discovery.py
│   │   ├── forward_separability.py
│   │   ├── market_structure.py
│   │   ├── policy_tables.py
│   │   ├── regime_grid.py
│   │   ├── stress.py
│   │   ├── tune_presets.py
│   │   └── validate_preset.py
│   ├── regime_calibration
│   │   ├── io.py
│   │   ├── metrics.py
│   │   ├── oracle.py
│   │   └── search.py
│   ├── runtime_forensics_tmp
│   │   ├── build_t3d_all_accepted_replay.py
│   │   ├── t0_runtime_manifest_builder.py
│   │   ├── t1_execution_lifecycle_pnl_forensics.py
│   │   ├── t1_regime_path_forensic.py
│   │   ├── t2_runtime_trading_forensic_synthesis.py
│   │   └── t3a_decision_nrr_rebuild.py
│   ├── simulation
│   │   ├── md_amr_data_adapter.py
│   │   ├── regime_replay.py
│   │   └── synthetic_llm_intent_generator.py
│   ├── system_stress_calibration
│   │   ├── __init__.py
│   │   └── core.py
│   ├── testing
│   │   ├── run_order_tests.py
│   │   └── run_tests.py
│   ├── _audit_sidecar_phase2.py
│   ├── _audit_sidecar_phase3.py
│   ├── _audit_sidecar_snapshot.py
│   ├── _freeze_snapshot.py
│   ├── build_project_atlas.py
│   ├── config_default_path_map.yaml
│   ├── log_audit.py
│   ├── metrics_summary.py
│   └── t5b_watchdog_analysis.py
└── vfoundation
    ├── adapters
    │   ├── exchange
    │   │   ├── __init__.py
    │   │   └── acl.py
    │   └── __init__.py
    ├── cli
    │   └── vfound
    │       ├── __init__.py
    │       └── __main__.py
    ├── core
    │   ├── adapters
    │   │   ├── __init__.py
    │   │   ├── base.py
    │   │   ├── execution_adapter.py
    │   │   ├── execution_exceptions.py
    │   │   └── idempotency_ledger.py
    │   ├── cache
    │   │   ├── __init__.py
    │   │   └── ttl_cache.py
    │   ├── idempotency
    │   │   ├── backends
    │   │   │   ├── __init__.py
    │   │   │   ├── redis_protocol.py
    │   │   │   ├── redis_store.py
    │   │   │   └── simple_redis_store.py
    │   │   ├── __init__.py
    │   │   ├── errors.py
    │   │   ├── idempotency.py
    │   │   └── store.py
    │   ├── __init__.py
    │   ├── backpressure.py
    │   ├── data_ref.py
    │   ├── deprecation.py
    │   ├── errors.py
    │   ├── exchange_context.py
    │   ├── fsm_core.py
    │   ├── fsm_emit_compat.py
    │   ├── fsm_v2.py
    │   ├── intent_layer.py
    │   ├── lifecycle.py
    │   ├── message_compat.py
    │   ├── meta_fsm_v2.py
    │   ├── payloads.py
    │   ├── protocol.py
    │   ├── protocol_migration.py
    │   ├── reconcile.py
    │   ├── retry_cb.py
    │   ├── retry_scheduler.py
    │   ├── routing.py
    │   ├── schema_registry.py
    │   ├── schema_validator.py
    │   ├── schema_version.py
    │   ├── ttl.py
    │   └── why_codes.py
    ├── dataref
    │   ├── latent_embeddings.py
    │   ├── streaming_io.py
    │   └── wal_archiver.py
    ├── dictionaries
    │   ├── domains
    │   │   ├── domain_decision_making.yaml
    │   │   ├── domain_execution_position.yaml
    │   │   ├── domain_feature_engineering.yaml
    │   │   ├── domain_market_data.yaml
    │   │   └── domain_risk_management.yaml
    │   ├── global_v2_2.yaml
    │   └── global_v2_2_framework.yaml
    ├── dr
    │   ├── dr_loader.py
    │   ├── merkle.py
    │   ├── replay.py
    │   ├── replay_boundary.py
    │   ├── snapshot.py
    │   ├── wal.py
    │   └── wal_gc.py
    ├── examples
    │   └── flow.yaml
    ├── obs
    │   ├── alert_manager.py
    │   ├── correlation.py
    │   ├── debug_api.py
    │   ├── domain_bridge.py
    │   ├── entropy_monitor.py
    │   ├── logger.py
    │   ├── order_logger.py
    │   ├── otlp_exporter.py
    │   ├── topology_auditor.py
    │   ├── tracing.py
    │   ├── why.py
    │   ├── why_chain_coverage.py
    │   └── xai_store.py
    ├── security
    │   ├── ratelimits.py
    │   ├── rbac_abac.py
    │   ├── redaction.py
    │   └── signing_ed25519.py
    ├── testing
    │   ├── __init__.py
    │   ├── chaos.py
    │   ├── dr_timing.py
    │   └── perf_benchmark.py
    ├── __init__.py
    └── config.py
```
