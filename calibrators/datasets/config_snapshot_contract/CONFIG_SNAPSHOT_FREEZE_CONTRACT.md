# CONFIG_SNAPSHOT_FREEZE_CONTRACT

This contract is for future frozen runtime bundles only. It does not retroactively make 03U config-authoritative.

## Rules
- Copy only. Never mutate runtime YAML during snapshot capture.
- Store the snapshot inside logs/frozen/<bundle>/config_snapshot/.
- Record missing optional or required configs explicitly; do not silently omit them.
- Record git branch, commit SHA, and dirty worktree status at capture time.
- Parse each copied YAML with a safe YAML parser when available and record parse status plus top-level keys.
- Record sha256 and byte size for each copied config file.
- Current workspace reference snapshots remain non-authoritative for past runtime bundles.

## Config Set
| Config | Required | Copied To | Notes |
| --- | --- | --- | --- |
| config/aurora/domains.yaml | yes | config_snapshot/config/aurora/domains.yaml | Decision-making domain config including LOW_VOL gate thresholds. |
| config/aurora/trading.yaml | yes | config_snapshot/config/aurora/trading.yaml | Trading mode and execution envelope config. |
| config/aurora/strategies.yaml | yes | config_snapshot/config/aurora/strategies.yaml | Strategy routing and enablement config. |
| config/aurora/strategies/aurora.yaml | yes | config_snapshot/config/aurora/strategies/aurora.yaml | Aurora strategy config surface. |
| config/aurora/strategies/md_amr.yaml | yes | config_snapshot/config/aurora/strategies/md_amr.yaml | MD AMR strategy config surface. |
| config/aurora/strategies/mean_reversion.yaml | yes | config_snapshot/config/aurora/strategies/mean_reversion.yaml | Mean reversion strategy config surface. |
| config/aurora/regime.yaml | yes | config_snapshot/config/aurora/regime.yaml | Regime detector config. |
| config/aurora/observability.yaml | yes | config_snapshot/config/aurora/observability.yaml | Observability config relevant for future frozen bundles. |
| config/alpha_search.yaml | optional | config_snapshot/config/alpha_search.yaml | Optional alpha search runtime config. |
| config/judge_review.yaml | optional | config_snapshot/config/judge_review.yaml | Optional judge review config. |
| config/judge_simulator.yaml | optional | config_snapshot/config/judge_simulator.yaml | Optional judge simulator config. |

## Required Manifest Fields
| Field | Meaning |
| --- | --- |
| generated_at_utc | UTC timestamp when the manifest was created |
| git.branch | Capture-time branch name |
| git.commit_sha | Capture-time commit SHA |
| git.status_short | Capture-time git status --short lines |
| files[].config | Repo-relative config path |
| files[].exists | Whether the source file existed at capture time |
| files[].size_bytes | Source file size in bytes |
| files[].sha256 | Source file SHA256 digest |
| files[].copied_to | Bundle-relative copied path |
| files[].modified_time_utc | Source file modified time rendered as UTC |
| files[].parse_status | MISSING, PARSED_MAPPING, PARSED_NON_MAPPING, PARSE_ERROR, or YAML_LIBRARY_UNAVAILABLE |
| files[].top_level_keys | Top-level mapping keys when parseable |
