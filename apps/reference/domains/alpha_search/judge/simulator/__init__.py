"""Phase 5 simulator foundation (Packages 5A–5H)."""

from .config_schema_validator import (
    run_simulator_preflight,
    validate_simulator_config_file,
    validate_simulator_paths,
    validate_simulator_schema_set,
)
from .cli import (
    EXIT_BAD_CONFIG,
    EXIT_MISSING_INPUT,
    EXIT_SIMULATION_FAILURE,
    EXIT_SUCCESS,
    EXIT_WRITE_FAILURE,
    load_simulator_config,
    main as cli_main,
    run_from_config,
)
from .calibration_dataset_writer import (
    build_calibration_records,
    write_calibration_dataset,
)
from .config_models import SimulatorConfig
from .disagreement_analyzer import (
    build_disagreement_record,
    compute_disagreement,
    determine_optimal_action,
)
from .expert_accuracy_reporter import (
    aggregate_expert_accuracy,
    compute_expert_accuracy_for_cycle,
)
from .fee_slippage_calculator import (
    compute_fee_cost_bps,
    compute_net_return,
    compute_slippage_cost_pct,
)
from .simulator_engine import (
    AccuracyBucket,
    BasicAccuracySummary,
    CorrelatedVerdictOutcome,
    CorrelationKey,
    OutcomeRecord,
    SimulationResult,
    VerdictRecord,
    build_disagreement_records,
    build_expert_accuracy_records,
    compute_basic_accuracy,
    correlate_verdicts_to_outcomes,
    enrich_correlations_with_economics,
    load_outcome_data,
    load_verdict_records,
    run_simulation,
)

__all__ = [
    # 5H — config/schema validation
    "run_simulator_preflight",
    "validate_simulator_config_file",
    "validate_simulator_paths",
    "validate_simulator_schema_set",
    # 5F — CLI
    "EXIT_BAD_CONFIG",
    "EXIT_MISSING_INPUT",
    "EXIT_SIMULATION_FAILURE",
    "EXIT_SUCCESS",
    "EXIT_WRITE_FAILURE",
    "cli_main",
    "load_simulator_config",
    "run_from_config",
    "AccuracyBucket",
    "BasicAccuracySummary",
    "CorrelatedVerdictOutcome",
    "CorrelationKey",
    "OutcomeRecord",
    "SimulationResult",
    "SimulatorConfig",
    "VerdictRecord",
    "aggregate_expert_accuracy",
    "build_calibration_records",
    "build_disagreement_record",
    "build_disagreement_records",
    "build_expert_accuracy_records",
    "compute_disagreement",
    "compute_expert_accuracy_for_cycle",
    "compute_fee_cost_bps",
    "compute_basic_accuracy",
    "compute_net_return",
    "compute_slippage_cost_pct",
    "correlate_verdicts_to_outcomes",
    "determine_optimal_action",
    "enrich_correlations_with_economics",
    "load_outcome_data",
    "load_verdict_records",
    "run_simulation",
    "write_calibration_dataset",
]
