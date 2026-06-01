"""Demo orchestrator — Story 1 cross-BPP legal pipeline.

This package implements the marketplace's flagship demo: a buyer-side
orchestrator that runs a controlled multi-step pipeline across two
BPPs (Tecla legal summarizer → Serg structured extractor) using the
real Beckn flow at every hop and validates each step's output against
the agent's declared JSON Schema.

Submodules
----------
specs      Frozen contract for the controlled demo (agent ids, BPP
           endpoints, declared input/output JSON Schemas, the planner
           prompt and the expected plan shape).
schema     Pure JSON Schema validator wrapper — failures are reported
           with a stable code/message so the UI can render them.
runner     Step-by-step orchestrator: discover → planner → step1 → step2,
           with per-step timing, schema validation, and structured
           execution traces returned to the caller.
"""
