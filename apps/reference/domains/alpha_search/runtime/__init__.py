"""
Alpha Search Standalone Runtime
===============================

Standalone domain process for parallel shadow-mode alpha search.
Runs 10+ scenario variants concurrently without dependency on apps/reference/main.py.

Architecture:
  IngestGateway -> ScenarioManager -> [ScenarioWorker x N] -> AggregateReporter
"""
