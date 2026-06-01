"""Agent probe — synthetic execution check for published agents.

After an agent is published it sits in ``probe_status='probation'``. The
probe synthesises a valid input from the agent's ``inputSchema``, executes
it, validates the output against ``outputSchema``, checks latency against
the declared SLA, and promotes the agent to ``live`` (or parks it in
``failing_probe``). See docs/PLAN-BPP-REGISTRY-LIFECYCLE.md, Epic E.

This package is import-safe without the DB stack for the pure helpers
(``synth``); the DB-backed runner/repository are imported explicitly.
"""
